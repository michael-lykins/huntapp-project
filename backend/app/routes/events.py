# backend/app/routes/events.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from app.services import get_search

router = APIRouter(prefix="/events", tags=["events"])

class PinEventIn(BaseModel):
    lon: float = Field(..., description="Longitude (decimal degrees)")
    lat: float = Field(..., description="Latitude (decimal degrees)")
    species: Optional[str] = None
    note: Optional[str] = None
    spot_id: Optional[str] = None
    event_type: str = "pin"

@router.post("/pin")
def create_pin_event(body: PinEventIn):
    s = get_search()
    try:
        # Provider-agnostic call: the search service decides how to index
        res = s.index_event_pin(
            lon=body.lon,
            lat=body.lat,
            species=body.species,
            note=body.note,
            spot_id=body.spot_id,
            event_type=body.event_type,
        )
        return {"ok": True, "result": getattr(res, "result", None) or res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to index pin event: {e}")
