# backend/app/worker.py
import os
import datetime as dt
import logging
from typing import Dict, Any

from redis import Redis
from rq import Queue, Worker
from rq.exceptions import StopRequested

from opentelemetry import trace, propagate
from opentelemetry.propagate import set_global_textmap
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from app.services import get_search
from app.observability import record_queue_depth

logger = logging.getLogger("huntapp.worker")

QUEUE_NAME = os.getenv("RQ_QUEUE", "ingest")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Ensure W3C tracecontext
set_global_textmap(TraceContextTextMapPropagator())
tracer = trace.get_tracer("huntapp.worker")


def _time_of_day(ts: dt.datetime) -> str:
    h = ts.hour
    if 5 <= h < 8 or 18 <= h < 21:
        return "dusk_dawn"
    if 8 <= h < 18:
        return "day"
    return "night"


def process_uploaded_image(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Worker entrypoint: build a normalized trailcam document and index via Search adapter."""
    ctx = propagate.extract(payload.get("otel", {}))

    with tracer.start_as_current_span("process_uploaded_image", context=ctx):
        search = get_search()

        now = dt.datetime.utcnow()
        ts = now

        # EXIF (if provided by API)
        exif = payload.get("exif") or {}
        # Try a couple formats if an EXIF datetime is present
        for k in ("EXIF DateTimeOriginal", "Image DateTime", "GPS GPSDate"):
            v = exif.get(k)
            if v:
                for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                    try:
                        ts = dt.datetime.strptime(str(v), fmt)
                        break
                    except Exception:
                        continue

        lat = payload.get("lat")
        lon = payload.get("lon")

        # Build a vendor-agnostic doc matching your serverless template (hunt-trailcam-template)
        doc = {
            "@timestamp": ts.isoformat() + "Z",
            "camera_id": payload.get("camera_id"),
            "image_url": payload.get("image_url"),  # keyword (index:false) in your template
            "image": {
                "width": payload.get("width"),
                "height": payload.get("height"),
                "exif": exif,  # dynamic:true per your template
            },
            "sun_period": _time_of_day(ts),
        }

        if lat is not None and lon is not None:
            try:
                doc["location"] = {"lat": float(lat), "lon": float(lon)}
            except Exception:
                pass

        # Optional mapping: API label -> species
        if payload.get("label"):
            doc["species"] = payload["label"]

        # Delegate to adapter (keeps ES specifics out of app code)
        res = search.index_trailcam(doc)
        logger.info("Indexed trailcam doc", extra={"result": res})

        return {"ok": True, **res}


def enqueue_image_job(payload: Dict[str, Any]) -> str:
    """Inject current trace context and enqueue for the worker."""
    carrier: Dict[str, str] = {}
    propagate.inject(carrier)

    payload = dict(payload)
    payload["otel"] = carrier

    redis_conn = Redis.from_url(REDIS_URL)
    q = Queue(QUEUE_NAME, connection=redis_conn)

    try:
        record_queue_depth(q.count)
    except Exception:
        pass

    job = q.enqueue(process_uploaded_image, payload)
    return job.get_id()


def run_worker():
    redis_conn = Redis.from_url(REDIS_URL)
    w = Worker([QUEUE_NAME], connection=redis_conn)
    try:
        w.work(with_scheduler=False)
    except StopRequested:
        logger.info("RQ worker stopping gracefully (StopRequested)")
    finally:
        # best-effort OTel flush on shutdown
        try:
            tp = trace.get_tracer_provider()
            if hasattr(tp, "shutdown"):
                tp.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    run_worker()
