from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import Dict
from app.services.gpx_kml_ingest import ingest_gpx_bytes, ingest_kml_bytes

router = APIRouter()

@router.post("/upload/geo")
async def upload_geo(file: UploadFile = File(...)) -> Dict:
    name = (file.filename or "").lower()
    data = await file.read()
    try:
        if name.endswith(".gpx") or b"<gpx" in data[:200].lower():
            counts = ingest_gpx_bytes(data)
        elif name.endswith(".kml") or b"<kml" in data[:200].lower():
            counts = ingest_kml_bytes(data)
        else:
            raise ValueError(f"Unsupported file type: {name}")
        return {"ok": True, "counts": counts}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
