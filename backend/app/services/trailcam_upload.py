from __future__ import annotations
import os, io, datetime as dt
from typing import Optional, Dict, Any
import boto3
from fastapi import UploadFile
import exifread

S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://minio:9000")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minioadmin")
S3_BUCKET = os.getenv("S3_BUCKET", "trailcam-images")

def _s3():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        region_name=S3_REGION,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
    )

async def save_upload_to_minio(file: UploadFile, prefix: str = "uploads", camera_id: Optional[str] = None) -> Dict[str, Any]:
    data = await file.read()
    key = f"{prefix}/{camera_id or 'unknown'}/{dt.datetime.utcnow().strftime('%Y/%m/%d')}/{file.filename}"
    s3 = _s3()
    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=data, ContentType=file.content_type or "application/octet-stream")
    image_url = f"{S3_ENDPOINT.rstrip('/')}/{S3_BUCKET}/{key}"
    return {"bucket": S3_BUCKET, "key": key, "size_bytes": len(data), "image_url": image_url}

async def extract_exif(file: UploadFile) -> Dict[str, Any]:
    # Read again fresh (caller should .seek(0))
    data = await file.read()
    tags = exifread.process_file(io.BytesIO(data), details=False)
    # Convert to plain dict[str,str]
    return {str(k): str(v) for k, v in tags.items()}

def build_payload(
    image_url: str,
    size_bytes: Optional[int],
    camera_id: Optional[str],
    lat: Optional[float],
    lon: Optional[float],
    heading_deg: Optional[float],
    label: Optional[str],
    exif: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    now = dt.datetime.utcnow().isoformat() + "Z"
    payload: Dict[str, Any] = {
        "image_url": image_url,
        "size_bytes": size_bytes,
        "camera_id": camera_id,
        "label": label,
        "lat": lat,
        "lon": lon,
        "heading_deg": heading_deg,
        "exif": exif or {},
        "ingest_ts": now,
    }
    return payload
