# backend/app/routes/images.py
from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime
from opentelemetry import trace

from app.services import get_search

router = APIRouter(prefix="/images", tags=["images"])
tracer = trace.get_tracer(__name__)


@router.get("/search")
def search_images(
    q: Optional[str] = Query(None, description="free text"),
    start: Optional[datetime] = Query(None, description="ISO start"),
    end: Optional[datetime] = Query(None, description="ISO end"),
    bbox: Optional[str] = Query(
        None,
        description="minLon,minLat,maxLon,maxLat (e.g. -122.6,37.6,-122.2,37.9)"
    ),
    size: int = Query(50, ge=1, le=500),
):
    """
    Vendor-agnostic search across trailcam images.
    Delegates to Search adapter (Elastic implementation stays in services/search_elastic.py).
    """
    with tracer.start_as_current_span("images.search"):
        search = get_search()

        # normalize bbox if present
        parsed_bbox = None
        if bbox:
            try:
                min_lon, min_lat, max_lon, max_lat = [float(x.strip()) for x in bbox.split(",")]
                parsed_bbox = (min_lon, min_lat, max_lon, max_lat)
            except Exception:
                # silently ignore bad bbox; you can 422 if you prefer
                parsed_bbox = None

        result = search.query_images(
            q=q,
            start=start.isoformat() if start else None,
            end=end.isoformat() if end else None,
            bbox=parsed_bbox,
            size=size,
        )
        return result
