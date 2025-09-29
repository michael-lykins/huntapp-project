from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional, Dict, Any
import datetime as dt
from app.services.trailcam_upload import handle_trailcam_upload
from app.worker import enqueue_image_job

router = APIRouter()

@router.post("/upload")
async def upload_image(
    camera_id: str = Form(...),
    file: UploadFile = File(None),
    image: UploadFile = File(None),
    heading_deg: Optional[float] = Form(None),
    lat: Optional[float] = Form(None),
    lon: Optional[float] = Form(None),
    label: Optional[str] = Form(None),
) -> Dict[str, Any]:
    the_file = file or image
    if the_file is None:
        raise HTTPException(status_code=400, detail="No file provided (expected 'file' or 'image').")
    result = await handle_trailcam_upload(camera_id=camera_id, file=the_file)
    payload = {
        "camera_id": camera_id,
        "image_url": result.get("image_url"),
        "size_bytes": result.get("size_bytes"),
        "exif": result.get("exif", {}),
        "lat": lat,
        "lon": lon,
        "heading_deg": heading_deg,
        "label": label,
        "ingest_ts": dt.datetime.utcnow().isoformat() + "Z",
    }
    job_id = enqueue_image_job(payload)
    return {"ok": True, **result, "index_job_id": job_id}
