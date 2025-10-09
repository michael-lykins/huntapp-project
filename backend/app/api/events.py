import os

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from lib.models.event import Event
from lib.services.elastic_client import get_elasticsearch_client
from lib.search.events_bootstrap import EVENTS_DATA_STREAM

router = APIRouter(prefix="/api/events", tags=["events"])

class PinCreate(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    note: Optional[str] = None
    species: Optional[str] = None
    spot_id: Optional[str] = None
    color: Optional[str] = None
    glyph: Optional[str] = None
    category: Optional[str] = None

class PinOut(BaseModel):
    result: str
    id: str

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _flatten_hit(hit: Dict[str, Any]) -> Dict[str, Any]:
    src = hit.get("_source", {}) or {}
    return {
        "id": hit.get("_id"),
        "timestamp": src.get("@timestamp"),
        "lat": src.get("geo", {}).get("lat"),
        "lon": src.get("geo", {}).get("lon"),
        "note": src.get("note"),
        "species": src.get("species"),
        "spot_id": src.get("spot_id"),
        "color": src.get("color"),
        "glyph": src.get("glyph"),
        "category": src.get("category"),
    }

@router.get("", response_model=List[Dict[str, Any]])
async def get_all(limit: int = 1000):
    search = get_search()
    result = search.search(index=EVENTS_DATA_STREAM, size=limit, sort="@timestamp:desc")
    hits = result.get("hits", {}).get("hits", [])
    return [_flatten_hit(h) for h in hits]

@router.post("", response_model=PinOut, status_code=status.HTTP_201_CREATED)
async def create_pin(body: PinCreate):
    es = get_search_client()
    doc = body.dict()
    doc["@timestamp"] = _utcnow_iso()
    doc["geo"] = {"lat": doc.pop("lat"), "lon": doc.pop("lon")}
    resp = es.index(index=EVENTS_DATA_STREAM, document=doc)
    return PinOut(result=resp.get("result", ""), id=resp.get("_id", ""))