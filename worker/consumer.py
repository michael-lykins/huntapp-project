import os
import json
import time
import logging
from datetime import datetime, timezone

import redis
from elasticsearch import Elasticsearch

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("ridgeline-worker")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CHANNEL = os.getenv("IMAGE_UPLOADED_CHANNEL", "image_uploaded")

ES_HOST = (
    os.getenv("ELASTIC_SEARCH_HOST")
    or os.getenv("ES_HOST")
    or os.getenv("ELASTICSEARCH_HOST")
)
ES_API_KEY = (
    os.getenv("ELASTIC_SEARCH_API_KEY")
    or os.getenv("ES_API_KEY")
    or os.getenv("ELASTICSEARCH_API_KEY")
)

S3_PUBLIC_BASE = os.getenv("S3_PUBLIC_BASE", "").rstrip("/") or None

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def get_es():
    if not ES_HOST or not ES_API_KEY:
        raise RuntimeError("ELASTIC_SEARCH_HOST and ELASTIC_SEARCH_API_KEY must be set")
    return Elasticsearch(hosts=[ES_HOST], api_key=ES_API_KEY, request_timeout=60)

def main():
    es = get_es()
    r = redis.from_url(REDIS_URL)
    pubsub = r.pubsub()
    pubsub.subscribe(CHANNEL)
    logger.info("Listening on redis channel=%s", CHANNEL)

    for msg in pubsub.listen():
        if msg["type"] != "message":
            continue
        try:
            payload = json.loads(msg["data"])
        except Exception as exc:
            logger.warning("bad message: %s", exc)
            continue

        image_id = payload.get("id")
        if not image_id:
            continue

        doc = {
            "@timestamp": now_iso(),
            "type": "image_ingested",
            "entity": "image",
            "entity_id": image_id,
        }
        try:
            es.index(index="events", document=doc)
        except Exception as exc:
            logger.error("failed to index event: %s", exc)

if __name__ == "__main__":
    main()
