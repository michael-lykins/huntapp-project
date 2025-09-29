# backend/app/observability.py
import json, logging, os, time
from typing import Dict
from opentelemetry import trace, metrics
from opentelemetry.trace import get_tracer
from opentelemetry.sdk.resources import Resource

# ---- JSON logging with trace/span correlation --------------------------------
class OTELJSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        span = trace.get_current_span()
        sc = span.get_span_context() if span else None

        def hex_id(v: int, width: int) -> str | None:
            return f"{v:0{width}x}" if v and v != 0 else None

        payload: Dict[str, object] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": hex_id(sc.trace_id, 32) if sc else None,
            "span_id": hex_id(sc.span_id, 16) if sc else None,
            "service.name": os.getenv("OTEL_SERVICE_NAME", None),
            "deployment.environment": os.getenv("DEPLOY_ENV", None),
            "ts": int(record.created * 1000),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps({k: v for k, v in payload.items() if v is not None})

def setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # remove uvicorn’s default handlers so we don’t double-log
    for h in list(root.handlers):
        root.removeHandler(h)
    h = logging.StreamHandler()
    h.setFormatter(OTELJSONFormatter())
    root.addHandler(h)
    # quiet noisy libs a bit
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

# ---- Custom metrics (RED-style for uploads) -----------------------------------
METER = metrics.get_meter("huntapp.observability", "0.1.0")
UPLOADS_TOTAL = METER.create_counter("uploads_total", description="Count of upload requests")
UPLOAD_DURATION_MS = METER.create_histogram("upload_duration_ms", unit="ms",
                                            description="Upload end-to-end latency")
QUEUE_DEPTH = METER.create_up_down_counter("ingest_queue_depth", description="RQ ingest queue depth")

def record_upload(kind: str, success: bool, duration_ms: float):
    attrs = {"kind": kind, "success": success}
    UPLOADS_TOTAL.add(1, attributes=attrs)
    UPLOAD_DURATION_MS.record(float(duration_ms), attributes=attrs)

def record_queue_depth(depth: int):
    # set by adding the delta from last; for simplicity, add absolute as delta from 0
    # (call with depth, then immediately call with -depth when you finish measuring, or just call occasionally)
    QUEUE_DEPTH.add(depth)
