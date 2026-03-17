"""
Smart 15-minute polling scheduler.

Runs `run_sync()` on a cron-like schedule. Checks lastTransmissionTimestamp
per camera before fetching photos, so only cameras that actually fired since
the last sync incur any real API work.

Also exposes a FastAPI app at /health and /trigger so the email_trigger
service (or any external caller) can fire an immediate sync via HTTP.
"""
import logging
import os
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI
import uvicorn

from .syncer import run_sync

logger = logging.getLogger(__name__)

POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "15"))

app = FastAPI(title="huntapp-sync-poller")
_scheduler: BackgroundScheduler | None = None


@app.get("/health")
def health():
    return {"status": "ok", "poll_interval_minutes": POLL_INTERVAL_MINUTES}


@app.post("/trigger")
def trigger(camera_ids: list[str] | None = None):
    """Fire an immediate sync outside the scheduled window."""
    logger.info("Manual trigger received, camera_ids=%s", camera_ids)
    results = run_sync(camera_ids=camera_ids)
    return {"synced": results}


def _scheduled_sync():
    logger.info("Scheduled sync started")
    try:
        run_sync()
    except Exception as exc:
        logger.error("Scheduled sync failed: %s", exc, exc_info=True)


def start_scheduler():
    global _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _scheduled_sync,
        trigger=IntervalTrigger(minutes=POLL_INTERVAL_MINUTES),
        id="tactacam_poll",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.info("Scheduler started — polling every %d min", POLL_INTERVAL_MINUTES)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    # Run first sync immediately on startup (in background so HTTP is ready fast)
    threading.Thread(target=_scheduled_sync, daemon=True).start()

    start_scheduler()

    port = int(os.getenv("SYNC_PORT", "8100"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
