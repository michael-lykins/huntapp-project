from __future__ import annotations
import os
import uuid
import re
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from botocore.config import Config

import boto3
import botocore
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    UploadFile,
    HTTPException,
    Request,
    Query,
)
from elasticsearch import Elasticsearch
import redis.asyncio as aioredis

from lib.search.images_index import (
    ensure_index,
    build_doc,
    index_one,
    index_bulk,
    fetch_one,
    fetch_ids,
    search_similar_by_embedding,
)
from lib.images.exif import extract as extract_exif
from app.api.waypoints import FAKE_WAYPOINTS
from lib.services.geo import nearest_waypoint  # uses haversine in your repo

router = APIRouter(tags=["images"])

# ---- filename timestamp inference -------------------------------------------
_TS_PATTERNS = [
    # 1) MMDDYYYYhhmmss (Reveal-like): e.g. 10092025002135
    (re.compile(r"(?P<mm>\d{2})(?P<dd>\d{2})(?P<yyyy>\d{4})(?P<hh>\d{2})(?P<mi>\d{2})(?P<ss>\d{2})"), "%m%d%Y%H%M%S"),
    # 2) YYYYMMDDhhmmss with optional separator between date/time
    (re.compile(r"(?P<yyyy>\d{4})(?P<mm>\d{2})(?P<dd>\d{2})[^0-9]?(?P<hh>\d{2})(?P<mi>\d{2})(?P<ss>\d{2})"), "%Y%m%d%H%M%S"),
    # 3) YYYY-MM-DD_hh-mm-ss or similar separators
    (re.compile(r"(?P<yyyy>\d{4})[-_](?P<mm>\d{2})[-_](?P<dd>\d{2})[ T_-](?P<hh>\d{2})[-_:]?(?P<mi>\d{2})[-_:]?(?P<ss>\d{2})"), "%Y%m%d%H%M%S"),
]

def _infer_timestamp_from_name(name: str) -> Optional[str]:
    """
    Parse timestamps from common camera filename patterns by scanning all 14-digit windows.
    Returns ISO8601Z if a reasonable timestamp (year 2000..2035) is found.
    """
    digits = re.sub(r"\D", "", name or "")
    n = len(digits)
    for i in range(0, max(0, n - 13)):
        chunk = digits[i:i+14]
        # Try MMDDYYYYhhmmss
        try:
            mm = int(chunk[0:2]); dd = int(chunk[2:4]); yyyy = int(chunk[4:8])
            hh = int(chunk[8:10]); mi = int(chunk[10:12]); ss = int(chunk[12:14])
            dt = datetime(yyyy, mm, dd, hh, mi, ss, tzinfo=timezone.utc)
            if 2000 <= yyyy <= 2035:
                return dt.isoformat().replace("+00:00", "Z")
        except Exception:
            pass
        # Try YYYYMMDDhhmmss
        try:
            yyyy = int(chunk[0:4]); mm = int(chunk[4:6]); dd = int(chunk[6:8])
            hh = int(chunk[8:10]); mi = int(chunk[10:12]); ss = int(chunk[12:14])
            dt = datetime(yyyy, mm, dd, hh, mi, ss, tzinfo=timezone.utc)
            if 2000 <= yyyy <= 2035:
                return dt.isoformat().replace("+00:00", "Z")
        except Exception:
            pass
    return None

# ---- Storage / URL settings (env-driven) ------------------------------------
S3_BUCKET = os.getenv("S3_BUCKET", "trailcam-images")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
S3_ENDPOINT = os.getenv("S3_ENDPOINT")  # e.g., http://minio:9000 for local
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY")
PUBLIC_BASE = os.getenv("S3_PUBLIC_BASE")  # e.g., https://cdn.example.com or https://cdn.example.com/{bucket}
AUTO_CREATE_BUCKET = os.getenv("S3_AUTO_CREATE_BUCKET", "true").lower() in ("1", "true", "yes")

def s3_client():
    # MinIO wants path-style: http://minio:9000/bucket/key (NOT bucket.minio:9000/key)
    cfg = Config(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
        retries={"max_attempts": 5, "mode": "standard"},
    )
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT") or None,   # e.g., http://minio:9000
        aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
        region_name=os.getenv("S3_REGION") or "us-east-1",
        config=cfg,
    )

def _ensure_bucket(cli) -> None:
    if not AUTO_CREATE_BUCKET:
        return
    try:
        cli.head_bucket(Bucket=S3_BUCKET)  # exists → return
        return
    except botocore.exceptions.ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code", "")
        if str(code) not in ("404", "NoSuchBucket", "NotFound"):
            return  # permission/etc: don't spam traces
    try:
        if S3_ENDPOINT:  # MinIO/local
            cli.create_bucket(Bucket=S3_BUCKET)
        else:
            if S3_REGION and S3_REGION != "us-east-1":
                cli.create_bucket(
                    Bucket=S3_BUCKET,
                    CreateBucketConfiguration={"LocationConstraint": S3_REGION},
                )
            else:
                cli.create_bucket(Bucket=S3_BUCKET)
    except botocore.exceptions.ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code", "")
        if code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            raise

def build_public_url(bucket: str, key: str) -> Optional[str]:
    """
    Build a public URL based on S3_PUBLIC_BASE.

    Accepted forms:
      1) https://cdn.example.com
         -> https://cdn.example.com/{bucket}/{key}
      2) https://cdn.example.com/trailcam-images
         -> https://cdn.example.com/trailcam-images/{key}
      3) https://cdn.example.com/{bucket}
         -> https://cdn.example.com/trailcam-images/{key}
    """
    if not PUBLIC_BASE:
        return None
    base = PUBLIC_BASE.rstrip("/")
    if "{bucket}" in base:
        return f"{base.replace('{bucket}', bucket)}/{key}"
    last_segment = base.rsplit("/", 1)[-1]
    if last_segment == bucket:
        return f"{base}/{key}"
    return f"{base}/{bucket}/{key}"

# ---- ES dependency -----------------------------------------------------------
def es_dep(request: Request) -> Elasticsearch:
    es: Optional[Elasticsearch] = getattr(request.app.state, "es", None)
    if es is None:
        raise HTTPException(status_code=503, detail="Elasticsearch not initialized")
    return es

# ---- helpers ----------------------------------------------------------------
def _guess_ext(name: str) -> str:
    n = (name or "").lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"):
        if n.endswith(ext):
            return ext
    return ".jpg"

# ---- Redis publish helper ----------------------------------------------------
async def publish_image_uploaded(image_url: Optional[str], doc_id: str, index_name: str, bucket: str, key: str) -> None:
    """
    Publish an event so the worker can fetch the image, analyze, and update ES.
    Includes both URL and bucket/key for robustness (URL may be private).
    """
    channel = os.getenv("IMAGE_UPLOADED_CHANNEL", "image_uploaded")
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    payload = {"image_url": image_url, "doc_id": doc_id, "index": index_name, "bucket": bucket, "key": key}
    r = await aioredis.from_url(redis_url)
    try:
        await r.publish(channel, json.dumps(payload))
    finally:
        await r.close()

# =============================================================================
# API endpoints
# =============================================================================

@router.post("/images")
async def upload_image(
    request: Request,
    es: Elasticsearch = Depends(es_dep),
    file: UploadFile = File(...),
    image_type: str = Form(...),  # "trailcam" | "cellphone" | "digital"
    captured_at: Optional[str] = Form(None),   # optional; EXIF/filename may override
    # Camera-inherited location (when selecting a saved camera in UI)
    lat: Optional[float] = Form(None),
    lon: Optional[float] = Form(None),
    trailcam_camera_make: Optional[str] = Form(None),
    trailcam_camera_model: Optional[str] = Form(None),
    trailcam_name: Optional[str] = Form(None),
    trailcam_description: Optional[str] = Form(None),
    trailcam_id: Optional[str] = Form(None),
    # NEW: waypoint behavior
    override_waypoint_id: Optional[str] = Form(None),
    auto_attach: Optional[bool] = Form(True),
    attach_threshold_meters: Optional[float] = Form(50.0),
):
    index_name = ensure_index(es)

    cli = s3_client()
    _ensure_bucket(cli)

    content = await file.read()

    # Prefer EXIF, then filename, then provided form field
    exif = extract_exif(content) if "image" in (file.content_type or "") else {}
    cap_exif = exif.get("captured_at")
    cap_name = _infer_timestamp_from_name(file.filename or "")
    cap = cap_exif or cap_name or captured_at

    # Compute image coordinates: camera lat/lon wins, else EXIF GPS
    img_lat, img_lon = None, None
    if lat is not None and lon is not None:
        img_lat, img_lon = lat, lon
    else:
        gps = exif.get("gps") or {}
        if gps.get("lat") is not None and gps.get("lon") is not None:
            img_lat, img_lon = gps["lat"], gps["lon"]

    # Resolve waypoint (override > nearest-within-threshold > none)
    waypoint_doc, distance_m = None, None
    if override_waypoint_id:
        waypoint_doc = next((w for w in FAKE_WAYPOINTS if w["id"] == override_waypoint_id), None)
    elif (auto_attach is True) and (img_lat is not None and img_lon is not None):
        waypoint_doc, distance_m = nearest_waypoint(
            img_lat, img_lon, FAKE_WAYPOINTS, max_m=float(attach_threshold_meters or 50.0)
        )

    _id = uuid.uuid4().hex
    key = f"{_id}{_guess_ext(file.filename)}"

    try:
        cli.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=content,
            ContentType=file.content_type or "application/octet-stream",
        )
    except botocore.exceptions.ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in ("NoSuchBucket", "404") and AUTO_CREATE_BUCKET:
            _ensure_bucket(cli)
            cli.put_object(
                Bucket=S3_BUCKET,
                Key=key,
                Body=content,
                ContentType=file.content_type or "application/octet-stream",
            )
        else:
            raise HTTPException(status_code=500, detail=f"S3 upload failed: {e}")

    url = build_public_url(S3_BUCKET, key)

    meta: Dict[str, Any] = {
        "id": _id,
        "bucket": S3_BUCKET,
        "key": key,
        "url": url,
        "content_type": file.content_type,
        "size_bytes": len(content),
        "image_type": image_type,
        "captured_at": cap,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "geo": {"lat": img_lat, "lon": img_lon} if (img_lat is not None and img_lon is not None) else None,
        "trailcam": (
            {
                "camera_make": trailcam_camera_make,
                "camera_model": trailcam_camera_model,
                "name": trailcam_name,
                "id": trailcam_id,
                "description": trailcam_description,
            }
            if image_type == "trailcam" else None
        ),
        # NEW: nearest waypoint result (waypoint_id for cascade delete)
        "waypoint": waypoint_doc,
        "waypoint_id": waypoint_doc["id"] if waypoint_doc else None,
        "distance_to_waypoint_m": distance_m,
    }

    doc = build_doc(meta=meta, exif=exif, extra={})
    es_id = index_one(es, doc)

    # Enqueue analysis for worker (non-blocking for the API)
    await publish_image_uploaded(url, es_id, index_name, S3_BUCKET, key)

    # NEW: return attachment summary for the UI
    return {
        "ok": True,
        "indexed_id": es_id,
        "bucket": S3_BUCKET,
        "key": key,
        "url": url,
        "attached": [{
            "filename": file.filename,
            "waypoint": waypoint_doc,
            "distance_m": distance_m,
            "exif": (exif.get("gps") or None)
        }],
    }

@router.post("/images:batch")
async def upload_images_batch(
    request: Request,
    es: Elasticsearch = Depends(es_dep),
    files: List[UploadFile] = File(...),
    image_type: str = Form(...),               # shared across all files
    captured_at: Optional[str] = Form(None),   # shared default (EXIF/filename override)
    # Camera-inherited location (shared default if provided)
    lat: Optional[float] = Form(None),
    lon: Optional[float] = Form(None),
    trailcam_camera_make: Optional[str] = Form(None),
    trailcam_camera_model: Optional[str] = Form(None),
    # NEW (shared behavior for the batch)
    override_waypoint_id: Optional[str] = Form(None),
    auto_attach: Optional[bool] = Form(True),
    attach_threshold_meters: Optional[float] = Form(50.0),
    continue_on_error: bool = Form(True),
):
    index_name = ensure_index(es)
    cli = s3_client()
    _ensure_bucket(cli)

    docs: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    to_publish: List[Dict[str, str]] = []
    attached_summary: List[Dict[str, Any]] = []

    for f in files:
        try:
            content = await f.read()
            exif = extract_exif(content) if "image" in (f.content_type or "") else {}
            cap = exif.get("captured_at") or _infer_timestamp_from_name(f.filename or "") or captured_at

            # Compute per-file coords (inherit provided lat/lon, else EXIF)
            img_lat, img_lon = None, None
            if lat is not None and lon is not None:
                img_lat, img_lon = lat, lon
            else:
                gps = exif.get("gps") or {}
                if gps.get("lat") is not None and gps.get("lon") is not None:
                    img_lat, img_lon = gps["lat"], gps["lon"]

            # Resolve waypoint
            waypoint_doc, distance_m = None, None
            if override_waypoint_id:
                waypoint_doc = next((w for w in FAKE_WAYPOINTS if w["id"] == override_waypoint_id), None)
            elif (auto_attach is True) and (img_lat is not None and img_lon is not None):
                waypoint_doc, distance_m = nearest_waypoint(
                    img_lat, img_lon, FAKE_WAYPOINTS, max_m=float(attach_threshold_meters or 50.0)
                )

            _id = uuid.uuid4().hex
            key = f"{_id}{_guess_ext(f.filename)}"

            cli.put_object(
                Bucket=S3_BUCKET,
                Key=key,
                Body=content,
                ContentType=f.content_type or "application/octet-stream",
            )
            url = build_public_url(S3_BUCKET, key)

            meta = {
                "id": _id,
                "bucket": S3_BUCKET,
                "key": key,
                "url": url,
                "content_type": f.content_type,
                "size_bytes": len(content),
                "image_type": image_type,
                "captured_at": cap,
                "ingested_at": datetime.now(timezone.utc).isoformat(),
                "geo": {"lat": img_lat, "lon": img_lon} if (img_lat is not None and img_lon is not None) else None,
                "trailcam": (
                    {"camera_make": trailcam_camera_make, "camera_model": trailcam_camera_model}
                    if image_type == "trailcam" else None
                ),
                "waypoint": waypoint_doc,
                "waypoint_id": waypoint_doc["id"] if waypoint_doc else None,
                "distance_to_waypoint_m": distance_m,
            }

            docs.append(build_doc(meta=meta, exif=exif, extra={}))
            results.append({"id": _id, "bucket": S3_BUCKET, "key": key, "url": url})
            to_publish.append({"doc_id": _id, "url": url, "bucket": S3_BUCKET, "key": key})
            attached_summary.append({
                "filename": f.filename,
                "waypoint": waypoint_doc,
                "distance_m": distance_m,
                "exif": (exif.get("gps") or None)
            })

        except Exception as e:
            if continue_on_error:
                results.append({"error": str(e), "filename": getattr(f, "filename", None)})
                attached_summary.append({"filename": getattr(f, "filename", None), "error": str(e)})
                continue
            raise

    if docs:
        index_bulk(es, docs)
        # publish all after bulk index returns
        for item in to_publish:
            await publish_image_uploaded(
                item["url"], item["doc_id"], index_name, item["bucket"], item["key"]
            )

    return {"ok": True, "count": len(results), "items": results, "attached": attached_summary}

@router.get("/images/{image_id}")
def get_image(image_id: str, es: Elasticsearch = Depends(es_dep)):
    src = fetch_one(es, image_id)
    if not src:
        raise HTTPException(status_code=404, detail="not found")
    if not src.get("url") and src.get("bucket") and src.get("key"):
        src["url"] = build_public_url(src["bucket"], src["key"])
    return src

@router.get("/images")
def list_images(
    es: Elasticsearch = Depends(es_dep),
    limit: int = Query(20, ge=1, le=200),
):
    ids = fetch_ids(es, limit=limit, must_not_missing_embedding=False)
    out: List[Dict[str, Any]] = []
    for _id in ids:
        src = fetch_one(es, _id) or {}
        url = src.get("url") or (
            build_public_url(src.get("bucket", ""), src.get("key", ""))
            if (src.get("bucket") and src.get("key"))
            else None
        )
        out.append({"id": _id, "bucket": src.get("bucket"), "key": src.get("key"), "url": url})
    return {"ok": True, "count": len(out), "items": out}

@router.get("/images/{image_id}/similar")
def similar_images(
    image_id: str,
    es: Elasticsearch = Depends(es_dep),
    k: int = Query(10, ge=1, le=100),
):
    src = fetch_one(es, image_id)
    if not src:
        raise HTTPException(status_code=404, detail="not found")
    emb = src.get("embedding")
    if not emb:
        raise HTTPException(status_code=400, detail="image has no embedding yet")

    results = search_similar_by_embedding(es, emb, k=k)
    items: List[Dict[str, Any]] = []
    for _id, score in results:
        if _id == image_id:
            continue
        other = fetch_one(es, _id) or {}
        url = other.get("url") or (
            build_public_url(other.get("bucket", ""), other.get("key", ""))
            if (other.get("bucket") and other.get("key"))
            else None
        )
        items.append({"id": _id, "score": score, "bucket": other.get("bucket"), "key": other.get("key"), "url": url})
    return {"ok": True, "query_id": image_id, "items": items}
