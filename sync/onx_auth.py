"""
OnX Maps OAuth2 PKCE authentication.

OnX uses Ory Hydra with PKCE (no client secret, browser-based).
Client ID: b500432c-9287-4f79-8a49-fb0ac1181370

First-time setup: run `python -m sync.onx_login` to complete the browser
login and store tokens to ONX_TOKEN_FILE.  Subsequent runs load from that
file and refresh automatically.
"""
import json
import logging
import os
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

TOKEN_ENDPOINT = "https://identity.onxmaps.com/oauth2/token"
CLIENT_ID = "b500432c-9287-4f79-8a49-fb0ac1181370"
DEFAULT_TOKEN_FILE = "/data/onx_tokens.json"


class OnxAuth:
    def __init__(self, token_file: str | None = None):
        self._token_file = Path(token_file or os.getenv("ONX_TOKEN_FILE", DEFAULT_TOKEN_FILE))
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at: float = 0
        self._load_tokens()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def get_token(self) -> str:
        if self._access_token and time.time() < self._expires_at - 60:
            return self._access_token
        if self._refresh_token:
            self._refresh()
            return self._access_token
        raise RuntimeError(
            "No OnX token available. Run `python -m sync.onx_login` to authenticate."
        )

    def store_tokens(self, access_token: str, refresh_token: str, expires_in: int):
        """Called by onx_login after a successful code exchange."""
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._expires_at = time.time() + expires_in
        self._save_tokens()
        logger.info("OnX tokens stored to %s", self._token_file)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _refresh(self):
        resp = requests.post(
            TOKEN_ENDPOINT,
            data={
                "grant_type": "refresh_token",
                "client_id": CLIENT_ID,
                "refresh_token": self._refresh_token,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        self._expires_at = time.time() + data.get("expires_in", 3600)
        if "refresh_token" in data:
            self._refresh_token = data["refresh_token"]
        self._save_tokens()
        logger.debug("OnX token refreshed")

    def _load_tokens(self):
        if not self._token_file.exists():
            return
        try:
            data = json.loads(self._token_file.read_text())
            self._access_token = data.get("access_token")
            self._refresh_token = data.get("refresh_token")
            self._expires_at = data.get("expires_at", 0)
        except Exception as exc:
            logger.warning("Could not load OnX token file: %s", exc)

    def _save_tokens(self):
        self._token_file.parent.mkdir(parents=True, exist_ok=True)
        self._token_file.write_text(
            json.dumps({
                "access_token": self._access_token,
                "refresh_token": self._refresh_token,
                "expires_at": self._expires_at,
            })
        )
