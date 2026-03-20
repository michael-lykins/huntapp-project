"""
One-time OnX login helper.

Because OnX's redirect_uri is locked to https://webmap.onxmaps.com/auth/callback,
the PKCE browser flow can't redirect back to localhost.  The recommended approach is
to paste the localStorage OIDC token from the browser DevTools console.

Usage (paste-from-browser, preferred):
    python -m sync.onx_login --paste

    Then in the OnX webmap browser tab open DevTools → Console and run:
        copy(localStorage.getItem('oidc.user:https://identity.onxmaps.com:b500432c-9287-4f79-8a49-fb0ac1181370'))
    Paste the output when prompted.

Or inside the sync container:
    docker exec -it sync python -m sync.onx_login --paste
"""
import base64
import hashlib
import http.server
import logging
import os
import secrets
import threading
import urllib.parse
import webbrowser

import requests

from .onx_auth import CLIENT_ID, TOKEN_ENDPOINT, OnxAuth

logger = logging.getLogger(__name__)

AUTH_ENDPOINT = "https://identity.onxmaps.com/oauth2/auth"
REDIRECT_URI = "http://localhost:9876/callback"
SCOPES = "openid email profile internal"

# ── PKCE helpers ─────────────────────────────────────────────────────────────

def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


# ── Local callback server ─────────────────────────────────────────────────────

_captured: dict = {}
_server_ready = threading.Event()


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/callback":
            params = urllib.parse.parse_qs(parsed.query)
            _captured["code"] = params.get("code", [None])[0]
            _captured["error"] = params.get("error", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<h2>OnX login successful!</h2>"
                b"<p>You can close this tab and return to the terminal.</p>"
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass  # suppress access log noise


def _run_server(server: http.server.HTTPServer):
    _server_ready.set()
    server.handle_request()  # handle exactly one request then stop


# ── Main ──────────────────────────────────────────────────────────────────────

def login():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)

    auth_url = (
        f"{AUTH_ENDPOINT}"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&scope={urllib.parse.quote(SCOPES)}"
        f"&state={state}"
        f"&code_challenge={challenge}"
        f"&code_challenge_method=S256"
    )

    server = http.server.HTTPServer(("127.0.0.1", 9876), _CallbackHandler)
    t = threading.Thread(target=_run_server, args=(server,), daemon=True)
    t.start()
    _server_ready.wait()

    print("\n── OnX Login ────────────────────────────────────────────")
    print("Opening your browser to log in to OnX…")
    print(f"\nIf the browser does not open, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    t.join(timeout=120)

    if not _captured.get("code"):
        error = _captured.get("error", "timeout or unknown error")
        print(f"\n✗ Login failed: {error}")
        return

    print("✓ Authorization code received, exchanging for tokens…")

    resp = requests.post(
        TOKEN_ENDPOINT,
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": _captured["code"],
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    if "access_token" not in data:
        print(f"\n✗ Token exchange failed: {data}")
        return

    auth = OnxAuth()
    auth.store_tokens(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token", ""),
        expires_in=data.get("expires_in", 3600),
    )

    token_file = os.getenv("ONX_TOKEN_FILE", "/data/onx_tokens.json")
    print(f"\n✓ Tokens saved to {token_file}")
    print("  OnX sync is now ready to run.\n")


def inject_from_paste():
    """
    Accept the OIDC JSON pasted from the browser DevTools console and store it.

    In the OnX webmap browser tab, open DevTools → Console and run:
        copy(localStorage.getItem('oidc.user:https://identity.onxmaps.com:b500432c-9287-4f79-8a49-fb0ac1181370'))
    Then paste the copied text when prompted here.
    """
    import json, sys, time

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("\n── OnX Token Paste ──────────────────────────────────────────")
    print("In your OnX webmap browser tab, open DevTools → Console and run:")
    print()
    print("  copy(localStorage.getItem('oidc.user:https://identity.onxmaps.com:b500432c-9287-4f79-8a49-fb0ac1181370'))")
    print()
    print("Then paste the result below and press Enter (then Ctrl-D or Ctrl-Z+Enter):")
    print()

    lines = []
    try:
        for line in sys.stdin:
            lines.append(line)
    except KeyboardInterrupt:
        pass

    raw = "".join(lines).strip()
    if not raw:
        print("\n✗ No input received.")
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"\n✗ Invalid JSON: {e}")
        return

    access_token = data.get("access_token")
    expires_at = data.get("expires_at")
    refresh_token = data.get("refresh_token")

    if not access_token:
        print("\n✗ No access_token in pasted data.")
        return

    if expires_at and time.time() > expires_at:
        print(f"\n✗ Token already expired (expires_at={expires_at}). Please log in again and re-paste.")
        return

    auth = OnxAuth()
    auth._access_token = access_token
    auth._refresh_token = refresh_token
    auth._expires_at = float(expires_at) if expires_at else time.time() + 1800
    auth._save_tokens()

    token_file = os.getenv("ONX_TOKEN_FILE", "/data/onx_tokens.json")
    mins_left = max(0, int((auth._expires_at - time.time()) / 60))
    print(f"\n✓ Token stored to {token_file} (expires in ~{mins_left} min)")
    print("  Run `POST /trigger/onx` to sync OnX data now.\n")


if __name__ == "__main__":
    import sys
    if "--paste" in sys.argv:
        inject_from_paste()
    else:
        login()
