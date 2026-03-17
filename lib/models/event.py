from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class Event(BaseModel):
    id: Optional[str]
    timestamp: datetime
    event_type: str
    note: Optional[str] = None
    species: Optional[str] = None
    spot_id: Optional[str] = None
    geo: Optional[dict] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    color: Optional[str] = None
