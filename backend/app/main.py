from __future__ import annotations

import os
import logging
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from elasticsearch import Elasticsearch

# Routers
from app.api import events, images, waypoints, trailcams, geo
from app.api.geo_ws import router as geo_ws_router
from app.api.delete import router as delete_router

logger = logging.getLogger("huntapp.api")

app = FastAPI(title="HuntApp API")

# CORS: allow the Next.js dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("API_CORS_ALLOW_ORIGINS", "http://localhost:3030")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _make_es() -> Optional[Elasticsearch]:
    host = (
        os.environ.get("ELASTIC_SEARCH_HOST")
        or os.environ.get("ES_HOST")
        or os.environ.get("ELASTICSEARCH_HOST")
    )
    api_key = (
        os.environ.get("ELASTIC_SEARCH_API_KEY")
        or os.environ.get("ES_API_KEY")
        or os.environ.get("ELASTICSEARCH_API_KEY")
    )
    if not host or not api_key:
        logger.warning("Elasticsearch not configured (ELASTIC_SEARCH_HOST/API_KEY missing)")
        return None
    return Elasticsearch(hosts=[host], api_key=api_key, request_timeout=60)

@app.on_event("startup")
def _startup() -> None:
    app.state.es = _make_es()
    if app.state.es:
        try:
            app.state.es.ping()
            logger.info("Connected to Elasticsearch")
        except Exception as exc:
            logger.warning("Elasticsearch ping failed: %s", exc)

@app.on_event("shutdown")
def _shutdown() -> None:
    es = getattr(app.state, "es", None)
    try:
        es and es.close()
    except Exception:
        pass

# REST + WS routers
app.include_router(geo.router, prefix="/api")
app.include_router(geo_ws_router, prefix="/api/geo")  # /api/geo/ws
app.include_router(events.router, prefix="/api")
app.include_router(images.router, prefix="/api")
app.include_router(waypoints.router, prefix="/api")
app.include_router(trailcams.router, prefix="/api")
app.include_router(delete_router, prefix="/api")

@app.exception_handler(Exception)
def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )

@app.get("/healthz")
def healthz():
    es = getattr(app.state, "es", None)
    ok = False
    reason = None
    if es:
        try:
            ok = bool(es.ping())
            reason = None if ok else "es-ping-failed"
        except Exception as exc:
            reason = f"es-error: {exc}"
    else:
        reason = "es-not-configured"
    return {"ready": ok, "reason": reason}
