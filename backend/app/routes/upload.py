from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from datetime import datetime
from opentelemetry import trace
from app.services import get_blob
from app.worker import enqueue_image_job  # uses queue + search adapter inside worker

router = APIRouter(prefix="/upload", tags=["upload"])
tracer = trace.get_tracer(__name__)

@router.post("/trailcam")
async def upload_trailcam(
    image: UploadFile = File(...),
    camera_id: str = Form(...),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    heading_deg: float | None = Form(None),
    label: str | None = Form(None),
):
    now = datetime.utcnow()
    key = f"uploads/{camera_id}/{now:%Y/%m/%d}/{image.filename}"
    try:
        blob = get_blob()
        data = await image.read()
        blob.put(key, data, image.content_type or "image/jpeg")
        image_url = blob.public_url(key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store image: {e}")

    payload = {
        "ingest_ts": now.isoformat() + "Z",
        "camera_id": camera_id,
        "lat": float(lat) if lat is not None else None,
        "lon": float(lon) if lon is not None else None,
        "heading_deg": float(heading_deg) if heading_deg is not None else None,
        "label": label,
        "image_url": image_url,
        "size_bytes": len(data),
        "exif": {},  # (optional) fill if you parse EXIF
    }
    job_id = enqueue_image_job(payload)
    return {"ok": True, "job_id": job_id, "image_url": image_url}
