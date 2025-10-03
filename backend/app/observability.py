import logging
import os
from typing import Optional, Mapping

try:
    # Logging correlation
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
except Exception:  # pragma: no cover
    LoggingInstrumentor = None  # type: ignore

try:
    from opentelemetry import metrics
except Exception:  # pragma: no cover
    metrics = None  # type: ignore

_metrics_initialized = False
_queue_hist = None

def setup_logging(level: Optional[str] = None) -> None:
    """Configure Python logging and (optionally) OpenTelemetry log correlation.

    This is safe to call multiple times.
    """
    lvl = (level or os.getenv("LOG_LEVEL") or "INFO").upper()
    try:
        logging.getLogger().setLevel(lvl)
    except Exception:
        pass

    if LoggingInstrumentor is not None:
        try:
            LoggingInstrumentor().instrument(set_logging_format=True)
        except Exception:
            # Best-effort; don't crash the app if OTEL libs are missing at build time
            pass

    logging.basicConfig(
        level=lvl,
        format=(
            "%(asctime)s %(levelname)s "
            "[trace_id=%(otelTraceID)s span_id=%(otelSpanID)s "
            "resource.service.name=%(otelServiceName)s trace_sampled=%(otelTraceSampled)s] "
            "- %(name)s: %(message)s"
        ),
    )

def _init_metrics() -> None:
    global _metrics_initialized, _queue_hist
    if _metrics_initialized or metrics is None:
        _metrics_initialized = True
        return
    try:
        meter = metrics.get_meter("huntapp.observability")
        _queue_hist = meter.create_histogram(
            name="huntapp.queue.depth",
            description="Approximate depth of the RQ ingest queue",
            unit="{jobs}",
        )
    except Exception:
        _queue_hist = None
    _metrics_initialized = True

def record_queue_depth(depth: int, attributes: Optional[Mapping[str, str]] = None) -> None:
    """Record a queue depth sample (exported via OTEL metrics).

    We intentionally use a histogram so we can see distribution over time without needing stateful callbacks.
    """
    if not _metrics_initialized:
        _init_metrics()
    if _queue_hist is None:
        return
    try:
        _queue_hist.record(int(depth), attributes or {"queue": "ingest"})
    except Exception:
        # Don't break app flow on metrics errors
        pass
