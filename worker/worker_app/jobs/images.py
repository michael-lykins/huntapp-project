import time, json
from datetime import datetime, timezone
from elasticsearch import Elasticsearch
from lib.images.io import parse_exif
from lib.images.ai import image_embedding_and_scores
from lib.search.images_bootstrap import IMAGES_INDEX, ensure_index

def process_and_index_image(*, es_url: str, es_api_key: str, doc: dict, raw: bytes):
    es = Elasticsearch(es_url, api_key=es_api_key, request_timeout=60)
    ensure_index(es)

    exif = {}
    try:
        exif = parse_exif(raw)
    except Exception:
        pass

    emb, contains_deer, deer_kind, age_bucket, scores = image_embedding_and_scores(raw)

    doc["ingested_at"] = datetime.now(timezone.utc).isoformat()
    if "gps" not in doc and "gps" in exif:
        doc["gps"] = exif["gps"]
    if "timestamp" not in doc and "timestamp_raw" in exif:
        # you can parse better; many trail-cams use "YYYY:MM:DD HH:MM:SS"
        doc["timestamp"] = exif["timestamp_raw"].replace(":", "-", 2)

    doc["camera_make"]  = doc.get("camera_make")  or exif.get("camera_make")
    doc["camera_model"] = doc.get("camera_model") or exif.get("camera_model")
    doc["ai"] = {
        "contains_deer": contains_deer,
        "deer_kind": deer_kind,
        "age_bucket": age_bucket,
        "scores": scores
    }
    doc["embedding"] = emb.tolist()

    es.index(index=IMAGES_INDEX, id=doc["image_id"], document=doc)
    return {"indexed": True, "id": doc["image_id"], "ai": doc["ai"]}
