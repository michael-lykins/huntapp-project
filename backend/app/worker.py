# backend/app/worker.py
import os
import logging
import datetime as dt
from typing import Dict, Any, Optional

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

# Ensure we use W3C tracecontext
set_global_textmap(TraceContextTextMapPropagator())
tracer = trace.get_tracer("huntapp.worker")

# Accept a few common EXIF datetime formats
_EXIF_DT_FORMATS = (
    "%Y:%m:%d %H:%M:%S",  # EXIF standard (e.g. 2025:10:01 07:07:16)
    "%Y-%m-%d %H:%M:%S",  # sometimes normalized
    "%Y-%m-%dT%H:%M:%S",  # ISO-ish without tz
)

def _parse_exif_dt(exif: Dict[str, Any]) -> Optional[dt.datetime]:
    for k in ("EXIF DateTimeOriginal", "Image DateTime", "GPS GPSDate"):
        v = exif.get(k)
        if not v:
            continue
        s = str(v).strip()
        for fmt in _EXIF_DT_FORMATS:
            try:
                # make tz-aware in UTC
                return dt.datetime.strptime(s, fmt).replace(tzinfo=dt.timezone.utc)
            except Exception:
                continue
    return None

def _time_of_day(ts: dt.datetime) -> str:
    # ts is assumed tz-aware; fall back gracefully
    hour = ts.hour
    if 5 <= hour < 8 or 18 <= hour < 21:
        return "dusk_dawn"
    if 8 <= hour < 18:
        return "day"
    return "night"

def process_uploaded_image(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Background job: build a vendor-agnostic trailcam document and hand it to
    the Search adapter. No direct Elasticsearch references here.
    """
    # Rehydrate parent span context (so worker spans attach to the API trace)
    ctx = propagate.extract(payload.get("otel", {}))

    with tracer.start_as_current_span("process_uploaded_image", context=ctx) as span:
        now = dt.datetime.now(dt.timezone.utc)

        exif: Dict[str, Any] = payload.get("exif") or {}
        ts = _parse_exif_dt(exif) or now

        # Pull optional fields provided by the API
        camera_id = payload.get("camera_id")
        image_url = payload.get("image_url")
        width = payload.get("width")
        height = payload.get("height")
        lat = payload.get("lat")
        lon = payload.get("lon")
        label = payload.get("label")  # map to 'species' if provided

        # Build a document that matches your serverless hunt-trailcam-template
        doc: Dict[str, Any] = {
            "@timestamp": ts.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "camera_id": camera_id,
            "image_url": image_url,  # keyword (index: false) per your template
            "image": {
                "width": width,
                "height": height,
                "exif": exif,  # dynamic: true in your template
            },
            "sun_period": _time_of_day(ts),
        }

        # Top-level geo_point + lat/lon (your template provides both)
        has_geo = False
        try:
            if lat is not None and lon is not None:
                lat_f = float(lat)
                lon_f = float(lon)
                doc["location"] = {"lat": lat_f, "lon": lon_f}
                doc["lat"] = lat_f
                doc["lon"] = lon_f
                has_geo = True
        except Exception:
            # If coords are invalid, skip silently (template will still accept the doc)
            pass

        # Optional species (from 'label')
        if label:
            doc["species"] = str(label)

        # Add some span attributes for visibility
        span.set_attribute("trailcam.camera_id", str(camera_id) if camera_id else "")
        span.set_attribute("trailcam.image_url", str(image_url) if image_url else "")
        span.set_attribute("trailcam.has_geo", has_geo)
        span.set_attribute("trailcam.sun_period", doc["sun_period"])

        # Vendor-agnostic indexing through the adapter
        search = get_search()

        # Prefer a specific method if your adapter provides one; otherwise fall back.
        # The adapter should take responsibility for index naming (e.g., hunt-trailcam-YYYY.MM)
        # and for any vendor-specific API calls.
        try:
            # Recommended adapter signature:
            #   index_name, result = search.index_trailcam(doc, ts)
            index_name, result = search.index_trailcam(doc, ts)  # type: ignore[attr-defined]
        except AttributeError:
            try:
                # Generic escape hatch if your adapter uses a unified method:
                #   index_name, result = search.index(kind="trailcam", doc=doc, ts=ts)
                index_name, result = search.index(kind="trailcam", doc=doc, ts=ts)  # type: ignore[attr-defined]
            except Exception as e:
                logger.exception("Search adapter failed to index trailcam document")
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                return {"ok": False, "error": "index_failed"}

        span.set_attribute("search.index", index_name or "")
        span.set_attribute("search.result", str(result) if result is not None else "")

        logger.info("Indexed trailcam document", extra={"index": index_name, "result": result})
        return {"ok": True, "index": index_name, "result": result}

def enqueue_image_job(payload: Dict[str, Any]) -> str:
    """
    Inject current trace context and enqueue for the worker.
    This preserves parent/child relationships in traces across API → worker.
    """
    carrier: Dict[str, str] = {}
    propagate.inject(carrier)

    job_payload = dict(payload)
    job_payload["otel"] = carrier

    redis_conn = Redis.from_url(REDIS_URL)
    q = Queue(QUEUE_NAME, connection=redis_conn)

    # Best-effort metric about queue depth (kept compatible with your existing helper)
    try:
        record_queue_depth(q.count)  # keep the callable semantics you used previously
    except Exception:
        pass

    job = q.enqueue(process_uploaded_image, job_payload)
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
