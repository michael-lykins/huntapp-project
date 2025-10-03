# app/routes/events.py
from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, condecimal
from opentelemetry import trace

try:
    # Prefer your shared client helper if present
    from app.es import get_search_client
    _es = get_search_client
except Exception:
    # Fallback if helper isn't available for some reason
    from elasticsearch import Elasticsearch

    def _es():
        return Elasticsearch(
            hosts=[os.environ["ELASTIC_SEARCH_HOST"]],
            api_key=os.environ["ELASTIC_SEARCH_API_KEY"],
            request_timeout=30,
        )

logger = logging.getLogger("huntapp.events")
tracer = trace.get_tracer("huntapp.events")

# In serverless, write to the data stream name, not an index-with-settings.
EVENTS_DS = os.getenv("ES_EVENTS_DATASTREAM", "hunt-events")


class PinEventIn(BaseModel):
    """Single-point event (“pin drop”)."""
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Event time (defaults to now, UTC).",
    )
    event_type: str = Field(..., description="e.g. stand|bedding|rub|scrape|access|camp|note|sighting")
    lat: condecimal(ge=-90, le=90) = Field(..., description="Latitude")
    lon: condecimal(ge=-180, le=180) = Field(..., description="Longitude")
    note: Optional[str] = Field(None, description="Optional free-form note")
    species: Optional[str] = Field(None, description="Optional species tag, e.g. deer|elk|turkey")
    spot_id: Optional[str] = Field(None, description="Optional client-side slug/id to correlate later")


class PinEventOut(BaseModel):
    id: str
    indexed: bool
    _source: dict


router = APIRouter(prefix="/events", tags=["events"])


@router.post("/pin", response_model=PinEventOut)
def create_pin_event(evt: PinEventIn):
    """
    Create a single geo_point event. Matches your serverless template:
      - @timestamp (date)
      - event_type (keyword)
      - geo (geo_point)
      - note (text)
      - species (keyword)
      - spot_id (keyword)
    """
    doc = {
        "@timestamp": evt.timestamp.isoformat(),
        "event_type": evt.event_type,
        "geo": {"lat": float(evt.lat), "lon": float(evt.lon)},
        "note": evt.note,
        "species": evt.species,
        "spot_id": evt.spot_id,
    }

    with tracer.start_as_current_span("events.create_pin") as span:
        span.set_attribute("event.type", evt.event_type)
        span.set_attribute("geo.lat", float(evt.lat))
        span.set_attribute("geo.lon", float(evt.lon))
        try:
            es = _es()
            res = es.index(index=EVENTS_DS, document=doc)
            _id = res.get("_id") or res.get("id") or ""
            ok = bool(res.get("result") in ("created", "updated") or res.get("result") is None)
            logger.info("Indexed pin event to %s id=%s", EVENTS_DS, _id)
            span.set_attribute("es.index", EVENTS_DS)
            span.set_attribute("es.id", _id)
            return PinEventOut(id=_id, indexed=ok, _source=doc)
        except Exception as e:
            logger.exception("Failed to index pin event")
            raise HTTPException(status_code=500, detail=f"Failed to index pin event: {e}")


@router.get("/search")
def search_events(
    q: Optional[str] = Query(None, description="Free text across note + event_type + species"),
    start: Optional[datetime] = Query(None, description="Start time (ISO8601)"),
    end: Optional[datetime] = Query(None, description="End time (ISO8601)"),
    bbox: Optional[str] = Query(
        None,
        description="minLon,minLat,maxLon,maxLat (e.g. -122.6,37.6,-122.2,37.9)"
    ),
    size: int = Query(100, ge=1, le=1000),
):
    """
    Search events with time range and optional map bounding box filter.
    """
    must: List[dict] = []
    filter_: List[dict] = []

    # Time range on @timestamp
    if start or end:
        rng = {}
        if start: rng["gte"] = start.isoformat()
        if end:   rng["lte"] = end.isoformat()
        filter_.append({"range": {"@timestamp": rng}})

    # BBox filter on 'geo'
    if bbox:
        try:
            min_lon, min_lat, max_lon, max_lat = [float(x.strip()) for x in bbox.split(",")]
            filter_.append({
                "geo_bounding_box": {"geo": {
                    "top_left":     {"lat": max_lat, "lon": min_lon},
                    "bottom_right": {"lat": min_lat, "lon": max_lon}
                }}
            })
        except Exception:
            # Ignore bad bbox; alternatively, you could raise 422
            pass

    # Text query across note (text), event_type (keyword), species (keyword)
    if q:
        must.append({
            "simple_query_string": {
                "query": q,
                "fields": ["note^2", "event_type", "species"]
            }
        })

    body = {
        "query": {"bool": {"must": must, "filter": filter_}},
        "size": size,
        "sort": [{"@timestamp": "desc"}],
    }

    with tracer.start_as_current_span("events.search") as span:
        span.set_attribute("search.size", size)
        try:
            es = _es()
            res = es.search(index=EVENTS_DS, body=body)
            hits = [
                {
                    "id": h.get("_id"),
                    **h.get("_source", {}),
                }
                for h in res.get("hits", {}).get("hits", [])
            ]
            return {"count": len(hits), "items": hits}
        except Exception as e:
            logger.exception("Search failed")
            raise HTTPException(status_code=500, detail=f"Search failed: {e}")


@router.get("/{event_id}")
def get_event(event_id: str):
    """
    Fetch a single event by ID.
    """
    with tracer.start_as_current_span("events.get"):
        try:
            es = _es()
            res = es.get(index=EVENTS_DS, id=event_id)
            if not res.get("found"):
                raise HTTPException(status_code=404, detail="Not found")
            return {"id": res.get("_id"), **res.get("_source", {})}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Fetch failed: {e}")
