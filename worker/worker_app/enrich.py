# worker/worker_app/enrich.py
"""
Offline/cron worker to enrich images with:
- vector embedding (for kNN search)
- deer detection + sex + simple age guess + probabilities

It will:
  * read a batch of documents missing `embedding` from Elasticsearch,
  * download the image from S3/minio,
  * compute an embedding (prefers open-clip if available; otherwise a 512-dim histogram fallback),
  * run a lightweight heuristic classifier (placeholder; swap with your model),
  * write partial updates back to Elasticsearch.

Run inside the worker container, e.g.:
    docker compose exec worker python -m worker_app.enrich --limit 25
"""

from __future__ import annotations
import os
import io
import sys
import argparse
import hashlib
from typing import List, Dict, Any, Optional, Tuple

import boto3
import numpy as np
from PIL import Image

from elasticsearch import Elasticsearch

# ---- Config (env) -----------------------------------------------------------
ES_HOST = os.getenv("ELASTIC_SEARCH_HOST")
ES_API_KEY = os.getenv("ELASTIC_SEARCH_API_KEY")
INDEX = os.getenv("IMAGES_INDEX", "images-v1")

S3_BUCKET = os.getenv("S3_BUCKET", "trailcam-images")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
S3_ENDPOINT = os.getenv("S3_ENDPOINT")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY")

EMBED_DIM = 512  # must match lib/search/images_index.py


# ---- ES helpers -------------------------------------------------------------
def es_client() -> Elasticsearch:
    if not ES_HOST or not ES_API_KEY:
        raise RuntimeError("ES env not set")
    return Elasticsearch(hosts=[ES_HOST], api_key=ES_API_KEY)


def fetch_candidates(es: Elasticsearch, limit: int) -> List[Dict[str, Any]]:
    query = {
        "bool": {
            "must_not": [{"exists": {"field": "embedding"}}]
        }
    }
    r = es.search(index=INDEX, size=limit, query=query, sort=[{"ingested_at": {"order": "desc"}}])
    return [ {"id": h["_id"], **h["_source"]} for h in r["hits"]["hits"] ]


def update_doc(es: Elasticsearch, doc_id: str, partial: Dict[str, Any]) -> None:
    es.update(index=INDEX, id=doc_id, doc=partial, doc_as_upsert=False)


# ---- S3 helpers -------------------------------------------------------------
def s3_cli():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT or None,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name=S3_REGION,
    )


def download_image(bucket: str, key: str) -> bytes:
    cli = s3_cli()
    r = cli.get_object(Bucket=bucket, Key=key)
    return r["Body"].read()


# ---- Embedding (open-clip optional) ----------------------------------------
def try_open_clip_embed(img: Image.Image) -> Optional[List[float]]:
    """
    If open-clip + torch are available, use CLIP embeddings.
    If not, return None and we’ll fallback.
    """
    try:
        import torch
        import open_clip

        model, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="openai"
        )
        model.eval()
        with torch.no_grad():
            image = preprocess(img).unsqueeze(0)
            features = model.encode_image(image)
            features = features / features.norm(dim=-1, keepdim=True)
            vec = features.squeeze(0).cpu().numpy().astype(np.float32)
            return vec.tolist()
    except Exception:
        return None


def histogram_embed(img: Image.Image, dim: int = EMBED_DIM) -> List[float]:
    """
    Lightweight fallback: concatenate normalized histograms from RGB channels,
    then pad/trim to desired dimension.
    """
    if img.mode != "RGB":
        img = img.convert("RGB")

    # 256 bins per channel -> 768 dims, then reduce/pad to target dim
    hists: List[np.ndarray] = []
    for c in range(3):
        h = np.array(img)[:, :, c].ravel()
        hist, _ = np.histogram(h, bins=256, range=(0, 255), density=True)
        hists.append(hist)

    vec = np.concatenate(hists).astype(np.float32)  # 768-dim
    if vec.shape[0] > dim:
        # simple downsample by averaging chunks
        factor = vec.shape[0] // dim
        vec = vec[: factor * dim].reshape(dim, factor).mean(axis=1)
    elif vec.shape[0] < dim:
        vec = np.pad(vec, (0, dim - vec.shape[0]), mode="constant")

    # L2 normalize
    n = np.linalg.norm(vec) + 1e-12
    vec = (vec / n).astype(np.float32)
    return vec.tolist()


def embed_image(image_bytes: bytes) -> List[float]:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    vec = try_open_clip_embed(img)
    if vec is None:
        vec = histogram_embed(img, dim=EMBED_DIM)
    return vec


# ---- Heuristic classifier (placeholder) ------------------------------------
def classify_whitetail(image_bytes: bytes) -> Tuple[bool, str, str, float, Dict[str, float]]:
    """
    Placeholder classification. Replace with your actual model.

    Returns:
        is_deer: bool
        animal: str (e.g., "whitetail")
        sex: "buck" | "doe" | "unknown"
        age_estimate: float (years)
        prob: dict with keys deer/buck/doe
    """
    # Trivial heuristic using bytes hash just to produce deterministic values
    h = int(hashlib.md5(image_bytes).hexdigest(), 16)
    deer_p = (h % 100) / 100.0
    is_deer = deer_p > 0.45

    if not is_deer:
        return False, "unknown", "unknown", 0.0, {"deer": deer_p, "buck": 0.0, "doe": 0.0}

    buck_p = ((h >> 8) % 100) / 100.0
    doe_p = max(0.0, 1.0 - buck_p)
    sex = "buck" if buck_p >= doe_p else "doe"

    # Fake age: 0.5..6.5
    age = 0.5 + ((h >> 16) % 61) / 10.0

    return True, "whitetail", sex, age, {"deer": deer_p, "buck": buck_p, "doe": doe_p}


# ---- Main pass --------------------------------------------------------------
def process_one(es: Elasticsearch, doc: Dict[str, Any]) -> bool:
    """
    Enrich a single document.
    """
    bucket = doc.get("bucket")
    key = doc.get("key")
    _id = doc.get("id") or doc.get("_id")
    if not bucket or not key or not _id:
        return False

    try:
        img_bytes = download_image(bucket, key)
    except Exception as e:
        print(f"[warn] download failed for {_id}: {e}", file=sys.stderr)
        return False

    try:
        emb = embed_image(img_bytes)
        is_deer, animal, sex, age, prob = classify_whitetail(img_bytes)
        update_doc(es, _id, {
            "embedding": emb,
            "is_deer": is_deer,
            "animal": animal if is_deer else None,
            "sex": sex if is_deer else "unknown",
            "age_estimate": age if is_deer else None,
            "prob": prob,
        })
        return True
    except Exception as e:
        print(f"[warn] enrich failed for {_id}: {e}", file=sys.stderr)
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=25, help="max docs to enrich this pass")
    args = ap.parse_args()

    es = es_client()
    docs = fetch_candidates(es, limit=args.limit)
    if not docs:
        print("no candidates")
        return

    ok = 0
    for d in docs:
        ok += 1 if process_one(es, d) else 0
    print(f"enriched {ok}/{len(docs)}")


if __name__ == "__main__":
    main()
