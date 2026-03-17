# backend/lib/search/images_index.py
from __future__ import annotations
from typing import Any, Dict, Iterable, List, Optional, Tuple

from elasticsearch import Elasticsearch
from elasticsearch import ApiError

INDEX = "images-v1"

# Serverless-safe mapping (no index "settings")
# Expanded with a few frequently used fields and an "analysis" object
MAPPING_ONLY: Dict[str, Any] = {
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "bucket": {"type": "keyword"},
            "key": {"type": "keyword"},
            "url": {"type": "keyword"},
            "content_type": {"type": "keyword"},
            "size_bytes": {"type": "long"},
            "image_type": {"type": "keyword"},  # trailcam | cellphone | digital
            "trailcam": {
                "properties": {
                    "camera_make": {"type": "keyword"},
                    "camera_model": {"type": "keyword"},
                    "trigger_mode": {"type": "keyword"},
                    "sensitivity": {"type": "keyword"},
                }
            },
            "captured_at": {"type": "date"},
            "ingested_at": {"type": "date"},
            "updated_at": {"type": "date"},
            "processed": {"type": "boolean"},
            "geo": {"type": "geo_point"},
            "width": {"type": "integer"},
            "height": {"type": "integer"},
            "mode": {"type": "keyword"},
            "format": {"type": "keyword"},

            # Optional ML enrichment container (keeps related fields together)
            "analysis": {
                "properties": {
                    "has_animal": {"type": "boolean"},
                    "species": {"type": "keyword"},
                    "sex": {"type": "keyword"},
                    "age_estimate": {"type": "keyword"},
                    "confidence": {"type": "float"},
                    "notes": {"type": "keyword"},
                }
            },

            # Legacy loose fields (kept for compatibility)
            "labels": {"type": "keyword"},
            "animal": {"type": "keyword"},
            "age_estimate": {"type": "float"},

            # Vector (used by /similar). Keep simple for serverless:
            "embedding": {"type": "dense_vector", "dims": 512},
        }
    }
}


def ensure_index(es: Elasticsearch) -> str:
    """
    Create the index if it does not exist and RETURN the index name.
    Designed to be safe for Elasticsearch Serverless.
    """
    if not es.indices.exists(index=INDEX):
        # Try to create using serverless-safe body
        try:
            es.indices.create(index=INDEX, body=MAPPING_ONLY)
        except ApiError as e:
            # If someone else created it first, that's fine
            if getattr(e, "error", "") != "resource_already_exists_exception":
                # Older code could have passed illegal 'settings'; we don't.
                # If we still get a 400/other, re-raise so you see what's wrong.
                raise
    # Always return the name the caller should use
    return INDEX


def build_doc(meta: Dict[str, Any], exif: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge meta + exif + extra, dropping None values and empty dicts.
    EXIF keys (e.g., captured_at, width/height) will naturally override meta on collision.
    """
    merged = {**meta, **exif, **extra}
    # Drop Nones and empty nested dicts
    cleaned: Dict[str, Any] = {}
    for k, v in merged.items():
        if v is None:
            continue
        if isinstance(v, dict) and not v:
            continue
        cleaned[k] = v
    return cleaned


def index_one(es: Elasticsearch, doc: Dict[str, Any]) -> str:
    """
    Index a single document using doc['id'] as the _id with create-only semantics.
    This prevents accidental overwrites/duplicates if retried.
    """
    doc_id = doc.get("id")
    if not doc_id:
        raise ValueError("index_one: doc missing required 'id'")

    # create-only; if the ID already exists, ES will throw 409
    resp = es.index(index=INDEX, id=doc_id, document=doc, op_type="create", refresh="wait_for")
    return resp["_id"]


def index_bulk(es: Elasticsearch, docs: Iterable[Dict[str, Any]]) -> List[str]:
    """
    Bulk index using each doc['id'] as the ES _id with create-only semantics.
    Ensures worker updates modify existing docs instead of creating new ones.
    """
    ops: List[Any] = []
    ids: List[str] = []
    for d in docs:
        doc_id = d.get("id")
        if not doc_id:
            raise ValueError("index_bulk: one or more docs missing required 'id'")
        # Use explicit bulk ops with create to enforce create-only semantics.
        ops.append({"create": {"_index": INDEX, "_id": doc_id}})
        ops.append(d)
        ids.append(doc_id)

    if not ops:
        return []

    es.bulk(operations=ops, refresh="wait_for")
    return ids


def fetch_one(es: Elasticsearch, doc_id: str) -> Optional[Dict[str, Any]]:
    try:
        resp = es.get(index=INDEX, id=doc_id)
        return resp.get("_source")
    except ApiError:
        return None


def fetch_ids(
    es: Elasticsearch,
    limit: int = 20,
    must_not_missing_embedding: bool = False,
) -> List[str]:
    """
    Return recent IDs; optionally require documents that have an 'embedding' field.
    """
    must_not = [{"exists": {"field": "embedding"}}] if must_not_missing_embedding else []
    body = {
        "query": {
            "bool": {
                "must": [{"match_all": {}}],
                # when must_not_missing_embedding=True, we want docs that DO have embedding
                # so we negate the negation approach and simply require exists in must
            }
        },
        "sort": [{"ingested_at": {"order": "desc"}}],
        "size": limit,
        "_source": False,
    }
    if must_not_missing_embedding:
        # If caller wants only docs WITH embeddings, add exists filter to must
        body["query"]["bool"].pop("must_not", None)
        body["query"]["bool"]["must"] = [{"exists": {"field": "embedding"}}]
    resp = es.search(index=INDEX, body=body)
    return [hit["_id"] for hit in resp.get("hits", {}).get("hits", [])]


def search_similar_by_embedding(
    es: Elasticsearch, emb: List[float], k: int = 10
) -> List[Tuple[str, float]]:
    """
    Simple kNN search on the 'embedding' field.
    """
    body = {
        "knn": {
            "field": "embedding",
            "query_vector": emb,
            "k": k,
            "num_candidates": max(k * 10, 100),
        },
        "_source": False,
    }
    resp = es.search(index=INDEX, body=body)
    out: List[Tuple[str, float]] = []
    for h in resp.get("hits", {}).get("hits", []):
        out.append((h["_id"], h.get("_score", 0.0)))
    return out
