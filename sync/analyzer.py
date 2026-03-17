"""
Phase 2 — AI analysis of Tactacam trail-camera images.

After each sync, this module finds images in ES that haven't been analyzed yet
(ai_species field is absent), fetches them from S3, sends them to
GPT-4.1-mini vision, and writes the results back to the same ES document.

GPT returns structured JSON:
  {
    "has_animal": bool,
    "species":    str | null,   e.g. "White-tailed deer", "Raccoon", null
    "sex":        str,          "male" | "female" | "unknown"
    "age_class":  str,          "fawn" | "yearling" | "2.5" | "3.5+" | "unknown"
    "antlers":    str | null,   free-text description, null if not applicable
    "confidence": float,        0.0 – 1.0
    "notes":      str
  }

Results written to:
  ai_species, ai_sex, ai_age_class, ai_labels (list), ai_confidence, ai_analyzed_at
"""
import base64
import io
import json
import logging
import os
from datetime import datetime, timezone

import boto3
import requests
from botocore.client import Config
from elasticsearch import Elasticsearch, helpers

logger = logging.getLogger(__name__)

IMAGES_INDEX = "tactacam-images"
S3_BUCKET = os.getenv("S3_BUCKET", "trailcam-images")
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"
VISION_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4.1-mini")
BATCH_SIZE = int(os.getenv("AI_ANALYSIS_BATCH_SIZE", "20"))
MIN_CONFIDENCE = float(os.getenv("AI_MIN_CONFIDENCE", "0.4"))

SYSTEM_PROMPT = (
    "You are a wildlife identification assistant for trail-camera images. "
    "Return ONLY valid JSON with these exact keys:\n"
    '  "has_animal": bool,\n'
    '  "species": string or null (common name, e.g. "White-tailed deer"),\n'
    '  "sex": "male" | "female" | "unknown",\n'
    '  "age_class": "fawn" | "yearling" | "2.5" | "3.5+" | "unknown",\n'
    '  "antlers": string or null (describe rack if visible, else null),\n'
    '  "confidence": float 0.0-1.0,\n'
    '  "notes": string (one sentence observation)\n'
    "If no animal is visible, set has_animal=false and species/sex/age_class/antlers to null/unknown."
)


def _es() -> Elasticsearch:
    return Elasticsearch(
        hosts=[os.environ["ELASTIC_SEARCH_HOST"]],
        api_key=os.environ["ELASTIC_SEARCH_API_KEY"],
    )


def _s3():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT"),
        aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
        region_name=os.getenv("S3_REGION", "us-east-1"),
        config=Config(signature_version="s3v4"),
    )


def _unanalyzed_docs(es: Elasticsearch, batch: int) -> list[dict]:
    """Return docs that haven't been AI-analyzed yet (ai_species absent)."""
    resp = es.search(
        index=IMAGES_INDEX,
        body={
            "size": batch,
            "query": {"bool": {"must_not": {"term": {"ai_analyzed": True}}}},
            "sort": [
                {"has_headshot": "desc"},   # Tactacam-flagged animal shots first
                {"@timestamp": "desc"},
            ],
            "_source": ["s3_key", "filename", "camera_name"],
        },
    )
    return resp["hits"]["hits"]


def _fetch_image(s3, s3_key: str) -> bytes:
    obj = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
    return obj["Body"].read()


def _call_vision(image_bytes: bytes) -> dict:
    b64 = base64.b64encode(image_bytes).decode()
    payload = {
        "model": VISION_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": "Analyze this trail-camera image."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "max_tokens": 300,
    }
    resp = requests.post(
        OPENAI_ENDPOINT,
        json=payload,
        headers={
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
            "Content-Type": "application/json",
        },
        timeout=90,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return json.loads(content) if isinstance(content, str) else content


def _build_update(result: dict) -> dict:
    labels = []
    if result.get("species"):
        labels.append(result["species"])
    if result.get("sex") and result["sex"] != "unknown":
        labels.append(result["sex"])
    if result.get("age_class") and result["age_class"] != "unknown":
        labels.append(result["age_class"])

    return {
        "ai_analyzed": True,
        "ai_analyzed_at": datetime.now(timezone.utc).isoformat(),
        "ai_has_animal": result.get("has_animal", False),
        "ai_species": result.get("species"),
        "ai_sex": result.get("sex"),
        "ai_age_class": result.get("age_class"),
        "ai_antlers": result.get("antlers"),
        "ai_confidence": result.get("confidence"),
        "ai_labels": labels,
        "ai_notes": result.get("notes"),
        # Populate semantic field so ELSER auto-embeds the note on ingest
        "ai_notes_semantic": result.get("notes"),
    }


def run_analysis(batch_size: int = BATCH_SIZE) -> dict:
    """
    Analyze one batch of unprocessed images. Returns summary stats.
    Safe to call repeatedly — stops when no unanalyzed docs remain.
    """
    es = _es()
    s3 = _s3()

    docs = _unanalyzed_docs(es, batch_size)
    if not docs:
        logger.info("No unanalyzed images found")
        return {"analyzed": 0, "animals": 0, "errors": 0}

    logger.info("Analyzing %d images with %s", len(docs), VISION_MODEL)

    stats = {"analyzed": 0, "animals": 0, "errors": 0}
    bulk_updates = []

    for hit in docs:
        doc_id = hit["_id"]
        src = hit["_source"]
        s3_key = src.get("s3_key")
        camera = src.get("camera_name", "?")
        filename = src.get("filename", doc_id)

        try:
            image_bytes = _fetch_image(s3, s3_key)
            result = _call_vision(image_bytes)
            update = _build_update(result)

            bulk_updates.append({
                "_op_type": "update",
                "_index": IMAGES_INDEX,
                "_id": doc_id,
                "doc": update,
            })

            stats["analyzed"] += 1
            if result.get("has_animal") and (result.get("confidence") or 0) >= MIN_CONFIDENCE:
                stats["animals"] += 1
                logger.info(
                    "Animal: [%s] %s — %s %s %s (conf=%.2f)",
                    camera, filename,
                    result.get("species"), result.get("sex"), result.get("age_class"),
                    result.get("confidence", 0),
                )
            else:
                logger.debug("No animal: [%s] %s", camera, filename)

        except Exception as exc:
            logger.error("Analysis failed for %s (%s): %s", filename, camera, exc)
            # Mark as analyzed with error so we don't retry forever
            bulk_updates.append({
                "_op_type": "update",
                "_index": IMAGES_INDEX,
                "_id": doc_id,
                "doc": {
                    "ai_analyzed": True,
                    "ai_analyzed_at": datetime.now(timezone.utc).isoformat(),
                    "ai_error": str(exc),
                },
            })
            stats["errors"] += 1

    if bulk_updates:
        helpers.bulk(es, bulk_updates)

    logger.info(
        "Analysis batch done: %d analyzed, %d animals, %d errors",
        stats["analyzed"], stats["animals"], stats["errors"],
    )
    return stats
