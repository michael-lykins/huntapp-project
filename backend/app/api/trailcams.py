"""
Trail camera API endpoints.

Pulls camera list from tactacam-cameras ES index and recent images
from tactacam-images for the map popup panel.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import boto3
from botocore.client import Config
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from elasticsearch import Elasticsearch

logger = logging.getLogger(__name__)

router = APIRouter(tags=["trailcams"])

CAMERAS_INDEX = "tactacam-cameras"
IMAGES_INDEX = "tactacam-images"
S3_BUCKET = os.getenv("S3_BUCKET", "trailcam-images")

# External MinIO URL for presigned URLs (browser-accessible)
# Inside Docker: minio:9000; from browser: localhost:9000
S3_PUBLIC_ENDPOINT = os.getenv("S3_PUBLIC_ENDPOINT", os.getenv("S3_ENDPOINT", ""))


def _es(request: Request) -> Elasticsearch:
    es: Optional[Elasticsearch] = getattr(request.app.state, "es", None)
    if es is None:
        raise HTTPException(status_code=503, detail="Elasticsearch not initialized")
    return es


def _s3_public():
    """S3 client using the browser-accessible endpoint for presigned URL generation."""
    endpoint = S3_PUBLIC_ENDPOINT or None
    # If running inside Docker (minio:9000), swap to localhost for browser access
    if endpoint and "minio:" in endpoint:
        endpoint = endpoint.replace("minio:", "localhost:")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
        region_name=os.getenv("S3_REGION", "us-east-1"),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _presign(s3, key: str, expires: int = 3600) -> Optional[str]:
    try:
        return s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": key},
            ExpiresIn=expires,
        )
    except Exception as exc:
        logger.warning("presign failed for %s: %s", key, exc)
        return None


@router.get("/trailcams")
def list_trailcams(request: Request, es: Elasticsearch = Depends(_es)):
    """List all trail cameras from ES with location, status, and AI summary stats."""
    try:
        resp = es.search(
            index=CAMERAS_INDEX,
            body={
                "size": 200,
                "query": {"match_all": {}},
                "sort": [{"last_transmission_ts": {"order": "desc", "missing": "_last"}}],
            },
        )
    except Exception as exc:
        logger.error("ES query failed for cameras: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))

    cameras = []
    for hit in resp["hits"]["hits"]:
        src = hit["_source"]
        loc = src.get("location") or {}
        def _f(v):
            try: return float(v)
            except (TypeError, ValueError): return None

        cameras.append({
            "id": hit["_id"],
            "camera_id": src.get("camera_id", hit["_id"]),
            "name": src.get("name") or src.get("camera_name") or hit["_id"],
            "model": src.get("model"),
            "property_id": src.get("property_id"),
            "property_name": src.get("property_name"),
            "lat": _f(loc.get("lat")),
            "lon": _f(loc.get("lon")),
            "last_transmission_ts": src.get("last_transmission_ts"),
            "last_sync_ts": src.get("last_sync_ts"),
            "battery_level": src.get("battery_level"),
            "signal_strength": src.get("signal_strength"),
        })

    return {"count": len(cameras), "cameras": cameras}


@router.get("/trailcams/{camera_id}/images")
def camera_images(
    camera_id: str,
    request: Request,
    es: Elasticsearch = Depends(_es),
    limit: int = Query(6, ge=1, le=50),
    animals_only: bool = Query(False),
):
    """Recent AI-analyzed images for a specific camera, with presigned S3 URLs."""
    must_filters: list = [{"term": {"camera_id": camera_id}}]
    if animals_only:
        must_filters.append({"term": {"ai_has_animal": True}})

    try:
        resp = es.search(
            index=IMAGES_INDEX,
            body={
                "size": limit,
                "query": {"bool": {"must": must_filters}},
                "sort": [{"@timestamp": {"order": "desc"}}],
                "_source": [
                    "filename", "s3_key", "@timestamp",
                    "ai_has_animal", "ai_species", "ai_sex",
                    "ai_age_class", "ai_antlers", "ai_confidence",
                    "ai_labels", "ai_notes", "has_headshot",
                    "camera_name",
                    "weather.temperature", "weather.wind_speed", "weather.wind_cardinal",
                    "weather.pressure_hpa", "weather.pressure_tendency",
                    "weather.moon_phase", "weather.sun_phase", "weather.label",
                ],
            },
        )
    except Exception as exc:
        logger.error("ES query failed for camera %s images: %s", camera_id, exc)
        raise HTTPException(status_code=502, detail=str(exc))

    s3 = _s3_public()
    images = []
    for hit in resp["hits"]["hits"]:
        src = hit["_source"]
        s3_key = src.get("s3_key")
        url = _presign(s3, s3_key) if s3_key else None
        images.append({
            "id": hit["_id"],
            "filename": src.get("filename"),
            "timestamp": src.get("@timestamp"),
            "url": url,
            "s3_key": s3_key,
            "ai_has_animal": src.get("ai_has_animal"),
            "ai_species": src.get("ai_species"),
            "ai_sex": src.get("ai_sex"),
            "ai_age_class": src.get("ai_age_class"),
            "ai_antlers": src.get("ai_antlers"),
            "ai_confidence": src.get("ai_confidence"),
            "ai_labels": src.get("ai_labels", []),
            "ai_notes": src.get("ai_notes"),
            "has_headshot": src.get("has_headshot"),
            "camera_name": src.get("camera_name"),
            "weather": src.get("weather"),
        })

    return {"camera_id": camera_id, "count": len(images), "images": images}


@router.get("/trailcams/{camera_id}/activity")
def camera_activity(camera_id: str, request: Request, es: Elasticsearch = Depends(_es)):
    """Hour-of-day sighting distribution (animals only) for stand timing intel."""
    try:
        resp = es.search(
            index=IMAGES_INDEX,
            body={
                "size": 0,
                "query": {"bool": {"must": [
                    {"term": {"camera_id": camera_id}},
                    {"term": {"ai_has_animal": True}},
                ]}},
                "aggs": {
                    "by_hour": {
                        "terms": {
                            "script": {
                                "source": "doc['@timestamp'].value.getHour()",
                                "lang": "painless",
                            },
                            "size": 24,
                            "order": {"_key": "asc"},
                        }
                    }
                },
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    buckets = resp.get("aggregations", {}).get("by_hour", {}).get("buckets", [])
    by_hour = {int(b["key"]): b["doc_count"] for b in buckets}
    hours = [{"hour": h, "count": by_hour.get(h, 0)} for h in range(24)]
    total = sum(h["count"] for h in hours)
    peak = max(hours, key=lambda h: h["count"])["hour"] if total else None
    return {"camera_id": camera_id, "total": total, "peak_hour": peak, "hours": hours}


@router.get("/trailcams/{camera_id}/stats")
def camera_stats(camera_id: str, request: Request, es: Elasticsearch = Depends(_es)):
    """AI species breakdown for a camera."""
    try:
        resp = es.search(
            index=IMAGES_INDEX,
            body={
                "size": 0,
                "query": {"bool": {"must": [
                    {"term": {"camera_id": camera_id}},
                    {"term": {"ai_has_animal": True}},
                ]}},
                "aggs": {
                    "by_species": {
                        "terms": {"field": "ai_species", "size": 20},
                    },
                },
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    aggs = resp.get("aggregations", {})
    species = [
        {"species": b["key"], "count": b["doc_count"]}
        for b in aggs.get("by_species", {}).get("buckets", [])
    ]
    return {
        "camera_id": camera_id,
        "animal_photos": resp["hits"]["total"]["value"],
        "species": species,
    }
