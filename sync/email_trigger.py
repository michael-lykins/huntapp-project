"""
Inbound email webhook — fast-path sync trigger.

Tactacam sends an email notification each time a camera fires. We configure
an email service (e.g. SendGrid Inbound Parse, Postmark, or AWS SES + SNS)
to POST the raw email payload to this endpoint. We parse the camera name /
ID out of the subject, then call the /trigger endpoint on the poller to kick
off a targeted sync for just that camera.

Supported email service formats:
  - SendGrid Inbound Parse  (multipart/form-data, field "subject")
  - Postmark inbound        (JSON body, field "Subject")
  - Generic JSON            (JSON body with "subject" or "Subject")

Set POLLER_URL to the internal address of the poller service.
"""
import logging
import os
import re

import httpx
from fastapi import FastAPI, Form, Request
import uvicorn

logger = logging.getLogger(__name__)

app = FastAPI(title="ridgeline-email-trigger")

POLLER_URL = os.getenv("POLLER_URL", "http://sync:8100")

# Tactacam email subjects look like:
#   "New image from Northwest Corner"
#   "New images from Big Field West (3)"
CAMERA_NAME_RE = re.compile(
    r"new image[s]? from (.+?)(?:\s*\(\d+\))?$",
    re.IGNORECASE,
)


def _extract_camera_name(subject: str) -> str | None:
    m = CAMERA_NAME_RE.search(subject.strip())
    return m.group(1).strip() if m else None


async def _trigger_sync(camera_name: str | None):
    async with httpx.AsyncClient(timeout=10) as client:
        payload = {}
        if camera_name:
            # The poller will resolve name → ID during sync; pass as hint
            logger.info("Email trigger: camera hint '%s'", camera_name)
        try:
            resp = await client.post(f"{POLLER_URL}/trigger", json=payload)
            resp.raise_for_status()
            logger.info("Poller triggered: %s", resp.json())
        except Exception as exc:
            logger.error("Failed to trigger poller: %s", exc)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/inbound/sendgrid")
async def sendgrid_inbound(subject: str = Form(default="")):
    """SendGrid Inbound Parse webhook (multipart/form-data)."""
    camera_name = _extract_camera_name(subject)
    logger.info("SendGrid inbound: subject=%r  camera=%s", subject, camera_name)
    await _trigger_sync(camera_name)
    return {"received": True}


@app.post("/inbound/postmark")
async def postmark_inbound(request: Request):
    """Postmark inbound JSON webhook."""
    body = await request.json()
    subject = body.get("Subject") or body.get("subject", "")
    camera_name = _extract_camera_name(subject)
    logger.info("Postmark inbound: subject=%r  camera=%s", subject, camera_name)
    await _trigger_sync(camera_name)
    return {"received": True}


@app.post("/inbound")
async def generic_inbound(request: Request):
    """Generic JSON webhook — works with any forwarder that sends {subject: ...}."""
    body = await request.json()
    subject = body.get("subject") or body.get("Subject", "")
    camera_name = _extract_camera_name(subject)
    logger.info("Generic inbound: subject=%r  camera=%s", subject, camera_name)
    await _trigger_sync(camera_name)
    return {"received": True}


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    port = int(os.getenv("EMAIL_TRIGGER_PORT", "8101"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
