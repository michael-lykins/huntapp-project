import os, io, uuid
from typing import Dict, Any
import exifread
import boto3
from botocore.client import Config

S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://minio:9000")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minioadmin")
S3_BUCKET = os.getenv("S3_BUCKET", "trailcam-images")

_s3 = boto3.client(
    "s3",
    region_name=S3_REGION,
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    config=Config(signature_version="s3v4"),
)

def _presign(key: str, expires: int = 3600) -> str:
    return _s3.generate_presigned_url("get_object", Params={"Bucket": S3_BUCKET, "Key": key}, ExpiresIn=expires)

async def handle_trailcam_upload(camera_id: str, file) -> Dict[str, Any]:
    data = await file.read()
    size = len(data)
    exif = {}
    try:
        tags = exifread.process_file(io.BytesIO(data), details=False)
        exif = {str(k): str(v) for k, v in tags.items()}
    except Exception:
        pass

    ext = os.path.splitext(file.filename or "")[1].lower() or ".jpg"
    key = f"{camera_id}/{uuid.uuid4().hex}{ext}"
    _s3.put_object(Bucket=S3_BUCKET, Key=key, Body=data, ContentType=file.content_type or "application/octet-stream")

    return {"bucket": S3_BUCKET, "object_key": key, "size_bytes": size, "image_url": _presign(key), "exif": exif}
