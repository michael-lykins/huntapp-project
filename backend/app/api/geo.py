from __future__ import annotations
from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Query, Body, Form
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from elasticsearch import Elasticsearch
import uuid
import xml.etree.ElementTree as ET

# WebSocket notifier from ws module
from app.api.geo_ws import broadcast_geo_refresh, ws_connection_count

router = APIRouter(prefix="/geo", tags=["geo"])

WAYPOINTS_INDEX = "waypoints-v1"
TRACKS_INDEX    = "tracks-v1"

# ---------------- ES wiring ----------------
def es_dep(request: Request) -> Elasticsearch:
    es = getattr(request.app.state, "es", None)
    if es is None:
        raise HTTPException(status_code=503, detail="Elasticsearch not initialized")
    return es

def ensure_indices(es: Elasticsearch) -> None:
    if not es.indices.exists(index=WAYPOINTS_INDEX):
        es.indices.create(
            index=WAYPOINTS_INDEX,
            mappings={
                "properties": {
                    "name":        {"type": "keyword"},
                    "tags":        {"type": "keyword"},
                    "type":        {"type": "keyword"},
                    "location":    {"type": "geo_point"},
                    "trailcam": {
                        "properties": {
                            "id":    {"type": "keyword"},
                            "name":  {"type": "keyword"},
                            "make":  {"type": "keyword"},
                            "model": {"type": "keyword"},
                        }
                    },
                    "source":      {"type": "keyword"},
                    "source_name": {"type": "keyword"},
                    "created_at":  {"type": "date"},
                    "updated_at":  {"type": "date"},
                }
            }
        )
    if not es.indices.exists(index=TRACKS_INDEX):
        es.indices.create(
            index=TRACKS_INDEX,
            mappings={
                "properties": {
                    "name":        {"type": "keyword"},
                    "geometry":    {"type": "geo_shape"},       # LineString
                    "source":      {"type": "keyword"},
                    "source_name": {"type": "keyword"},
                    "created_at":  {"type": "date"},
                    "updated_at":  {"type": "date"},
                }
            }
        )

# ---------------- GPX/KML parsers ----------------
def _parse_gpx(file_bytes: bytes) -> List[Dict[str, Any]]:
    feats: List[Dict[str, Any]] = []
    try:
        root = ET.fromstring(file_bytes)
    except ET.ParseError as e:
        raise HTTPException(status_code=400, detail=f"Invalid GPX: {e}")
    ns = {'gpx': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}
    # waypoints
    for wpt in root.findall('.//gpx:wpt', ns) if ns else root.findall('.//wpt'):
        lat = float(wpt.get('lat')); lon = float(wpt.get('lon'))
        name_el = wpt.find('gpx:name', ns) if ns else wpt.find('name')
        feats.append({"type":"Feature","geometry":{"type":"Point","coordinates":[lon,lat]},
                      "properties":{"name": name_el.text if name_el is not None else None, "kind":"wpt"}})
    # tracks
    trk_path = './/gpx:trk' if ns else './/trk'
    trkseg_path = './/gpx:trkseg' if ns else './/trkseg'
    trkpt_path = './/gpx:trkpt' if ns else './/trkpt'
    for trk in root.findall(trk_path, ns):
        coords=[]
        for trkseg in trk.findall(trkseg_path, ns):
            for trkpt in trkseg.findall(trkpt_path, ns):
                coords.append([float(trkpt.get('lon')), float(trkpt.get('lat'))])
        if coords:
            name_el = trk.find('gpx:name', ns) if ns else trk.find('name')
            feats.append({"type":"Feature","geometry":{"type":"LineString","coordinates":coords},
                          "properties":{"name": name_el.text if name_el is not None else None, "kind":"trk"}})
    return feats

def _parse_kml(file_bytes: bytes) -> List[Dict[str, Any]]:
    feats: List[Dict[str, Any]] = []
    try:
        root = ET.fromstring(file_bytes)
    except ET.ParseError as e:
        raise HTTPException(status_code=400, detail=f"Invalid KML: {e}")
    ns={'kml': 'http://www.opengis.net/kml/2.2'}
    for pm in root.findall('.//kml:Placemark', ns):
        name_el = pm.find('kml:name', ns)
        pt = pm.find('.//kml:Point/kml:coordinates', ns)
        line = pm.find('.//kml:LineString/kml:coordinates', ns)
        if pt is not None and pt.text:
            lon,lat,*_ = [float(x) for x in pt.text.strip().split(',')]
            feats.append({"type":"Feature","geometry":{"type":"Point","coordinates":[lon,lat]},
                          "properties":{"name": name_el.text if name_el is not None else None, "kind":"wpt"}})
        elif line is not None and line.text:
            coords=[]
            for pair in line.text.strip().split():
                lon,lat,*_ = [float(x) for x in pair.split(',')]
                coords.append([lon,lat])
            feats.append({"type":"Feature","geometry":{"type":"LineString","coordinates":coords},
                          "properties":{"name": name_el.text if name_el is not None else None, "kind":"trk"}})
    return feats

def _split(features: List[Dict[str,Any]]) -> Tuple[List[Dict[str,Any]], List[Dict[str,Any]]]:
    pts, lines = [], []
    for f in features:
        g = f.get("geometry", {})
        if g.get("type") == "Point":
            pts.append(f)
        elif g.get("type") == "LineString":
            lines.append(f)
    return pts, lines

# ---------------- Dedupe / nearest search ----------------
def _find_nearest_point_id(es: Elasticsearch, lat: float, lon: float, max_meters: float) -> Optional[str]:
    q = {
        "size": 1,
        "query": {"match_all": {}},
        "sort": [{
            "_geo_distance": {
                "location": {"lat": lat, "lon": lon},
                "unit": "m",
                "order": "asc"
            }
        }],
        "_source": False
    }
    res = es.search(index=WAYPOINTS_INDEX, body=q)
    hits = res.get("hits", {}).get("hits", [])
    if not hits:
        return None
    dist = hits[0].get("sort", [None])[0]
    if dist is not None and dist <= max_meters:
        return hits[0]["_id"]
    return None

# ---------------- Public routes ----------------
@router.post("/upload")
async def upload_geo(file: UploadFile = File(...)):
    name = (file.filename or "").lower()
    raw = await file.read()
    if name.endswith(".gpx"):
        feats = _parse_gpx(raw)
    elif name.endswith(".kml"):
        feats = _parse_kml(raw)
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type. Use .gpx or .kml.")
    return {"ok": True, "count": len(feats), "features": feats}

@router.post("/ingest")
async def ingest_geo(
    request: Request,
    file: UploadFile = File(...),
    source_name: Optional[str] = Form(None),
    dedupe_meters: float = Form(10.0),
    trailcam_id: Optional[str] = Form(None),
    trailcam_name: Optional[str] = Form(None),
    trailcam_make: Optional[str] = Form(None),
    trailcam_model: Optional[str] = Form(None),
):
    es = es_dep(request)
    ensure_indices(es)

    name = (file.filename or "").lower()
    raw = await file.read()
    if name.endswith(".gpx"):
        feats = _parse_gpx(raw)
    elif name.endswith(".kml"):
        feats = _parse_kml(raw)
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type. Use .gpx or .kml.")

    pts, lines = _split(feats)
    now = datetime.now(timezone.utc).isoformat()

    trailcam_obj = None
    if trailcam_id or trailcam_name or trailcam_make or trailcam_model:
        trailcam_obj = {
            "id": trailcam_id,
            "name": trailcam_name,
            "make": trailcam_make,
            "model": trailcam_model,
        }

    created, updated = 0, 0

    for p in pts:
        lon, lat = p["geometry"]["coordinates"]
        existing_id = _find_nearest_point_id(es, lat=lat, lon=lon, max_meters=dedupe_meters)
        if existing_id:
            doc: Dict[str, Any] = {"updated_at": now}
            pname = (p.get("properties") or {}).get("name")
            if pname:
                doc["name"] = pname
            if trailcam_obj:
                doc["trailcam"] = trailcam_obj
            es.update(index=WAYPOINTS_INDEX, id=existing_id, body={"doc": doc})
            updated += 1
        else:
            doc_id = uuid.uuid4().hex
            body = {
                "name": (p.get("properties") or {}).get("name"),
                "tags": [],
                "type": None,
                "location": {"lat": lat, "lon": lon},
                "trailcam": trailcam_obj,
                "source": "gpx_kml",
                "source_name": source_name or file.filename,
                "created_at": now,
                "updated_at": now,
            }
            es.index(index=WAYPOINTS_INDEX, id=doc_id, document=body)
            created += 1

    for l in lines:
        doc_id = uuid.uuid4().hex
        body = {
            "name": (l.get("properties") or {}).get("name"),
            "geometry": l["geometry"],
            "source": "gpx_kml",
            "source_name": source_name or file.filename,
            "created_at": now,
            "updated_at": now,
        }
        es.index(index=TRACKS_INDEX, id=doc_id, document=body)

    try:
        await broadcast_geo_refresh()
    except Exception:
        pass

    return {"ok": True, "waypoints_created": created, "waypoints_updated": updated, "tracks_indexed": len(lines)}

@router.post("/waypoints")
async def create_waypoint(
    request: Request,
    name: Optional[str] = Body(None),
    lat: float = Body(...),
    lon: float = Body(...),
    type: Optional[str] = Body(None),
    trailcam: Optional[Dict[str, Any]] = Body(None),
):
    """
    Create a single waypoint.
    """
    es = es_dep(request)
    ensure_indices(es)
    now = datetime.now(timezone.utc).isoformat()

    doc_id = uuid.uuid4().hex
    body = {
        "name": name,
        "tags": [],
        "type": type,
        "location": {"lat": lat, "lon": lon},
        "trailcam": trailcam,
        "source": "manual",
        "source_name": "map_click",
        "created_at": now,
        "updated_at": now,
    }
    es.index(index=WAYPOINTS_INDEX, id=doc_id, document=body)

    try:
        await broadcast_geo_refresh()
    except Exception:
        pass

    return {"ok": True, "id": doc_id}

@router.post("/tracks")
async def create_track(
    request: Request,
    name: Optional[str] = Body(None),
    coordinates: List[List[float]] = Body(..., embed=True),  # [[lon,lat], ...]
    source_name: Optional[str] = Body("manual_drawn"),
):
    """
    Create a LineString track.
    """
    es = es_dep(request)
    ensure_indices(es)
    now = datetime.now(timezone.utc).isoformat()

    if not coordinates or any(len(c) != 2 for c in coordinates):
        raise HTTPException(status_code=400, detail="coordinates must be [[lon,lat], ...]")

    doc_id = uuid.uuid4().hex
    body = {
        "name": name,
        "geometry": {"type": "LineString", "coordinates": coordinates},
        "source": "manual",
        "source_name": source_name,
        "created_at": now,
        "updated_at": now,
    }
    es.index(index=TRACKS_INDEX, id=doc_id, document=body)

    try:
        await broadcast_geo_refresh()
    except Exception:
        pass

    return {"ok": True, "id": doc_id}

@router.get("/features")
def get_features_bbox(
    request: Request,
    bbox: str = Query(..., description="minLon,minLat,maxLon,maxLat"),
    limit_points: int = Query(2000, ge=1, le=10000),
    limit_lines: int = Query(1000, ge=1, le=10000),
):
    es = es_dep(request)
    ensure_indices(es)

    try:
        min_lon, min_lat, max_lon, max_lat = [float(x) for x in bbox.split(",")]
    except Exception:
        raise HTTPException(status_code=400, detail="bbox must be minLon,minLat,maxLon,maxLat")

    q_points = {
        "size": limit_points,
        "query": {
            "bool": {
                "filter": [
                    {"geo_bounding_box": {
                        "location": {
                            "top_left": {"lat": max_lat, "lon": min_lon},
                            "bottom_right": {"lat": min_lat, "lon": max_lon},
                        }
                    }}
                ]
            }
        },
        "_source": ["name", "location", "trailcam", "type"]
    }

    q_lines = {
        "size": limit_lines,
        "query": {
            "bool": {
                "filter": [
                    {"geo_shape": {
                        "geometry": {
                            "shape": {
                                "type": "envelope",
                                "coordinates": [[min_lon, max_lat],[max_lon, min_lat]]
                            },
                            "relation": "intersects"
                        }
                    }}
                ]
            }
        },
        "_source": ["name", "geometry"]
    }

    pts = es.search(index=WAYPOINTS_INDEX, body=q_points)
    lns = es.search(index=TRACKS_INDEX,    body=q_lines)

    features: List[Dict[str, Any]] = []

    for hit in pts.get("hits", {}).get("hits", []):
        src = hit["_source"]
        features.append({
            "type": "Feature",
            "id": hit["_id"],
            "geometry": {"type": "Point", "coordinates": [src["location"]["lon"], src["location"]["lat"]]},
            "properties": {
                "name": src.get("name"),
                "kind": "wpt",
                "trailcam": src.get("trailcam"),
                "type": src.get("type"),
            }
        })

    for hit in lns.get("hits", {}).get("hits", []):
        src = hit["_source"]
        features.append({
            "type": "Feature",
            "id": hit["_id"],
            "geometry": src["geometry"],
            "properties": {"name": src.get("name"), "kind": "trk"}
        })

    return {"type": "FeatureCollection", "features": features}

@router.patch("/waypoints/{waypoint_id}")
async def update_waypoint(
    waypoint_id: str,
    request: Request,
    name: Optional[str] = Body(None),
    lat: Optional[float] = Body(None),
    lon: Optional[float] = Body(None),
    type: Optional[str] = Body(None),
    trailcam: Optional[Dict[str, Any]] = Body(None),
):
    es = es_dep(request)
    ensure_indices(es)

    doc: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if name is not None:
        doc["name"] = name
    if lat is not None and lon is not None:
        doc["location"] = {"lat": lat, "lon": lon}
    if type is not None:
        doc["type"] = type
    if trailcam is not None:
        doc["trailcam"] = trailcam
    if len(doc) == 1:
        raise HTTPException(status_code=400, detail="Nothing to update")

    es.update(index=WAYPOINTS_INDEX, id=waypoint_id, body={"doc": doc})
    try:
        await broadcast_geo_refresh()
    except Exception:
        pass

    return {"ok": True, "id": waypoint_id}

@router.get("/ws_status")
def ws_status():
    return {"connections": ws_connection_count()}
