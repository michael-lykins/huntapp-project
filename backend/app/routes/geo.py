from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.services import get_search

router = APIRouter(prefix="/geo", tags=["geo"])

class PinIn(BaseModel):
    timestamp: Optional[datetime] = Field(default=None, description="Defaults to now() if omitted")
    event_type: str = Field(default="pin")
    lat: float
    lon: float
    note: Optional[str] = None
    species: Optional[str] = None
    spot_id: Optional[str] = None

@router.post("/pin")
def create_pin(pin: PinIn):
    doc = {
        "@timestamp": (pin.timestamp or datetime.utcnow()).isoformat() + "Z",
        "event_type": pin.event_type,
        "lat": pin.lat,
        "lon": pin.lon,
        "note": pin.note,
        "species": pin.species,
        "spot_id": pin.spot_id,
    }
    res = get_search().index_event_pin(doc)
    return {"ok": True, "id": res.get("_id")}
