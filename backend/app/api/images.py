from __future__ import annotations
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Literal, Dict, Any
from datetime import datetime
import io, json, time
from redis import Redis
from rq import Queue
import boto3
from lib.images.io import sha256_bytes, get_boto_session, put_s3_bytes
from os import getenv
from uuid import uuid4

router = APIRouter(prefix="/v1/images", tags=["images"])

ImageSource = Literal["trail_camera","cell_phone","digital_camera"]

class TrailMeta(BaseModel):
    camera_id: Optional[str] = None
    manufacturer: Optional[str] = None
    temperature_c: Optional[float] = None
    moon_phase: Optional[str] = None
    trigger: Optional[str] = None
    exposure: Optional[str] = None

class ImageMeta(BaseModel):
    source_type: ImageSource
    timestamp: Optional[datetime] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    trail: Optional[TrailMeta] = None

def _queue() -> Queue:
    r = Redis(host="redis", port=6379)
    return Queue("images", connection=r)

def _boto():
    sess, kw = get_boto_session(
        endpoint=getenv("S3_ENDPOINT", ""),
        region=getenv("S3_REGION", "us-east-1"),
        access_key=getenv("S3_ACCESS_KEY", ""),
        secret_key=getenv("S3_SECRET_KEY", ""),
    )
    return sess, kw, getenv("S3_BUCKET", "trailcam-images")

def _es():
    return getenv("ELASTIC_SEARCH_HOST"), getenv("ELASTIC_SEARCH_API_KEY")

@router.post("", summary="Upload a single image")
async def upload_one(
    file: UploadFile = File(...),
    meta_json: Optional[str] = Form(None)
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "file must be an image/*")
    raw = await file.read()
    sha = sha256_bytes(raw)
    image_id = str(uuid4())

    meta = ImageMeta.model_validate_json(meta_json) if meta_json else ImageMeta(source_type="digital_camera")
    doc = {
        "image_id": image_id,
        "sha256": sha,
        "s3_key": f"images/{time.strftime('%Y/%m/%d')}/{image_id}.jpg",
        "source_type": meta.source_type,
    }
    if meta.timestamp: doc["timestamp"] = meta.timestamp.isoformat()
    if meta.lat is not None and meta.lon is not None:
        doc["gps"] = {"lat": meta.lat, "lon": meta.lon}
    if meta.camera_make:  doc["camera_make"] = meta.camera_make
    if meta.camera_model: doc["camera_model"] = meta.camera_model
    if meta.trail: doc["trail"] = meta.trail.model_dump(exclude_none=True)

    sess, kw, bucket = _boto()
    put_s3_bytes(session=sess, bucket=bucket, key=doc["s3_key"], data=raw, content_type=file.content_type)

    es_url, es_api_key = _es()
    # enqueue worker job
    queue = _queue()
    job = queue.enqueue(
        "worker_app.jobs.images.process_and_index_image",
        es_url=es_url, es_api_key=es_api_key, doc=doc, raw=raw,
        job_timeout=600
    )
    return {"image_id": image_id, "enqueued": True, "job_id": job.id}

@router.post("/bulk", summary="Upload multiple images")
async def upload_bulk(
    files: List[UploadFile] = File(...),
    default_meta_json: Optional[str] = Form(None)
):
    meta = ImageMeta.model_validate_json(default_meta_json) if default_meta_json else None
    sess, kw, bucket = _boto()
    es_url, es_api_key = _es()
    queue = _queue()

    results = []
    for f in files:
        if not f.content_type or not f.content_type.startswith("image/"):
            continue
        raw = await f.read()
        sha = sha256_bytes(raw)
        image_id = str(uuid4())
        doc = {
            "image_id": image_id,
            "sha256": sha,
            "s3_key": f"images/{time.strftime('%Y/%m/%d')}/{image_id}.jpg",
            "source_type": meta.source_type if meta else "digital_camera",
        }
        if meta:
            if meta.timestamp: doc["timestamp"] = meta.timestamp.isoformat()
            if meta.lat is not None and meta.lon is not None:
                doc["gps"] = {"lat": meta.lat, "lon": meta.lon}
            if meta.camera_make:  doc["camera_make"] = meta.camera_make
            if meta.camera_model: doc["camera_model"] = meta.camera_model
            if meta.trail: doc["trail"] = meta.trail.model_dump(exclude_none=True)

        put_s3_bytes(session=sess, bucket=bucket, key=doc["s3_key"], data=raw, content_type=f.content_type)
        job = queue.enqueue(
            "worker_app.jobs.images.process_and_index_image",
            es_url=es_url, es_api_key=es_api_key, doc=doc, raw=raw,
            job_timeout=600
        )
        results.append({"image_id": image_id, "job_id": job.id})
    return {"accepted": len(results), "items": results}
