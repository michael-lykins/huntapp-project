# backend/lib/search/maintenance_images.py
from __future__ import annotations
import os
from typing import Dict, Iterable, List, Optional, Tuple

from elasticsearch import Elasticsearch
from elasticsearch import ApiError

INDEX = "images-v1"

# --- URL builder (same logic as your API's build_public_url) -----------------
PUBLIC_BASE = os.getenv("S3_PUBLIC_BASE")  # e.g., http://minio:9000 or https://cdn.example.com/{bucket}

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


# --- Search helpers ----------------------------------------------------------
def _scan_ids(es: Elasticsearch, query: Dict, fields: Optional[List[str]] = None, batch: int = 500) -> Iterable[Dict]:
    """
    Simple search_after scanner. Yields hits (dict with _id and _source if requested).
    """
    sort = [{"_shard_doc": "asc"}]  # cheap/consistent for scan-like usage
    body = {
        "query": query,
        "size": batch,
        "sort": sort,
        "_source": fields if fields is not None else False,
    }
    last_sort = None
    while True:
        if last_sort:
            body["search_after"] = last_sort
        resp = es.search(index=INDEX, body=body)
        hits = resp.get("hits", {}).get("hits", [])
        if not hits:
            break
        for h in hits:
            yield h
        last_sort = hits[-1]["sort"]


# --- 1) Backfill missing URL where bucket+key exist --------------------------
def backfill_missing_urls(es: Elasticsearch, dry_run: bool = True, limit: Optional[int] = None) -> Tuple[int, int]:
    """
    For docs where url is missing BUT bucket+key exist, compute url and update.
    Returns (candidates, updated).
    """
    query = {
        "bool": {
            "must": [
                {"exists": {"field": "bucket"}},
                {"exists": {"field": "key"}},
            ],
            "must_not": [
                {"exists": {"field": "url"}},
            ],
        }
    }
    candidates = 0
    updated = 0
    ops: List[Dict] = []

    for h in _scan_ids(es, query, fields=["bucket", "key"]):
        candidates += 1
        if limit and candidates > limit:
            break
        src = h.get("_source", {})
        bucket = src.get("bucket")
        key = src.get("key")
        url = build_public_url(bucket, key)
        if not url:
            continue  # nothing to set without S3_PUBLIC_BASE
        if dry_run:
            continue
        ops.append({"update": {"_index": INDEX, "_id": h["_id"]}})
        ops.append({"doc": {"url": url}})
        if len(ops) >= 2 * 500:
            es.bulk(operations=ops, refresh="wait_for")
            updated += 500
            ops = []

    if ops and not dry_run:
        es.bulk(operations=ops, refresh="wait_for")
        updated += len(ops) // 2

    return candidates, (0 if dry_run else updated)


# --- 2) Find / Delete “orphan” analysis-only docs ---------------------------
def find_orphans(es: Elasticsearch, sample: int = 20) -> List[Dict]:
    """
    Orphans = docs missing bucket OR key. We return a small sample with useful fields.
    """
    query = {
        "bool": {
            "should": [
                {"bool": {"must_not": {"exists": {"field": "bucket"}}}},
                {"bool": {"must_not": {"exists": {"field": "key"}}}},
            ],
            "minimum_should_match": 1,
        }
    }
    body = {
        "query": query,
        "size": sample,
        "sort": [{"ingested_at": {"order": "desc"}}],
        "_source": ["bucket", "key", "url", "processed", "analysis", "size_bytes", "ingested_at", "updated_at"],
    }
    resp = es.search(index=INDEX, body=body)
    return resp.get("hits", {}).get("hits", [])


def count_orphans(es: Elasticsearch) -> int:
    query = {
        "bool": {
            "should": [
                {"bool": {"must_not": {"exists": {"field": "bucket"}}}},
                {"bool": {"must_not": {"exists": {"field": "key"}}}},
            ],
            "minimum_should_match": 1,
        }
    }
    resp = es.count(index=INDEX, body={"query": query})
    return resp.get("count", 0)


def delete_orphans(es: Elasticsearch, dry_run: bool = True, limit: Optional[int] = None) -> Tuple[int, int]:
    """
    Deletes docs that cannot be tied to an object (missing bucket OR key).
    Returns (candidates, deleted).
    """
    query = {
        "bool": {
            "should": [
                {"bool": {"must_not": {"exists": {"field": "bucket"}}}},
                {"bool": {"must_not": {"exists": {"field": "key"}}}},
            ],
            "minimum_should_match": 1,
        }
    }
    candidates = 0
    deleted = 0
    ops: List[Dict] = []

    for h in _scan_ids(es, query):
        candidates += 1
        if limit and candidates > limit:
            break
        if dry_run:
            continue
        ops.append({"delete": {"_index": INDEX, "_id": h["_id"]}})
        if len(ops) >= 1000:
            es.bulk(operations=ops, refresh="wait_for")
            deleted += len(ops)
            ops = []

    if ops and not dry_run:
        es.bulk(operations=ops, refresh="wait_for")
        deleted += len(ops)

    return candidates, (0 if dry_run else deleted)


# --- 3) Quick report ---------------------------------------------------------
def report(es: Elasticsearch) -> Dict[str, int]:
    """
    Returns quick counts for sanity checking.
    """
    def _c(q: Dict) -> int:
        return es.count(index=INDEX, body={"query": q}).get("count", 0)

    missing_url_with_key = _c({
        "bool": {
            "must": [{"exists": {"field": "bucket"}}, {"exists": {"field": "key"}}],
            "must_not": [{"exists": {"field": "url"}}],
        }
    })
    orphans = count_orphans(es)
    total = es.count(index=INDEX).get("count", 0)

    return {
        "total_docs": total,
        "orphans_missing_bucket_or_key": orphans,
        "missing_url_but_have_bucket_key": missing_url_with_key,
    }
