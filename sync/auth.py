"""
Tactacam / Reveal Cognito authentication.

Tactacam uses AWS Cognito USER_PASSWORD_AUTH (no SRP, no client secret).
Client ID: 6r9tpojvgvkci5trla0ip14mon
"""
import os
import time
import logging
import requests

logger = logging.getLogger(__name__)

COGNITO_URL = "https://cognito-idp.us-east-1.amazonaws.com/"
CLIENT_ID = "6r9tpojvgvkci5trla0ip14mon"


class TactacamAuth:
    def __init__(self):
        self.username = os.environ["TACTACAM_USERNAME"]
        self.password = os.environ["TACTACAM_PASSWORD"]
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at: float = 0

    def get_token(self) -> str:
        if self._access_token and time.time() < self._expires_at - 60:
            return self._access_token
        if self._refresh_token:
            try:
                self._refresh()
                return self._access_token
            except Exception:
                logger.warning("Token refresh failed, re-authenticating")
        self._authenticate()
        return self._access_token

    def _authenticate(self):
        resp = requests.post(
            COGNITO_URL,
            headers={
                "Content-Type": "application/x-amz-json-1.1",
                "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
            },
            json={
                "AuthFlow": "USER_PASSWORD_AUTH",
                "ClientId": CLIENT_ID,
                "AuthParameters": {
                    "USERNAME": self.username,
                    "PASSWORD": self.password,
                },
            },
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json()["AuthenticationResult"]
        self._store(result)
        logger.info("Tactacam auth: authenticated as %s", self.username)

    def _refresh(self):
        resp = requests.post(
            COGNITO_URL,
            headers={
                "Content-Type": "application/x-amz-json-1.1",
                "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
            },
            json={
                "AuthFlow": "REFRESH_TOKEN_AUTH",
                "ClientId": CLIENT_ID,
                "AuthParameters": {"REFRESH_TOKEN": self._refresh_token},
            },
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json()["AuthenticationResult"]
        self._store(result)
        logger.debug("Tactacam auth: token refreshed")

    def _store(self, result: dict):
        self._access_token = result["AccessToken"]
        self._expires_at = time.time() + result["ExpiresIn"]
        if "RefreshToken" in result:
            self._refresh_token = result["RefreshToken"]
