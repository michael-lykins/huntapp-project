"""
OnX sync logic.

Pulls waypoints, tracks, lines, shapes, land areas, and trail cameras from
OnX and upserts them into Elasticsearch.  All operations are idempotent —
running multiple times is safe.

Indices:
    onx-waypoints    — stands, blinds, parking, food plots, gates, etc.
    onx-markups      — tracks, lines, shapes
    onx-land-areas   — property boundaries with full polygon geometry
    onx-cameras      — trail cameras registered in OnX (cross-ref Tactacam)
"""
import logging
import os
from datetime import datetime, timezone

from elasticsearch import Elasticsearch, helpers

from .onx_auth import OnxAuth
from .onx_client import OnxClient

logger = logging.getLogger(__name__)

WAYPOINTS_INDEX = "onx-waypoints"
MARKUPS_INDEX = "onx-markups"
LAND_AREAS_INDEX = "onx-land-areas"
CAMERAS_INDEX = "onx-cameras"


def _es() -> Elasticsearch:
    return Elasticsearch(
        hosts=[os.environ["ELASTIC_SEARCH_HOST"]],
        api_key=os.environ["ELASTIC_SEARCH_API_KEY"],
    )


# ── Document builders ─────────────────────────────────────────────────────────

def _geo_point(coords: list) -> dict | None:
    """Convert [lon, lat, alt?] to ES geo_point {lat, lon}."""
    if not coords or len(coords) < 2:
        return None
    return {"lat": coords[1], "lon": coords[0]}


def _waypoint_doc(item: dict) -> dict:
    geo = item.get("geo_json") or {}
    geom = geo.get("geometry") or {}
    props = geo.get("properties") or {}
    coords = geom.get("coordinates") or []

    owner = item.get("owner") or {}
    doc = {
        "@timestamp": item.get("updated_at") or item.get("created_at"),
        "uuid": item.get("uuid"),
        "name": item.get("name"),
        "type": "waypoint",
        "icon": props.get("icon"),
        "color": item.get("color"),
        "notes": item.get("notes"),
        "updated_at": item.get("updated_at"),
        "created_at": item.get("created_at"),
        "last_synced_at": item.get("last_synced_at"),
        "permissions": item.get("permissions", []),
        "owner": {
            "account_id": owner.get("account_id"),
            "name": owner.get("name"),
        } if owner else None,
        "attachments_photo_count": len((item.get("attachments") or {}).get("photos", [])),
        "ingest_ts": datetime.now(timezone.utc).isoformat(),
    }
    pt = _geo_point(coords)
    if pt:
        doc["location"] = pt
    if len(coords) > 2:
        doc["altitude_m"] = coords[2]
    return doc


def _markup_doc(item: dict, markup_type: str) -> dict:
    geo = item.get("geo_json") or {}
    geom = geo.get("geometry") or {}
    props = geo.get("properties") or {}
    coords = geom.get("coordinates") or []

    owner = item.get("owner") or {}
    doc = {
        "@timestamp": item.get("updated_at") or item.get("created_at"),
        "uuid": item.get("uuid"),
        "name": item.get("name"),
        "type": markup_type,
        "color": props.get("color") or item.get("color"),
        "notes": item.get("notes"),
        "updated_at": item.get("updated_at"),
        "created_at": item.get("created_at"),
        "permissions": item.get("permissions", []),
        "owner": {
            "account_id": owner.get("account_id"),
            "name": owner.get("name"),
        } if owner else None,
        "geometry_type": geom.get("type"),
        "ingest_ts": datetime.now(timezone.utc).isoformat(),
    }

    # For tracks/lines store the raw GeoJSON so we can render on the map later
    if markup_type in ("track", "line") and coords:
        doc["geojson_coordinates"] = coords
        # Centroid approximation from first point
        first = coords[0] if coords else []
        if first and len(first) >= 2:
            doc["location"] = {"lat": first[1], "lon": first[0]}

    # For shapes store polygon coordinates
    if markup_type == "shape" and coords:
        doc["geojson_coordinates"] = coords
        # Approximate centroid from outer ring first point
        outer = coords[0] if coords else []
        first = outer[0] if outer else []
        if first and len(first) >= 2:
            doc["location"] = {"lat": first[1], "lon": first[0]}

    return doc


def _land_area_doc(item: dict) -> dict:
    return {
        "@timestamp": item.get("createdAt"),
        "id": item.get("id"),
        "name": item.get("name"),
        "area_sqm": item.get("area"),
        "created_at": item.get("createdAt"),
        "created_by": item.get("createdBy"),
        "permissions": item.get("permissions", []),
        "style": item.get("style"),
        "geometry": item.get("geometry"),       # full GeoJSON geometry
        "section_count": len(item.get("sections") or []),
        "sections": [
            {
                "id": s.get("id"),
                "name": s.get("name"),
                "area_sqm": s.get("area"),
                "geometry": s.get("geometry"),
                "representative_point": s.get("representativePoint"),
                "county_names": (s.get("attributes") or {}).get("countyNames"),
                "states": [
                    st.get("abbreviation")
                    for st in ((s.get("attributes") or {}).get("states") or [])
                    if st.get("abbreviation")
                ],
            }
            for s in (item.get("sections") or [])
        ],
        "ingest_ts": datetime.now(timezone.utc).isoformat(),
    }


def _camera_doc(node: dict) -> dict:
    placement = node.get("currentPlacement") or {}
    loc = placement.get("location") or {}
    make = (node.get("deviceInformation") or {}).get("make") or {}
    battery = (node.get("deviceInformation") or {}).get("batteryInformation") or {}
    orientation = placement.get("orientation") or {}
    integration = node.get("integrationInformation") or {}
    latest_photos = node.get("photos", {}).get("edges", [])
    latest_photo = (latest_photos[0]["node"] if latest_photos else None)

    doc = {
        "@timestamp": placement.get("placedAt") or node.get("lastChangedBatteries"),
        "onx_id": node.get("id"),
        "name": node.get("name"),
        "in_field": node.get("inField"),
        "brand": make.get("brand"),
        "model": make.get("model"),
        "is_cellular": (node.get("deviceInformation") or {}).get("isCellular"),
        "battery_count": battery.get("numberOfBatteries"),
        "last_changed_batteries": node.get("lastChangedBatteries"),
        "partner_brand": integration.get("partnerBrand"),
        "placement": {
            "id": placement.get("id"),
            "name": placement.get("name"),
            "placed_at": placement.get("placedAt"),
            "orientation_begin": orientation.get("beginning"),
            "orientation_end": orientation.get("end"),
        },
        "sd_card": node.get("sdCard"),
        "notes": [n.get("content") for n in (node.get("notes") or []) if n.get("content")],
        "color": (node.get("presentation") or {}).get("color"),
        "historical_placement_count": len(node.get("historicalPlacements") or []),
        "removed_from_inventory_at": node.get("removedFromInventoryAt"),
        "latest_photo_url": (latest_photo or {}).get("contentUrl"),
        "latest_photo_captured_at": (latest_photo or {}).get("capturedAtLocal"),
        "ingest_ts": datetime.now(timezone.utc).isoformat(),
    }
    if loc.get("lat") and loc.get("lon"):
        doc["location"] = {"lat": loc["lat"], "lon": loc["lon"]}
    return doc


# ── Sync entry point ──────────────────────────────────────────────────────────

def run_onx_sync() -> dict[str, int]:
    """
    Pull all OnX data and upsert to Elasticsearch.
    Returns counts per data type.
    """
    auth = OnxAuth()
    client = OnxClient(auth)
    es = _es()

    results: dict[str, int] = {}
    bulk_docs = []

    # ── Waypoints ──
    try:
        waypoints = client.get_waypoints()
        for item in waypoints:
            uuid = item.get("uuid")
            if not uuid:
                continue
            bulk_docs.append({
                "_index": WAYPOINTS_INDEX,
                "_id": uuid,
                "_source": _waypoint_doc(item),
            })
        results["waypoints"] = len(waypoints)
    except Exception as exc:
        logger.error("Failed to sync waypoints: %s", exc)
        results["waypoints"] = 0

    # ── Tracks ──
    try:
        tracks = client.get_tracks()
        for item in tracks:
            uuid = item.get("uuid")
            if not uuid:
                continue
            bulk_docs.append({
                "_index": MARKUPS_INDEX,
                "_id": uuid,
                "_source": _markup_doc(item, "track"),
            })
        results["tracks"] = len(tracks)
    except Exception as exc:
        logger.error("Failed to sync tracks: %s", exc)
        results["tracks"] = 0

    # ── Lines ──
    try:
        lines = client.get_lines()
        for item in lines:
            uuid = item.get("uuid")
            if not uuid:
                continue
            bulk_docs.append({
                "_index": MARKUPS_INDEX,
                "_id": uuid,
                "_source": _markup_doc(item, "line"),
            })
        results["lines"] = len(lines)
    except Exception as exc:
        logger.error("Failed to sync lines: %s", exc)
        results["lines"] = 0

    # ── Shapes ──
    try:
        shapes = client.get_shapes()
        for item in shapes:
            uuid = item.get("uuid")
            if not uuid:
                continue
            bulk_docs.append({
                "_index": MARKUPS_INDEX,
                "_id": uuid,
                "_source": _markup_doc(item, "shape"),
            })
        results["shapes"] = len(shapes)
    except Exception as exc:
        logger.error("Failed to sync shapes: %s", exc)
        results["shapes"] = 0

    # ── Land areas ──
    try:
        land_areas = client.get_land_areas()
        for item in land_areas:
            area_id = item.get("id")
            if not area_id:
                continue
            bulk_docs.append({
                "_index": LAND_AREAS_INDEX,
                "_id": area_id,
                "_source": _land_area_doc(item),
            })
        results["land_areas"] = len(land_areas)
    except Exception as exc:
        logger.error("Failed to sync land areas: %s", exc)
        results["land_areas"] = 0

    # ── Trail cameras ──
    try:
        cameras = client.get_trail_cams()
        for node in cameras:
            cam_id = node.get("id")
            if not cam_id:
                continue
            bulk_docs.append({
                "_index": CAMERAS_INDEX,
                "_id": cam_id,
                "_source": _camera_doc(node),
            })
        results["cameras"] = len(cameras)
    except Exception as exc:
        logger.error("Failed to sync trail cameras: %s", exc)
        results["cameras"] = 0

    # ── Bulk write ──
    if bulk_docs:
        helpers.bulk(es, bulk_docs)
        logger.info(
            "OnX sync complete: %d waypoints, %d tracks, %d lines, %d shapes, "
            "%d land_areas, %d cameras",
            results.get("waypoints", 0),
            results.get("tracks", 0),
            results.get("lines", 0),
            results.get("shapes", 0),
            results.get("land_areas", 0),
            results.get("cameras", 0),
        )
    else:
        logger.info("OnX sync: nothing to index")

    return results
