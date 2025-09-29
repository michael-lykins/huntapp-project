import os, datetime as dt, time, logging
from typing import Dict, Any
from redis import Redis
from rq import Queue, Worker
from opentelemetry import trace, propagate
from opentelemetry.propagate import set_global_textmap
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from app.es import get_search_client
from app.observability import record_queue_depth

logger = logging.getLogger("huntapp.worker")

QUEUE_NAME = os.getenv("RQ_QUEUE", "ingest")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Ensure we use W3C tracecontext
set_global_textmap(TraceContextTextMapPropagator())
tracer = trace.get_tracer("huntapp.worker")

def _cardinal_16(deg: float) -> str:
    dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
    deg = (deg % 360 + 360) % 360
    idx = int((deg + 11.25) // 22.5) % 16
    return dirs[idx]

def _time_of_day(ts: dt.datetime) -> str:
    h = ts.hour
    if 5 <= h < 8 or 18 <= h < 21: return "dusk_dawn"
    if 8 <= h < 18: return "day"
    return "night"

def process_uploaded_image(payload: Dict[str, Any]) -> Dict[str, Any]:
    # Extract parent trace context if present
    ctx = propagate.extract(payload.get("otel", {}))
    with tracer.start_as_current_span("process_uploaded_image", context=ctx) as span:
        es = get_search_client()
        now = dt.datetime.utcnow()
        ts = now
        exif = payload.get("exif") or {}
        for k in ("EXIF DateTimeOriginal", "Image DateTime", "GPS GPSDate"):
            if k in exif:
                try:
                    ts = dt.datetime.strptime(str(exif[k]), "%Y:%m:%d %H:%M:%S")
                    break
                except Exception:
                    pass

        lat = payload.get("lat"); lon = payload.get("lon"); heading = payload.get("heading_deg")
        doc = {
            "@timestamp": ts.isoformat() + "Z",
            "ingest_ts": payload.get("ingest_ts") or now.isoformat() + "Z",
            "camera": {"id": payload.get("camera_id")},
            "labels": {"user": [payload.get("label")] if payload.get("label") else []},
            "media": {"url": payload.get("image_url"), "size_bytes": payload.get("size_bytes")},
            "exif": exif,
            "context": {"time_of_day": _time_of_day(ts)},
        }
        if lat is not None and lon is not None:
            doc["camera"]["location"] = {"lat": float(lat), "lon": float(lon)}
        if heading is not None:
            doc.setdefault("camera", {}).setdefault("heading", {})["deg"] = float(heading)
            doc["camera"]["heading"]["cardinal_16"] = _cardinal_16(float(heading))

        index = f"hunt-images-{ts.strftime('%Y.%m')}"
        res = es.index(index=index, document=doc)
        span.set_attribute("index", index)
        span.set_attribute("result", res.get("result"))
        logger.info(f"Indexed image to {index}")
        return {"ok": True, "index": index, "result": res.get("result")}

def enqueue_image_job(payload: Dict[str, Any]) -> str:
    """Inject current trace context and enqueue for the worker."""
    # Inject W3C trace context so worker spans are children of the API request span
    carrier: Dict[str, str] = {}
    propagate.inject(carrier)
    payload = dict(payload)  # copy
    payload["otel"] = carrier

    redis_conn = Redis.from_url(REDIS_URL)
    q = Queue(QUEUE_NAME, connection=redis_conn)
    # optional visibility metric: queue depth snapshot
    try:
        record_queue_depth(q.count)
    except Exception:
        pass
    job = q.enqueue(process_uploaded_image, payload)
    return job.get_id()

def run_worker():
    redis_conn = Redis.from_url(REDIS_URL)
    Worker([QUEUE_NAME], connection=redis_conn).work(with_scheduler=False)

if __name__ == "__main__":
    run_worker()
