# worker/vision_consumer.py
import os
import json
import asyncio
import logging
from datetime import datetime, timezone

import aiohttp
import boto3
from botocore.client import Config as BotoConfig
import redis.asyncio as aioredis
from elasticsearch import Elasticsearch, ApiError

from lib.services.image_analyzer import analyze_bytes
from lib.search.images_index import ensure_index

logger = logging.getLogger("vision_consumer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- Env/config ---
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CHANNEL = os.getenv("IMAGE_UPLOADED_CHANNEL", "image_uploaded")

ELASTIC_HOST = os.getenv("ELASTIC_SEARCH_HOST")
ELASTIC_KEY = os.getenv("ELASTIC_SEARCH_API_KEY")

# Target index (default to images-v1)
DEFAULT_IMAGES_INDEX = os.getenv("IMAGES_INDEX", "images-v1")

# MinIO / S3 settings
S3_ENDPOINT = os.getenv("S3_ENDPOINT_URL", "http://minio:9000")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY_ID", os.getenv("MINIO_ROOT_USER", "minioadmin"))
S3_SECRET_KEY = os.getenv("S3_SECRET_ACCESS_KEY", os.getenv("MINIO_ROOT_PASSWORD", "minioadmin"))
S3_FORCE_PATH_STYLE = os.getenv("S3_FORCE_PATH_STYLE", "true").lower() == "true"

if not ELASTIC_HOST or not ELASTIC_KEY:
    raise RuntimeError(
        "Missing Elasticsearch credentials in environment variables: "
        "set ELASTIC_SEARCH_HOST and ELASTIC_SEARCH_API_KEY"
    )

# Sync ES client (called via asyncio.to_thread when used)
es = Elasticsearch(ELASTIC_HOST, api_key=ELASTIC_KEY)

# One S3 client for the process
_s3 = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    region_name=S3_REGION,
    config=BotoConfig(s3={"addressing_style": "path"} if S3_FORCE_PATH_STYLE else {}),
)
logger.info("Initialized S3 client for endpoint %s", S3_ENDPOINT)

cfg = {
    "ENABLE_VISION_ANALYSIS": os.getenv("ENABLE_VISION_ANALYSIS"),
    "VISION_ANALYSIS_PROVIDER": os.getenv("VISION_ANALYSIS_PROVIDER"),
    "OPENAI_VISION_MODEL": os.getenv("OPENAI_VISION_MODEL"),
    "AZURE_OPENAI_ENDPOINT": "set" if os.getenv("AZURE_OPENAI_ENDPOINT") else "unset",
    "ANIMAL_CONFIDENCE_MIN": os.getenv("ANIMAL_CONFIDENCE_MIN"),
}
logger.info(f"Vision analysis config: {cfg}")


async def _http_get_bytes(url: str, *, timeout_s: float = 30.0) -> bytes:
    """Fetch raw bytes with sane timeouts."""
    timeout = aiohttp.ClientTimeout(total=timeout_s, connect=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status} fetching {url}")
            return await resp.read()


async def _s3_get_bytes(bucket: str, key: str) -> bytes:
    """Fetch object bytes via S3/MinIO (uses threadpool since boto3 is blocking)."""
    def _do_get():
        obj = _s3.get_object(Bucket=bucket, Key=key)
        return obj["Body"].read()

    return await asyncio.to_thread(_do_get)


async def _es_update(index: str, doc_id: str, body: dict):
    """Run blocking es.update() in a worker thread."""
    def _do_update():
        return es.update(index=index, id=doc_id, doc=body, doc_as_upsert=True)
    return await asyncio.to_thread(_do_update)


def _resolve_index_name(index_from_msg, es_client) -> str:
    """
    Determine which index to update:
    - If message provides a non-empty string in 'index_name', use it.
    - Ignore boolean 'index' values (True/False) that were previously misused as names.
    - Otherwise, default to configured index (ensure it exists first time).
    """
    # Preferred explicit field from publisher
    if isinstance(index_from_msg, str) and index_from_msg.strip():
        return index_from_msg.strip()

    # Fall back to the default images index (create/ensure template if needed)
    try:
        ensured = ensure_index(es_client)
        return ensured or DEFAULT_IMAGES_INDEX
    except Exception:
        # If ensure_index throws for any reason, still fall back to env default
        return DEFAULT_IMAGES_INDEX


async def process_message(message: dict):
    """
    Process a single image_uploaded event:
      - Fetch the image bytes (S3 if bucket+key, else HTTP URL)
      - Analyze with model(s)
      - Update the Elasticsearch doc in the correct index
    Expected message keys:
      doc_id (str)                REQUIRED
      url (str)                   optional if bucket+key provided
      bucket (str)                optional (MinIO/S3)
      key (str)                   optional (MinIO/S3 object key)
      index_name (str)            optional (explicit ES index name)
      index (bool)                optional (legacy flag; ignored for index naming)
    """
    doc_id = message.get("doc_id")
    image_url = message.get("image_url") or message.get("url")
    bucket = message.get("bucket")
    key = message.get("key")
    index_from_msg = message.get("index_name")  # use string only
    legacy_index_field = message.get("index")   # may be True/False in your events

    if not doc_id:
        logger.warning("Malformed message (missing doc_id): %s", message)
        return

    index_name = _resolve_index_name(index_from_msg, es)
    # Helpful debug without accidentally using booleans as index names
    logger.info(
        "Processing doc_id=%s index_name=%s url=%s bucket=%s key=%s legacy_index=%s",
        doc_id, index_name, image_url, bucket, key, legacy_index_field
    )

    try:
        # Prefer S3 if bucket/key are present
        if bucket and key:
            logger.info("Fetching via S3 API (bucket=%s key=%s)", bucket, key)
            content = await _s3_get_bytes(bucket, key)
        elif image_url:
            logger.info("Fetching via HTTP: %s", image_url)
            content = await _http_get_bytes(image_url)
        else:
            raise RuntimeError("No image source: need (bucket+key) or url")

        # Run AI analysis (your implementation returns {"analysis": …, "embedding": …, "timestamp": …})
        result = await analyze_bytes(content)

        # Build update payload
        updated_at = result.get("timestamp") or datetime.now(timezone.utc).isoformat()
        body = {
            "analysis": result.get("analysis"),
            "embedding": result.get("embedding"),
            "updated_at": updated_at,
            "processed": True,
        }

        await _es_update(index_name, doc_id, body)
        logger.info("✅ Updated ES doc %s in %s", doc_id, index_name)

    except ApiError as e:
        logger.exception("Elasticsearch API error updating %s/%s: %s", index_name, doc_id, e)
    except Exception as e:
        logger.exception("Error processing image %s: %s", doc_id, e)


async def consume_once():
    """Subscribe and consume until the connection ends (one lifecycle)."""
    logger.info("Connecting to Redis at %s", REDIS_URL)
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)

    try:
        pubsub = redis.pubsub()
        await pubsub.subscribe(CHANNEL)
        logger.info("Subscribed to Redis channel '%s' — waiting for messages…", CHANNEL)

        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            data = msg.get("data")
            try:
                payload = json.loads(data)
            except Exception:
                logger.warning("Received non-JSON message on %s: %r", CHANNEL, data)
                continue

            await process_message(payload)

    finally:
        try:
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.close()
        except Exception:
            pass
        await redis.close()
        logger.info("Redis connection closed.")


async def consume_forever():
    """Outer loop to auto-reconnect if Redis drops."""
    backoff = 1
    while True:
        try:
            await consume_once()
            await asyncio.sleep(1.0)
            backoff = 1
        except Exception as e:
            logger.exception("Consumer error: %s — reconnecting in %ss", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)  # cap backoff


if __name__ == "__main__":
    asyncio.run(consume_forever())
