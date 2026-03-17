from __future__ import annotations
from typing import Literal, Optional, Dict, Any, List
from pydantic import BaseModel, Field

ImageType = Literal["trail_camera", "cell_phone", "digital_camera"]

class ImageMeta(BaseModel):
    image_type: ImageType
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    captured_at: Optional[str] = Field(None, description="ISO8601")
    trailcam: Optional[Dict[str, Any]] = None  # model, make, sensitivity, bait, etc.

class ImageIn(BaseModel):
    meta: ImageMeta

class ImageOut(BaseModel):
    id: str
    s3_key: str
    meta: ImageMeta
    status: Literal["queued","processed","error"] = "queued"

class BulkOut(BaseModel):
    ids: List[str]
