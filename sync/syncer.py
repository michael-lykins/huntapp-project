"""
Core Tactacam sync logic.

Strategy: single paginated pass through /photos/v2 (newest-first), collecting
photos for all cameras simultaneously. Stops when every photo on a page is
older than the oldest known sync timestamp across all active cameras.

On the very first run (no history), INITIAL_LOOKBACK_DAYS caps how far back
we go so we don't download years of images.
"""
import io
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests
import boto3
from botocore.client import Config
from elasticsearch import Elasticsearch, helpers

from .auth import TactacamAuth
from .client import TactacamClient

logger = logging.getLogger(__name__)

CAMERAS_INDEX = "tactacam-cameras"
IMAGES_INDEX = "tactacam-images"
S3_BUCKET = os.getenv("S3_BUCKET", "trailcam-images")
INITIAL_LOOKBACK_DAYS = int(os.getenv("INITIAL_LOOKBACK_DAYS", "30"))


def _es() -> Elasticsearch:
    return Elasticsearch(
        hosts=[os.environ["ELASTIC_SEARCH_HOST"]],
        api_key=os.environ["ELASTIC_SEARCH_API_KEY"],
    )


def _s3():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT"),
        aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
        region_name=os.getenv("S3_REGION", "us-east-1"),
        config=Config(signature_version="s3v4"),
    )


def _parse_ts(ts_str: str | None) -> datetime | None:
    if not ts_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(ts_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _last_sync_ts_all(es: Elasticsearch, camera_ids: list[str]) -> dict[str, datetime | None]:
    """Return the latest indexed photo timestamp for each camera in one query."""
    result: dict[str, datetime | None] = {cid: None for cid in camera_ids}
    try:
        resp = es.search(
            index=IMAGES_INDEX,
            body={
                "size": 0,
                "aggs": {
                    "by_camera": {
                        "terms": {"field": "camera_id", "size": 50},
                        "aggs": {
                            "latest": {"max": {"field": "@timestamp"}}
                        },
                    }
                },
            },
        )
        for bucket in resp["aggregations"]["by_camera"]["buckets"]:
            cid = bucket["key"]
            ts_ms = bucket["latest"]["value"]
            if cid in result and ts_ms:
                result[cid] = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    except Exception:
        pass  # index doesn't exist yet on first run
    return result


def _upsert_cameras(es: Elasticsearch, cameras: list[dict], last_sync_map: dict):
    docs = []
    for camera in cameras:
        cid = camera.get("cameraId") or camera.get("id")
        gps = camera.get("gps") or {}
        lat = gps.get("latitude")
        lon = gps.get("longitude")

        doc = {
            "camera_id": cid,
            "name": camera.get("name") or camera.get("cameraName"),
            "model": camera.get("hardwareVersion") or camera.get("model"),
            "property_name": camera.get("location"),
            "last_transmission_ts": camera.get("lastTransmissionTimestamp"),
            "battery_level": camera.get("batteryLevel"),
            "signal_strength": camera.get("signalStrength"),
        }
        if lat and lon:
            doc["location"] = {"lat": lat, "lon": lon}
        ts = last_sync_map.get(cid)
        if ts:
            doc["last_sync_ts"] = ts.isoformat()

        docs.append({"_index": CAMERAS_INDEX, "_id": cid, "_source": doc})

    if docs:
        helpers.bulk(es, docs)


def _s3_key(camera_id: str, filename: str) -> str:
    return f"tactacam/{camera_id}/{filename}"


def _build_index_doc(photo: dict, camera: dict, s3_key: str) -> dict:
    gps = photo.get("gpsLocation") or {}
    lat = gps.get("lat") or gps.get("latitude")
    lon = gps.get("lon") or gps.get("longitude")

    weather = photo.get("weatherRecord") or {}
    wind = weather.get("windDirection") or {}

    doc = {
        "@timestamp": photo.get("photoDateUtc"),
        "ingest_ts": datetime.now(timezone.utc).isoformat(),
        "camera_id": camera.get("cameraId") or camera.get("id"),
        "camera_name": camera.get("name") or camera.get("cameraName"),
        "property_name": camera.get("location"),
        "property_id": camera.get("propertyId"),
        "filename": photo.get("filename") or photo.get("photoId"),
        "s3_key": s3_key,
        "has_headshot": photo.get("hasHeadshot", False),
        "signal": (photo.get("metadata") or {}).get("signal") or photo.get("signal"),
        "battery": (photo.get("metadata") or {}).get("batteryLevel") or photo.get("batteryLevel"),
        "weather": {
            "temperature": weather.get("temperature"),
            "temp_max_12h": (weather.get("temperatureRange12Hours") or {}).get("max"),
            "temp_min_12h": (weather.get("temperatureRange12Hours") or {}).get("min"),
            "wind_speed": wind.get("speed"),
            "wind_deg": wind.get("degrees"),
            "wind_cardinal": wind.get("cardinalLabelShort"),
            "wind_gust": weather.get("windGust"),
            "pressure_hpa": weather.get("barometricPressure"),
            "pressure_tendency": weather.get("pressureTendency"),
            "moon_phase": str(weather["moonPhase"]) if weather.get("moonPhase") is not None else None,
            "sun_phase": weather.get("sunPhase"),
            "label": weather.get("weatherLabel"),
            "temp_departure_24h": weather.get("past24HoursTemperatureDeparture"),
        },
    }
    if lat and lon:
        doc["location"] = {"lat": lat, "lon": lon}
    return doc


def run_sync(camera_ids: list[str] | None = None, dry_run: bool = False) -> dict[str, int]:
    """
    Run a full sync cycle in a single pass through the photo feed.

    Args:
        camera_ids: If set, only collect photos for these cameras.
        dry_run: Skip all writes (auth/connectivity test only).
    """
    auth = TactacamAuth()
    client = TactacamClient(auth)
    es = _es()
    s3 = _s3()

    all_cameras = client.get_cameras()
    camera_map = {
        (c.get("cameraId") or c.get("id")): c
        for c in all_cameras
    }

    active_ids = set(camera_ids) if camera_ids else set(camera_map.keys())
    active_cameras = {cid: camera_map[cid] for cid in active_ids if cid in camera_map}

    # One aggregation query to get last-synced timestamp per camera
    last_sync_map = _last_sync_ts_all(es, list(active_ids))

    # Cutoff: oldest timestamp we care about.
    # For cameras with no history, use INITIAL_LOOKBACK_DAYS.
    initial_cutoff = datetime.now(timezone.utc) - timedelta(days=INITIAL_LOOKBACK_DAYS)
    cutoff_map: dict[str, datetime] = {
        cid: (last_sync_map.get(cid) or initial_cutoff)
        for cid in active_ids
    }
    global_cutoff = min(cutoff_map.values())

    logger.info(
        "Sync started: %d cameras, global cutoff %s",
        len(active_ids), global_cutoff.isoformat()
    )

    # Bucket photos by camera_id as we page through the feed
    photo_buckets: dict[str, list[dict]] = defaultdict(list)

    for photo in client.iter_photos(limit=100):
        photo_ts = _parse_ts(photo.get("photoDateUtc"))

        # Stop when every remaining photo is older than our global cutoff
        if photo_ts and photo_ts <= global_cutoff:
            break

        photo_cid = str(photo.get("cameraId") or "")
        if photo_cid not in active_ids:
            continue

        # Skip if this specific camera already has this photo
        cam_cutoff = cutoff_map.get(photo_cid, initial_cutoff)
        if photo_ts and photo_ts <= cam_cutoff:
            continue

        photo_buckets[photo_cid].append(photo)

    # Now process each camera's collected photos
    results: dict[str, int] = {}
    all_bulk_docs = []

    for cid, photos in photo_buckets.items():
        camera = active_cameras.get(cid, {})
        camera_results = 0

        for photo in photos:
            filename = photo.get("filename") or photo.get("photoId")
            key = _s3_key(cid, filename)

            if not dry_run:
                try:
                    img_bytes = requests.get(photo["photoUrl"], timeout=60).content
                    s3.upload_fileobj(
                        io.BytesIO(img_bytes),
                        S3_BUCKET,
                        key,
                        ExtraArgs={"ContentType": "image/jpeg"},
                    )
                except Exception as exc:
                    logger.error("Camera %s: failed to store %s: %s", cid, filename, exc)
                    continue

            doc = _build_index_doc(photo, camera, key)
            all_bulk_docs.append({
                "_index": IMAGES_INDEX,
                "_id": f"{cid}_{filename}",
                "_source": doc,
            })
            camera_results += 1

        results[cid] = camera_results
        logger.info("Camera %s (%s): %d new photos", cid, camera.get("name"), camera_results)

    # Mark cameras with no new photos
    for cid in active_ids:
        if cid not in results:
            results[cid] = 0

    if all_bulk_docs and not dry_run:
        helpers.bulk(es, all_bulk_docs)
        logger.info("Indexed %d total photos to ES", len(all_bulk_docs))

    # Upsert camera registry
    if not dry_run:
        _upsert_cameras(es, list(active_cameras.values()), last_sync_map)

    total = sum(results.values())
    logger.info("Sync complete: %d new photos across %d cameras", total, len(active_ids))
    return results
