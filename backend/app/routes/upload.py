# backend/app/routes/upload.py
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional
from uuid import uuid4
from datetime import datetime
import os
from urllib.parse import urljoin

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from opentelemetry import trace, propagate

# If you have enqueue_image_job in app.worker, import it; otherwise comment out that part
try:
    from app.worker import enqueue_image_job
except Exception:
    enqueue_image_job = None

router = APIRouter(prefix="/upload", tags=["upload"])
tracer = trace.get_tracer(__name__)

# ---- S3/MinIO config ----
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://minio:9000")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minioadmin")
S3_BUCKET = os.getenv("S3_BUCKET", "trailcam-images")

# Public base to hand back to clients (browser). Defaults to localhost:9000 for dev.
PUBLIC_BASE = os.getenv("S3_PUBLIC_URL", "http://localhost:9000").rstrip("/")

def _s3_client():
    # path-style + v4 signing is friendly to MinIO and AWS
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        region_name=S3_REGION,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )

def _ensure_bucket_exists(s3):
    try:
        s3.head_bucket(Bucket=S3_BUCKET)
        return
    except ClientError as e:
        code = str(e.response.get("Error", {}).get("Code"))
        if code not in ("404", "NoSuchBucket", "NotFound"):
            # Other errors: auth, network, etc.
            raise

    # Create if missing. MinIO accepts CreateBucket without LocationConstraint.
    try:
        if S3_REGION and S3_REGION.lower() != "us-east-1":
            s3.create_bucket(
                Bucket=S3_BUCKET,
                CreateBucketConfiguration={"LocationConstraint": S3_REGION},
            )
        else:
            s3.create_bucket(Bucket=S3_BUCKET)
    except ClientError as e:
        # Another writer may have created it first; ignore bucket-exists races
        code = str(e.response.get("Error", {}).get("Code"))
        if code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            raise

def _public_url(bucket: str, key: str) -> str:
    # Return a browser-friendly URL (e.g., http://localhost:9000/trailcam-images/...)
    return f"{PUBLIC_BASE}/{bucket}/{key}"

@router.post("/trailcam")
async def upload_trailcam_image(
    image: UploadFile = File(...),
    camera_id: str = Form(...),
    lat: Optional[float] = Form(None),
    lon: Optional[float] = Form(None),
    heading_deg: Optional[float] = Form(None),
    label: Optional[str] = Form(None),
):
    """
    Stores the image to S3/MinIO and (optionally) enqueues a background job
    to index metadata in your search cluster.
    """
    with tracer.start_as_current_span("upload.trailcam") as span:
        # Read file into memory (for larger uploads, stream to S3 using upload_fileobj)
        data = await image.read()
        if not data:
            raise HTTPException(status_code=400, detail="Empty upload")

        # Build a stable key
        now = datetime.utcnow()
        fname = image.filename or "upload.jpg"
        # Append short uuid to avoid collisions
        name, dot, ext = fname.rpartition(".")
        ext = (dot + ext) if dot else ""
        key = f"uploads/{camera_id}/{now:%Y/%m/%d}/{(name or 'image')}-{uuid4().hex[:12]}{ext}"

        s3 = _s3_client()
        try:
            _ensure_bucket_exists(s3)
            s3.put_object(
                Bucket=S3_BUCKET,
                Key=key,
                Body=data,
                ContentType=image.content_type or "application/octet-stream",
            )
        except ClientError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to store image: {e.response.get('Error', {}).get('Message', str(e))}",
            )

        image_url = _public_url(S3_BUCKET, key)

        # Build payload for the worker (if you’re indexing to Elasticsearch or elsewhere)
        payload = {
            "camera_id": camera_id,
            "image_url": image_url,
            "width": None,   # populate in worker if you parse EXIF
            "height": None,
            "lat": lat,
            "lon": lon,
            "heading_deg": heading_deg,
            "label": label,
        }

        # Inject parent trace context so worker spans are linked
        carrier = {}
        propagate.inject(carrier)
        payload["otel"] = carrier

        job_id = None
        if enqueue_image_job:
            try:
                job_id = enqueue_image_job(payload)
            except Exception:
                # Don't fail the upload if background queue is temporarily unavailable
                pass

        return {"ok": True, "job_id": job_id, "image_url": image_url}
