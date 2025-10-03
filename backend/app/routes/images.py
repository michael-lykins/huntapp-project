from fastapi import APIRouter, Query
from typing import Optional, Tuple
from datetime import datetime
from opentelemetry import trace
from app.services import get_search

router = APIRouter(prefix="/images", tags=["images"])
tracer = trace.get_tracer(__name__)

def _parse_bbox(bbox: Optional[str]) -> Optional[Tuple[float, float, float, float]]:
    if not bbox:
        return None
    try:
        a, b, c, d = [float(x.strip()) for x in bbox.split(",")]
        return (a, b, c, d)
    except Exception:
        return None

@router.get("/search")
def search_images(
    q: Optional[str] = Query(None, description="Free text"),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    bbox: Optional[str] = Query(None, description="minLon,minLat,maxLon,maxLat"),
    size: int = Query(50, ge=1, le=500),
):
    s = get_search()
    bbox_t = _parse_bbox(bbox)
    with tracer.start_as_current_span("images.search"):
        items = s.query_images(
            q=q,
            start=start.isoformat() if start else None,
            end=end.isoformat() if end else None,
            bbox=bbox_t,
            size=size,
        )
    return {"count": len(items), "items": items}
