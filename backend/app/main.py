# backend/app/main.py
from __future__ import annotations

import os
import time
import logging
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import events, images
from lib.search.events_bootstrap import bootstrap_events
from lib.services.search import get_elasticsearch_client  # your factory

logger = logging.getLogger("huntapp.api")

# ---- Settings (simple, env-driven) -----------------------------------------
API_TITLE = os.getenv("API_TITLE", "HuntApp API")
API_VERSION = os.getenv("API_VERSION", "1.2")
CORS_ORIGINS = os.getenv("API_CORS_ALLOW_ORIGINS", "http://localhost:3030").split(",")

ES_HOST = os.getenv("ELASTIC_SEARCH_HOST")
ES_API_KEY = os.getenv("ELASTIC_SEARCH_API_KEY")

if not ES_HOST or not ES_API_KEY:
    logger.warning("ELASTIC_SEARCH_HOST or ELASTIC_SEARCH_API_KEY not set; "
                   "Elasticsearch features will be disabled.")

# ---- App --------------------------------------------------------------------
app = FastAPI(title=API_TITLE, version=API_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in CORS_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(events.router, prefix="/api")
app.include_router(images.router, prefix="/api")

# ---- Elasticsearch bootstrap (single client + light retry) ------------------
def _init_es_with_retry(max_attempts: int = 5, delay_s: float = 1.0):
    """
    Create a single Elasticsearch client with small retry/backoff.
    Return None if we can't initialize—API should still start.
    """
    if not ES_HOST or not ES_API_KEY:
        return None

    last_exc: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            es = get_elasticsearch_client(host=ES_HOST, api_key=ES_API_KEY)
            # optional: cheap ping to validate connection
            try:
                if hasattr(es, "ping") and not es.ping():
                    raise RuntimeError("Elasticsearch ping failed")
            except Exception as ping_exc:
                # ping being blocked shouldn’t necessarily kill startup
                logger.warning("ES ping failed (attempt %s/%s): %s",
                               attempt, max_attempts, ping_exc)
            return es
        except Exception as exc:
            last_exc = exc
            logger.warning("ES init failed (attempt %s/%s): %s",
                           attempt, max_attempts, exc)
            time.sleep(delay_s * attempt)  # linear backoff
    logger.error("ES init failed after %s attempts: %s", max_attempts, last_exc)
    return None


@app.on_event("startup")
def on_startup():
    """
    Start fast; don’t crash app if ES isn’t available yet.
    """
    es = _init_es_with_retry()
    app.state.es = es  # make available to routers if they want it
    if es is not None:
        try:
            bootstrap_events(es)  # << pass the client
            logger.info("Elasticsearch bootstrap complete.")
        except Exception as exc:
            # Don’t kill the API on bootstrap failures (non-critical)
            logger.warning("Elasticsearch bootstrap skipped: %s", exc, exc_info=True)
    else:
        logger.warning("Elasticsearch not initialized; skipping bootstrap.")


@app.get("/healthz")
def healthz():
    """
    Lightweight liveness probe. Add ES checks here if you want a readiness probe.
    """
    return {"status": "ok", "version": API_VERSION}
