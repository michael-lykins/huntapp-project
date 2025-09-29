import datetime as dt
from typing import Dict, List, Any, Tuple
from elasticsearch.helpers import bulk
from app.es import get_search_client

def _point(lon: float, lat: float) -> Dict[str, Any]:
    return {"type": "point", "coordinates": [lon, lat]}

def _linestring(coords: List[Tuple[float, float]]) -> Dict[str, Any]:
    return {"type": "linestring", "coordinates": [[lon, lat] for lon, lat in coords]}

def ingest_gpx_bytes(data: bytes) -> Dict[str, int]:
    import gpxpy
    gpx = gpxpy.parse(data.decode("utf-8", errors="ignore"))
    es = get_search_client()
    now = dt.datetime.utcnow().isoformat() + "Z"
    w_docs: List[Dict[str, Any]] = []
    t_docs: List[Dict[str, Any]] = []

## Waypoints
    for w in gpx.waypoints:
        doc = {
            "@timestamp": (w.time or dt.datetime.utcnow()).isoformat() + "Z" if getattr(w, "time", None) else now,
            "source": "gpx",
            "name": w.name,
            "desc": w.description,
            "elev_m": float(w.elevation) if w.elevation else None,
            "geom": _point(float(w.longitude), float(w.latitude)),
        }
        w_docs.append(doc)

## Tracks and Routes    
    for trk in gpx.tracks:
        name = trk.name
        desc = trk.description
        for seg in trk.segments:
            coords = [(float(p.longitude), float(p.latitude)) for p in seg.points]
            if not coords:
                continue
            doc = {"source": "gpx", "name": name, "desc": desc, "geom": _linestring(coords)}
            t_docs.append(doc)

    for rte in gpx.routes:
        name = getattr(rte, "name", None)
        desc = getattr(rte, "description", None)
        coords = [(float(p.longitude), float(p.latitude)) for p in rte.points]
        if coords:
            t_docs.append({"source": "gpx", "name": name, "desc": desc,
                       "geom": _linestring(coords)})

    actions = []
    for d in w_docs:
        actions.append({"_op_type": "index", "_index": "hunt-geo-waypoints", "_source": d})
    for d in t_docs:
        actions.append({"_op_type": "index", "_index": "hunt-geo-tracks", "_source": d})
    if actions:
        bulk(es, actions, request_timeout=60)
    return {"waypoints": len(w_docs), "tracks": len(t_docs), "areas": 0}

def ingest_kml_bytes(data: bytes) -> Dict[str, int]:
    from fastkml import kml
    from shapely.geometry import mapping

    doc = kml.KML()
    doc.from_string(data)

    es = get_search_client()
    w_docs: List[Dict[str, Any]] = []
    t_docs: List[Dict[str, Any]] = []
    a_docs: List[Dict[str, Any]] = []

    def visit(feat):
        from fastkml.kml import Placemark, Document, Folder
        if isinstance(feat, (Document, Folder)):
            for f in feat.features():
                visit(f)
            return

        if isinstance(feat, Placemark):
            geom = feat.geometry
            if geom is None:
                return
            gj = mapping(geom)
            gtype = gj.get("type", "").lower()
            props = {
                "source": "kml",
                "name": getattr(feat, "name", None),
                "desc": getattr(feat, "description", None),
            }

            if gtype == "point":
                lon, lat, *rest = gj["coordinates"]
                w_docs.append({**props, "geom": {"type": "point", "coordinates": [lon, lat]}})

            elif gtype == "linestring":
                coords = [(lon, lat) for lon, lat, *rest in gj["coordinates"]]
                t_docs.append({**props, "geom": {"type": "linestring", "coordinates": coords}})

            elif gtype == "polygon":
                rings: List[List[Tuple[float, float]]] = []
                # gj["coordinates"] is a sequence of rings: [outer, hole1, ...]
                for ring in gj["coordinates"]:
                    ring2 = [(lon, lat) for lon, lat, *rest in ring]
                    rings.append(ring2)
                a_docs.append({**props, "geom": {"type": "polygon", "coordinates": rings}})

            # NOTE: MultiLineString / MultiPolygon can be added later if needed.

    for f in doc.features():
        visit(f)

    actions = []
    for d in w_docs:
        actions.append({"_op_type": "index", "_index": "hunt-geo-waypoints", "_source": d})
    for d in t_docs:
        actions.append({"_op_type": "index", "_index": "hunt-geo-tracks", "_source": d})
    for d in a_docs:
        actions.append({"_op_type": "index", "_index": "hunt-geo-areas", "_source": d})
    if actions:
        bulk(es, actions, request_timeout=60)

    return {"waypoints": len(w_docs), "tracks": len(t_docs), "areas": len(a_docs)}
