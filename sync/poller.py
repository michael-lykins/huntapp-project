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
from .analyzer import run_analysis
from .onx_syncer import run_onx_sync

logger = logging.getLogger(__name__)

POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "15"))
ONX_SYNC_INTERVAL_HOURS = int(os.getenv("ONX_SYNC_INTERVAL_HOURS", "6"))

app = FastAPI(title="ridgeline-sync-poller")
_scheduler: BackgroundScheduler | None = None


@app.get("/health")
def health():
    return {"status": "ok", "poll_interval_minutes": POLL_INTERVAL_MINUTES}


@app.post("/trigger")
def trigger(
    camera_ids: list[str] | None = None,
    backfill_days: int | None = None,
    since_date: str | None = None,
):
    """Fire an immediate sync + AI analysis outside the scheduled window.

    For a full historical backfill use since_date (preferred):
        POST /trigger?since_date=2022-12-13

    For a rolling lookback use backfill_days:
        POST /trigger?backfill_days=90

    Backfills (since_date or backfill_days) run in the background and return
    immediately — check container logs for progress.
    """
    logger.info(
        "Manual trigger received, camera_ids=%s, backfill_days=%s, since_date=%s",
        camera_ids, backfill_days, since_date,
    )
    is_backfill = backfill_days is not None or since_date is not None

    if is_backfill:
        # Backfills can take minutes to hours — run async so the caller gets
        # an immediate acknowledgement instead of a timeout.
        def _run():
            try:
                synced = run_sync(camera_ids=camera_ids, backfill_days=backfill_days, since_date=since_date)
                ai_stats = run_analysis()
                logger.info("Backfill complete: synced=%s ai=%s", synced, ai_stats)
            except Exception as exc:
                logger.error("Backfill failed: %s", exc, exc_info=True)

        threading.Thread(target=_run, daemon=True).start()
        return {
            "status": "backfill_started",
            "since_date": since_date,
            "backfill_days": backfill_days,
            "camera_ids": camera_ids,
            "message": "Backfill running in background — follow logs for progress.",
        }

    synced = run_sync(camera_ids=camera_ids)
    ai_stats = run_analysis()
    return {"synced": synced, "ai": ai_stats}


@app.post("/analyze")
def analyze():
    """Run a standalone AI analysis pass (no sync)."""
    stats = run_analysis()
    return {"ai": stats}


@app.post("/trigger/onx")
def trigger_onx():
    """Fire an immediate OnX sync (waypoints, shapes, tracks, land areas, cameras)."""
    logger.info("Manual OnX sync trigger received")
    results = run_onx_sync()
    return {"onx": results}


def _scheduled_onx_sync():
    logger.info("Scheduled OnX sync started")
    try:
        run_onx_sync()
    except Exception as exc:
        logger.error("Scheduled OnX sync failed: %s", exc, exc_info=True)


def _scheduled_sync():
    logger.info("Scheduled sync started")
    try:
        run_sync()
        run_analysis()
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
    _scheduler.add_job(
        _scheduled_onx_sync,
        trigger=IntervalTrigger(hours=ONX_SYNC_INTERVAL_HOURS),
        id="onx_sync",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.info(
        "Scheduler started — Tactacam every %d min, OnX every %d hrs",
        POLL_INTERVAL_MINUTES, ONX_SYNC_INTERVAL_HOURS,
    )


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
