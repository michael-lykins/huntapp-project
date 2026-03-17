"""
Hunting intelligence chat endpoint.

Three-stage pipeline:
  1. Claude reads the question and writes an ES|QL query (analytics).
  2. Execute ES|QL + run ELSER semantic image search in parallel.
  3. Claude reads the ES|QL results and returns a hunter-focused plain-English answer.
     Semantic image results are returned alongside for visual context.
"""
from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import anthropic
import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["intel"])

ELASTIC_HOST = os.environ.get("ELASTIC_SEARCH_HOST", "")
ELASTIC_API_KEY = os.environ.get("ELASTIC_SEARCH_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ── Schema context given to Claude ────────────────────────────────────────────

SCHEMA = """
You have access to two Elasticsearch indices via ES|QL:

INDEX: tactacam-images
  @timestamp          date       — when the photo was taken (UTC)
  camera_id           keyword    — unique camera identifier
  camera_name         keyword    — human name of the camera (e.g. "Bedding Area")
  s3_key              keyword    — image storage key (ALWAYS include this field when returning individual image rows)
  ai_has_animal       boolean    — true if an animal was detected
  ai_species          keyword    — species common name (e.g. "White-tailed deer", "Raccoon")
  ai_sex              keyword    — "male", "female", or "unknown"
  ai_age_class        keyword    — "fawn", "yearling", "2.5", "3.5+", or "unknown"
  ai_antlers          text       — free-text antler description (null if not applicable)
  ai_confidence       float      — 0.0–1.0 confidence score
  ai_notes            text       — one-sentence GPT observation about the image
  has_headshot        boolean    — Tactacam's own animal-detected flag
  weather.temperature float      — temperature in °F at capture time
  weather.wind_speed  float      — wind speed in mph
  weather.wind_cardinal keyword  — wind direction (N, NE, NW, S, SW, etc.)
  weather.pressure_hpa float     — barometric pressure in inHg
  weather.pressure_tendency keyword — "R" (rising), "F" (falling), "S" (steady)
  weather.moon_phase  keyword    — e.g. "Waxing Gibbous", "Full Moon", "New Moon"
  weather.sun_phase   keyword    — "Daytime", "Civil Twilight", "Nautical Twilight", "Night"
  weather.label       keyword    — weather description (e.g. "Sunny", "Mostly cloudy")

INDEX: tactacam-cameras
  camera_id           keyword    — matches camera_id in tactacam-images
  name                keyword    — camera name
  property_name       keyword    — property / hunting area name
  last_transmission_ts date      — last time camera sent data
  battery_level       keyword    — battery percentage string
  signal_strength     keyword    — signal string

ES|QL syntax notes:
- Use FROM to select an index: FROM tactacam-images
- Filter with WHERE: WHERE ai_has_animal == true AND ai_species == "White-tailed deer"
- Date math: WHERE @timestamp > NOW() - 30 days
- Aggregation: STATS count = COUNT(*) BY camera_name
- Sort: SORT count DESC
- Limit: LIMIT 20
- String comparison is case-sensitive; common species values include: "White-tailed deer", "Raccoon", "Wild turkey", "Eastern cottontail rabbit", "Coyote", "coyote", "Bobcat"
- weather.pressure_tendency values are "R" for rising, "F" for falling, "S" for steady
- For time-of-day analysis, use DATE_EXTRACT("hour_of_day", @timestamp) to get the hour (0-23)
- When the question asks about specific images (oldest, newest, most recent, a particular photo), always SELECT s3_key, camera_name, ai_species, ai_sex, ai_age_class, ai_notes along with @timestamp so images can be displayed
"""

ESQL_SYSTEM = f"""{SCHEMA}

Your job: given a hunter's question, write ONE valid ES|QL query that best answers it.
Return ONLY the raw ES|QL query string — no markdown, no explanation, no backticks.
Keep queries focused and efficient (LIMIT ≤ 50 unless doing aggregations).
If the question is about timing/activity, use DATE_EXTRACT to bucket by hour.
If the question is about weather correlation, filter or group by weather.pressure_tendency.
"""

ANSWER_SYSTEM = """You are a hunting advisor with deep knowledge of white-tailed deer behavior, stand placement, and habitat.
Given a hunter's question and Elasticsearch query results as JSON, give a concise, actionable answer (2-5 sentences).
Focus on what the hunter should DO with this information — when to sit, which stand to prioritize, what conditions to watch for.
Be specific: reference actual camera names, counts, times, and conditions from the data.
If the data is sparse or inconclusive, say so honestly and suggest what to watch for as more data comes in.
Do not mention Elasticsearch, ES|QL, or databases — speak like a trusted hunting buddy.
"""


S3_PUBLIC_ENDPOINT = os.environ.get("S3_PUBLIC_ENDPOINT", "http://localhost:9000")
S3_BUCKET = os.environ.get("S3_BUCKET", "trailcam-images")
IMAGES_INDEX = "tactacam-images"


# ── ES|QL executor ─────────────────────────────────────────────────────────────

def _run_esql(query: str) -> dict:
    resp = requests.post(
        f"{ELASTIC_HOST}/_query",
        json={"query": query},
        headers={"Authorization": f"ApiKey {ELASTIC_API_KEY}", "Content-Type": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _esql_to_records(result: dict) -> list[dict]:
    columns = [c["name"] for c in result.get("columns", [])]
    return [dict(zip(columns, row)) for row in result.get("values", [])]


# ── Semantic image search ───────────────────────────────────────────────────────

def _semantic_search(query: str, limit: int = 6) -> list[dict]:
    """Run ELSER semantic search on ai_notes_semantic, return image hit dicts."""
    try:
        resp = requests.post(
            f"{ELASTIC_HOST}/{IMAGES_INDEX}/_search",
            json={
                "query": {"semantic": {"field": "ai_notes_semantic", "query": query}},
                "size": limit,
                "_source": ["camera_name", "ai_species", "ai_sex", "ai_age_class",
                            "ai_confidence", "ai_notes", "@timestamp", "s3_key"],
            },
            headers={"Authorization": f"ApiKey {ELASTIC_API_KEY}", "Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", {}).get("hits", [])
        results = []
        for h in hits:
            src = h.get("_source", {})
            s3_key = src.get("s3_key")
            results.append({
                "score": round(h.get("_score", 0), 4),
                "doc_id": h["_id"],
                "camera_name": src.get("camera_name"),
                "ai_species": src.get("ai_species"),
                "ai_sex": src.get("ai_sex"),
                "ai_age_class": src.get("ai_age_class"),
                "ai_confidence": src.get("ai_confidence"),
                "ai_notes": src.get("ai_notes"),
                "timestamp": src.get("@timestamp"),
                "s3_key": s3_key,
                "url": f"{S3_PUBLIC_ENDPOINT}/{S3_BUCKET}/{s3_key}" if s3_key else None,
            })
        return results
    except Exception as exc:
        logger.warning("Semantic search failed: %s", exc)
        return []


# ── Request / Response models ──────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str


# Sonnet 4.6 pricing (per million tokens)
_INPUT_COST_PER_M = 3.00
_OUTPUT_COST_PER_M = 15.00

def _token_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000) * _INPUT_COST_PER_M + (output_tokens / 1_000_000) * _OUTPUT_COST_PER_M


class AskResponse(BaseModel):
    answer: str
    esql_query: str
    row_count: int
    images: list[dict] = []
    image_source: str = "elser"  # "esql" | "elser"
    error: Optional[str] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None


# ── Endpoint ───────────────────────────────────────────────────────────────────

@router.post("/intel/ask", response_model=AskResponse)
def ask(req: AskRequest):
    """Three-stage Claude + ES|QL + ELSER hunting intelligence query."""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")
    if not ELASTIC_HOST or not ELASTIC_API_KEY:
        raise HTTPException(status_code=503, detail="Elasticsearch not configured")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Stage 1 — Generate ES|QL query
    try:
        esql_msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=ESQL_SYSTEM,
            messages=[{"role": "user", "content": req.question}],
        )
        esql_query = esql_msg.content[0].text.strip()
        total_in = esql_msg.usage.input_tokens
        total_out = esql_msg.usage.output_tokens
        logger.info("Generated ES|QL: %s", esql_query)
    except Exception as exc:
        logger.error("Claude ES|QL generation failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Query generation failed: {exc}")

    # Stage 2 — Execute ES|QL + ELSER semantic search in parallel
    esql_error: Optional[str] = None
    records: list[dict] = []
    semantic_images: list[dict] = []

    with ThreadPoolExecutor(max_workers=2) as executor:
        esql_future = executor.submit(_run_esql, esql_query)
        semantic_future = executor.submit(_semantic_search, req.question)

        try:
            result = esql_future.result()
            records = _esql_to_records(result)
            logger.info("ES|QL returned %d rows", len(records))
        except Exception as exc:
            esql_error = str(exc)
            logger.warning("ES|QL execution failed: %s", exc)

        try:
            semantic_images = semantic_future.result()
            logger.info("Semantic search returned %d images", len(semantic_images))
        except Exception as exc:
            logger.warning("Semantic search failed: %s", exc)

    # Prefer images from ES|QL records (exact query results) over ELSER semantic matches.
    # ES|QL records have images when the query returns individual rows (not aggregations).
    esql_images = [
        {
            "doc_id": r.get("_id", r.get("camera_id", "")),
            "camera_name": r.get("camera_name"),
            "ai_species": r.get("ai_species"),
            "ai_sex": r.get("ai_sex"),
            "ai_age_class": r.get("ai_age_class"),
            "ai_confidence": r.get("ai_confidence"),
            "ai_notes": r.get("ai_notes"),
            "timestamp": r.get("@timestamp"),
            "s3_key": r.get("s3_key"),
            "url": f"{S3_PUBLIC_ENDPOINT}/{S3_BUCKET}/{r['s3_key']}" if r.get("s3_key") else None,
        }
        for r in records
        if r.get("s3_key")
    ]

    # Stage 3 — Generate hunter-friendly answer
    data_summary = (
        f"Query result ({len(records)} rows):\n{json.dumps(records[:20], default=str, indent=2)}"
        if records
        else f"Query returned no results. Error (if any): {esql_error}"
    )

    answer_prompt = f"""Hunter's question: {req.question}

ES|QL query used: {esql_query}

{data_summary}

Give a concise, actionable hunting answer based on this data."""

    try:
        answer_msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            system=ANSWER_SYSTEM,
            messages=[{"role": "user", "content": answer_prompt}],
        )
        answer = answer_msg.content[0].text.strip()
        total_in += answer_msg.usage.input_tokens
        total_out += answer_msg.usage.output_tokens
    except Exception as exc:
        logger.error("Claude answer generation failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Answer generation failed: {exc}")

    cost = _token_cost(total_in, total_out)
    logger.info("Intel query cost: $%.5f (%d in, %d out tokens)", cost, total_in, total_out)

    # Use ES|QL images if the query returned individual records with images;
    # otherwise fall back to ELSER semantic search results.
    if esql_images:
        images = esql_images[:6]
        image_source = "esql"
    else:
        images = semantic_images
        image_source = "elser"

    return AskResponse(
        answer=answer,
        esql_query=esql_query,
        row_count=len(records),
        images=images,
        image_source=image_source,
        error=esql_error,
        tokens_in=total_in,
        tokens_out=total_out,
        cost_usd=round(cost, 5),
    )
