"""
Tactacam Reveal REST API client.

Base URL: https://api.reveal.ishareit.net/v1/
Auth: Bearer {accessToken} from Cognito
"""
import logging
from typing import Generator
import requests

from .auth import TactacamAuth

logger = logging.getLogger(__name__)

BASE_URL = "https://api.reveal.ishareit.net/v1"


class TactacamClient:
    def __init__(self, auth: TactacamAuth):
        self._auth = auth
        self._session = requests.Session()

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._auth.get_token()}"}

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{BASE_URL}{path}"
        resp = self._session.get(url, headers=self._headers(), params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _patch(self, path: str, body: dict) -> dict:
        url = f"{BASE_URL}{path}"
        resp = self._session.patch(url, headers=self._headers(), json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Cameras
    # ------------------------------------------------------------------

    def get_cameras(self) -> list[dict]:
        """Return full list of cameras with GPS, status, battery, signal."""
        data = self._get("/cameras")
        cameras = data if isinstance(data, list) else data.get("cameras", data.get("items", []))
        logger.info("Fetched %d cameras from Tactacam", len(cameras))
        return cameras

    # ------------------------------------------------------------------
    # Photos
    # ------------------------------------------------------------------

    def iter_photos(
        self,
        limit: int = 100,
        since_token: str | None = None,
    ) -> Generator[dict, None, None]:
        """
        Yield photos newest-first from /photos/v2 (cursor-based pagination).

        Stops when `nextToken` is absent (reached the end of the feed).
        Callers that only want new photos should stop early when they see
        a photo they've already processed (compare photoDateUtc / filename).
        """
        params: dict = {"limit": limit}
        if since_token:
            params["nextToken"] = since_token

        while True:
            data = self._get("/photos/v2", params=params)
            photos = data.get("photos", data.get("items", []))
            for photo in photos:
                yield photo
            next_token = data.get("nextToken")
            if not next_token:
                break
            params["nextToken"] = next_token

    def get_photo(self, filename: str) -> dict:
        """Fetch individual photo with full metadata."""
        return self._get(f"/photos/{filename}")

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    def get_account(self) -> dict:
        return self._get("/account")

    def enable_email_notifications(self) -> dict:
        """
        Enable email delivery for new-image notifications so inbound email
        can trigger the fast-path sync.  Safe to call repeatedly — idempotent.
        """
        account = self.get_account()
        delivery = account.get("deliverySettings", {})
        if delivery.get("email"):
            logger.info("Email notifications already enabled")
            return account

        patched = self._patch(
            "/account",
            {"deliverySettings": {**delivery, "email": True}},
        )
        logger.info("Email notifications enabled on Tactacam account")
        return patched
