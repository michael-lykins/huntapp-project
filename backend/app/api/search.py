"""
Semantic search endpoint using ELSER v2 sparse embeddings on ai_notes_semantic.

Allows natural-language queries like "big buck near food plot" or "doe with fawn
at dawn" — returns ranked trail-camera images with metadata and a presigned S3 URL.
"""
from __future__ import annotations

import logging
import os

import requests
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(tags=["search"])

ELASTIC_HOST = os.environ.get("ELASTIC_SEARCH_HOST", "")
ELASTIC_API_KEY = os.environ.get("ELASTIC_SEARCH_API_KEY", "")
S3_PUBLIC_ENDPOINT = os.environ.get("S3_PUBLIC_ENDPOINT", "http://localhost:9000")
S3_BUCKET = os.environ.get("S3_BUCKET", "trailcam-images")

IMAGES_INDEX = "tactacam-images"


class SearchResult(BaseModel):
    score: float
    doc_id: str
    camera_name: Optional[str] = None
    ai_species: Optional[str] = None
    ai_sex: Optional[str] = None
    ai_age_class: Optional[str] = None
    ai_antlers: Optional[str] = None
    ai_confidence: Optional[float] = None
    ai_notes: Optional[str] = None
    timestamp: Optional[str] = None
    s3_key: Optional[str] = None
    url: Optional[str] = None
    weather_temp: Optional[float] = None
    weather_moon: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchResult]


def _image_url(s3_key: str) -> str:
    return f"{S3_PUBLIC_ENDPOINT}/{S3_BUCKET}/{s3_key}"


@router.get("/search", response_model=SearchResponse)
def semantic_search(
    q: str = Query(..., description="Natural language search query"),
    limit: int = Query(default=12, ge=1, le=50),
):
    """
    Semantic search over trail-camera images using ELSER sparse embeddings.
    Searches the ai_notes_semantic field for images matching the natural language query.
    """
    body = {
        "query": {
            "semantic": {
                "field": "ai_notes_semantic",
                "query": q,
            }
        },
        "size": limit,
        "_source": [
            "camera_name", "ai_species", "ai_sex", "ai_age_class",
            "ai_antlers", "ai_confidence", "ai_notes", "@timestamp",
            "s3_key", "weather.temperature", "weather.moon_phase",
        ],
    }

    resp = requests.post(
        f"{ELASTIC_HOST}/{IMAGES_INDEX}/_search",
        json=body,
        headers={
            "Authorization": f"ApiKey {ELASTIC_API_KEY}",
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    hits = data.get("hits", {}).get("hits", [])
    results = []
    for hit in hits:
        src = hit.get("_source", {})
        s3_key = src.get("s3_key")
        results.append(SearchResult(
            score=round(hit.get("_score", 0), 4),
            doc_id=hit["_id"],
            camera_name=src.get("camera_name"),
            ai_species=src.get("ai_species"),
            ai_sex=src.get("ai_sex"),
            ai_age_class=src.get("ai_age_class"),
            ai_antlers=src.get("ai_antlers"),
            ai_confidence=src.get("ai_confidence"),
            ai_notes=src.get("ai_notes"),
            timestamp=src.get("@timestamp"),
            s3_key=s3_key,
            url=_image_url(s3_key) if s3_key else None,
            weather_temp=src.get("weather", {}).get("temperature"),
            weather_moon=src.get("weather", {}).get("moon_phase"),
        ))

    return SearchResponse(query=q, total=len(results), results=results)
