"""Service-account auth for the Drive API, without the Google SDK.

Two token sources, both cached until ~1 minute before expiry:

- ServiceAccountAuth: signs a JWT with a downloaded key and exchanges it for an
  access token (OAuth 2.0 JWT bearer flow). Used for local development.
- MetadataServerAuth: on Cloud Run, asks the metadata server for a token for
  the service account attached to the service. No key file exists anywhere.

get_auth() picks one: an explicit key wins; otherwise the metadata server.
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
GCS_SCOPE = "https://www.googleapis.com/auth/devstorage.read_write"
DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"


class ServiceAccountAuth:
    def __init__(self, info: dict, scope: str = SCOPE):
        self.scope = scope
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
    def from_env(cls, scope: str = SCOPE) -> "ServiceAccountAuth":
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
        return cls(info, scope)

    def token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._expires_at - 60:
                return self._token
            now = int(time.time())
            assertion = jwt.encode(
                {
                    "iss": self.email,
                    "scope": self.scope,
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


METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
)


class MetadataServerAuth:
    """Token for the service account attached to the Cloud Run service."""

    def __init__(self, url: str | None = None, scope: str = SCOPE):
        self.scope = scope
        self.url = url or os.environ.get("METADATA_TOKEN_URL") or METADATA_TOKEN_URL
        self._token: str | None = None
        self._expires_at = 0.0
        self._lock = threading.Lock()

    def token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._expires_at - 60:
                return self._token
            resp = requests.get(
                self.url,
                params={"scopes": self.scope},
                headers={"Metadata-Flavor": "Google"},
                timeout=10,
            )
            if not resp.ok:
                raise RuntimeError(f"metadata server token request failed ({resp.status_code}): {resp.text[:300]}")
            data = resp.json()
            self._token = data["access_token"]
            self._expires_at = time.time() + int(data.get("expires_in", 3600))
            return self._token


def get_auth(scope: str = SCOPE):
    if os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY", "").strip() or os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS", ""
    ).strip():
        return ServiceAccountAuth.from_env(scope)
    if os.environ.get("K_SERVICE") or os.environ.get("USE_METADATA_SERVER"):
        return MetadataServerAuth(scope=scope)  # K_SERVICE is set by Cloud Run
    raise RuntimeError(
        "No Google credentials. Locally, set GOOGLE_APPLICATION_CREDENTIALS to the key file path "
        "(or GOOGLE_SERVICE_ACCOUNT_KEY to its JSON). On Cloud Run, the attached service account is used."
    )
