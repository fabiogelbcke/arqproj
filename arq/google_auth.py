"""Service-account auth for the Drive API, without the Google SDK.

Signs a JWT with the service account's private key and exchanges it for a
short-lived access token (OAuth 2.0 JWT bearer flow). Tokens are cached until
~1 minute before expiry.
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time

import jwt
import requests

SCOPE = "https://www.googleapis.com/auth/drive.readonly"
DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"


class ServiceAccountAuth:
    def __init__(self, info: dict):
        try:
            self.email = info["client_email"]
            self.private_key = info["private_key"]
        except KeyError as e:
            raise RuntimeError(f"service account key is missing {e.args[0]!r}") from None
        self.token_uri = info.get("token_uri") or DEFAULT_TOKEN_URI
        self._token: str | None = None
        self._expires_at = 0.0
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls) -> "ServiceAccountAuth":
        """GOOGLE_SERVICE_ACCOUNT_KEY (raw JSON or base64 JSON) wins over
        GOOGLE_APPLICATION_CREDENTIALS (path to the JSON key file)."""
        raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY", "").strip()
        path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        if raw:
            info = json.loads(raw if raw.startswith("{") else base64.b64decode(raw))
        elif path:
            with open(path, encoding="utf-8") as fh:
                info = json.load(fh)
        else:
            raise RuntimeError(
                "No service account configured. Set GOOGLE_APPLICATION_CREDENTIALS "
                "to the key file path, or GOOGLE_SERVICE_ACCOUNT_KEY to its JSON."
            )
        return cls(info)

    def token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._expires_at - 60:
                return self._token
            now = int(time.time())
            assertion = jwt.encode(
                {
                    "iss": self.email,
                    "scope": SCOPE,
                    "aud": self.token_uri,
                    "iat": now,
                    "exp": now + 3600,
                },
                self.private_key,
                algorithm="RS256",
            )
            resp = requests.post(
                self.token_uri,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
                timeout=15,
            )
            if not resp.ok:
                raise RuntimeError(
                    f"token exchange failed ({resp.status_code}): {resp.text[:300]}"
                )
            data = resp.json()
            self._token = data["access_token"]
            self._expires_at = now + int(data.get("expires_in", 3600))
            return self._token
