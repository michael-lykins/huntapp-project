# lib/services/storage.py
from __future__ import annotations
import os, uuid, datetime as dt
import boto3
from typing import BinaryIO

def _client():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT") or None,
        aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
        region_name=os.getenv("S3_REGION", "us-east-1"),
    )

def make_key(filename: str, prefix: str = "uploads") -> str:
    ext = (filename.rsplit(".",1)[-1] or "bin").lower()
    today = dt.datetime.utcnow().strftime("%Y/%m/%d")
    return f"{prefix}/{today}/{uuid.uuid4().hex}.{ext}"

def put_object(fileobj: BinaryIO, key: str, content_type: str | None = None) -> str:
    bucket = os.environ["S3_BUCKET"]
    s3 = _client()
    extra = {"ContentType": content_type} if content_type else {}
    s3.upload_fileobj(Fileobj=fileobj, Bucket=bucket, Key=key, ExtraArgs=extra or None)
    return key

def object_url(key: str) -> str:
    endpoint = os.getenv("S3_ENDPOINT")
    bucket = os.environ["S3_BUCKET"]
    if endpoint:
        # MinIO/local style URL
        return f"{endpoint.rstrip('/')}/{bucket}/{key}"
    # AWS virtual hosted–style (works in most regions with public bucket/policy)
    region = os.getenv("S3_REGION","us-east-1")
    return f"https://{bucket}.s3.{region}.amazonaws.com/{key}"
