"""
Backfill CLIP embeddings for tactacam-images documents.

Finds analyzed images missing the `embedding` field, downloads each from S3,
generates a 512-dim CLIP (ViT-B-32) embedding, and writes it back to ES.

Usage:
    docker compose exec worker python -m worker_app.jobs.embed_tactacam
    docker compose exec worker python -m worker_app.jobs.embed_tactacam --limit 100 --batch 10
"""
from __future__ import annotations

import argparse
import io
import logging
import os
import sys

import boto3
import torch
import open_clip
from PIL import Image
from botocore.client import Config
from elasticsearch import Elasticsearch, helpers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

IMAGES_INDEX = "tactacam-images"
S3_BUCKET = os.getenv("S3_BUCKET", "trailcam-images")

_MODEL = None
_PREPROCESS = None


def _load_clip():
    global _MODEL, _PREPROCESS
    if _MODEL is None:
        logger.info("Loading CLIP ViT-B-32...")
        _MODEL, _, _PREPROCESS = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="laion2b_s34b_b79k"
        )
        _MODEL.eval()
        logger.info("CLIP loaded")


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


@torch.inference_mode()
def _embed(image_bytes: bytes) -> list[float]:
    _load_clip()
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    t = _PREPROCESS(img).unsqueeze(0)
    feats = _MODEL.encode_image(t)
    feats = feats / feats.norm(dim=-1, keepdim=True)
    return feats[0].cpu().numpy().tolist()


def _fetch_candidates(es: Elasticsearch, limit: int) -> list[dict]:
    resp = es.search(
        index=IMAGES_INDEX,
        body={
            "size": limit,
            "query": {
                "bool": {
                    "must": [{"term": {"ai_analyzed": True}}],
                    "must_not": [{"exists": {"field": "embedding"}}],
                }
            },
            "sort": [{"ai_analyzed_at": "desc"}],
            "_source": ["s3_key", "filename", "camera_name"],
        },
    )
    return resp["hits"]["hits"]


def run(limit: int = 500, batch_size: int = 20) -> dict:
    es = _es()
    s3 = _s3()

    docs = _fetch_candidates(es, limit)
    if not docs:
        logger.info("No documents missing embeddings")
        return {"processed": 0, "errors": 0}

    logger.info("Embedding %d images with CLIP ViT-B-32", len(docs))
    stats = {"processed": 0, "errors": 0}
    bulk_ops = []

    for hit in docs:
        doc_id = hit["_id"]
        s3_key = hit["_source"].get("s3_key")
        camera = hit["_source"].get("camera_name", "?")

        if not s3_key:
            logger.warning("Doc %s has no s3_key, skipping", doc_id)
            stats["errors"] += 1
            continue

        try:
            obj = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
            image_bytes = obj["Body"].read()
            embedding = _embed(image_bytes)

            bulk_ops.append({
                "_op_type": "update",
                "_index": IMAGES_INDEX,
                "_id": doc_id,
                "doc": {"embedding": embedding},
            })
            stats["processed"] += 1

            if len(bulk_ops) >= batch_size:
                helpers.bulk(es, bulk_ops)
                logger.info("  flushed %d embeddings", len(bulk_ops))
                bulk_ops.clear()

        except Exception as exc:
            logger.error("Failed %s (%s): %s", doc_id, camera, exc)
            stats["errors"] += 1

    if bulk_ops:
        helpers.bulk(es, bulk_ops)
        logger.info("  flushed %d embeddings", len(bulk_ops))

    logger.info("Done: %d embedded, %d errors", stats["processed"], stats["errors"])
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Backfill CLIP embeddings for tactacam-images")
    ap.add_argument("--limit", type=int, default=500, help="max docs to process")
    ap.add_argument("--batch", type=int, default=20, help="ES bulk flush size")
    args = ap.parse_args()
    result = run(limit=args.limit, batch_size=args.batch)
    sys.exit(0 if result["errors"] == 0 else 1)
