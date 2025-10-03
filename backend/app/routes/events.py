# backend/app/routes/events.py
from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import os

from opentelemetry import trace

# Import your "search" client factory (keeps code vendor-agnostic here)
# If your project exposes get_search_client() in app.es, keep it.
try:
    from app.es import get_search_client  # existing helper you already use
except Exception:
    get_search_client = None  # if you later swap it for another adapter

router = APIRouter(prefix="/events", tags=["events"])
tracer = trace.get_tracer(__name__)

# Allow overriding the target index/data stream name from env
EVENTS_INDEX = os.getenv("EVENTS_INDEX", "hunt-events")

class PinEvent(BaseModel):
    # keep these as floats so FastAPI validation returns clean 422s when bad
    lat: float = Field(..., description="Latitude")
    lon: float = Field(..., description="Longitude")
    event_type: str = Field(..., min_length=1, description="e.g. stand, bedding, rub, scrape, access, camp")
    note: Optional[str] = None
    species: Optional[str] = None
    spot_id: Optional[str] = None
    ts: Optional[datetime] = Field(None, description="Optional custom timestamp")

@router.post("/pin")
def create_pin(evt: PinEvent):
    """
    Create a point event. We send a vendor-agnostic document:
      - '@timestamp'
      - 'event_type', 'note', 'species', 'spot_id'
      - 'geo': { 'lat', 'lon' }   <-- single geo object (your template maps this as geo_point)
    Any pipeline or serverless-specific transforms remain on the Elastic side.
    """
    if get_search_client is None:
        raise HTTPException(500, detail="Search client not configured")

    doc = {
        "@timestamp": (evt.ts or datetime.now(timezone.utc)).isoformat(),
        "event_type": evt.event_type,
        "note": evt.note,
        "species": evt.species,
        "spot_id": evt.spot_id,
        "geo": {"lat": evt.lat, "lon": evt.lon},
    }

    try:
        with tracer.start_as_current_span("es.index.event.pin"):
            es = get_search_client()
            # For serverless data streams, this name is usually just the data stream name.
            res = es.index(index=EVENTS_INDEX, document=doc)
        return {"ok": True, "id": res.get("_id"), "result": res.get("result")}
    except Exception as e:
        # Keep the app agnostic and bubble a clear error
        raise HTTPException(status_code=400, detail=f"Failed to index pin event: {e}")
