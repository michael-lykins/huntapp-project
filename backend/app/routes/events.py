from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from app.services import get_search

router = APIRouter(prefix="/events", tags=["events"])
EVENTS_INDEX = "hunt-events"  # ES template/pipeline configured on the Elastic side


class PinIn(BaseModel):
    lat: float = Field(..., description="Latitude")
    lon: float = Field(..., description="Longitude")
    event_type: str = Field(..., description="Type of event, e.g. stand/scrape/etc")
    note: Optional[str] = None
    species: Optional[str] = None
    spot_id: Optional[str] = None


def build_pin_document(p: PinIn) -> Dict[str, Any]:
    return {
        "@timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": p.event_type,
        "note": p.note,
        "species": p.species,
        "spot_id": p.spot_id,
        # vendor-agnostic fields; ES pipeline can turn these into geo_point
        "lat": float(p.lat),
        "lon": float(p.lon),
    }


@router.post("/_debug/payload")
def debug_payload(p: PinIn):
    return build_pin_document(p)


@router.post("/pin")
def create_pin(p: PinIn):
    doc = build_pin_document(p)
    svc = get_search()
    try:
        res = svc.index(EVENTS_INDEX, doc)  # <-- IMPORTANT: .index(...)
        return {
            "ok": True,
            "result": res.get("result"),
            "index": res.get("_index"),
            "id": res.get("_id"),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to index pin event: {e!r}")
