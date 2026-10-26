"""Signing in with Google (OpenID Connect, authorization code with PKCE): who is
this, by a verified email. Only name and email are asked for; nothing in Drive.

The ID token comes straight from Google's token endpoint over TLS, in exchange
for the code and the client secret, so it is trusted as Google's answer without
checking its signature (OpenID Connect Core 3.1.3.7); its issuer, audience,
expiry and nonce are still checked, and the email must be verified.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx2

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
ISSUERS = frozenset({"https://accounts.google.com", "accounts.google.com"})
SCOPE = "openid email profile"


class SignInError(Exception):
    """Google's answer can't be used; `detail` is for the log only."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class Identity:
    email: str  # verified by Google, lower case
    name: str | None


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def new_verifier() -> str:
    """PKCE: kept by the browser that starts (in a signed cookie), sent with the code."""
    return secrets.token_urlsafe(48)


def challenge(verifier: str) -> str:
    return _b64(hashlib.sha256(verifier.encode()).digest())


@dataclass(frozen=True)
class GoogleSignIn:
    client_id: str
    client_secret: str
    redirect_uri: str

    def authorization_url(self, state: str, nonce: str, verifier: str) -> str:
        return f"{AUTH_URL}?" + urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "scope": SCOPE,
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge(verifier),
                "code_challenge_method": "S256",
                "prompt": "select_account",
            }
        )

    async def identify(
        self, http: httpx2.AsyncClient, code: str, verifier: str, nonce: str
    ) -> Identity:
        """The code from Google's return → who signed in."""
        try:
            response = await http.post(
                TOKEN_URL,
                data={
                    "code": code,
                    "code_verifier": verifier,
                    "grant_type": "authorization_code",
                    "redirect_uri": self.redirect_uri,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
        except httpx2.TransportError as error:
            raise SignInError(f"token endpoint unreachable: {error!r}") from error
        if response.status_code >= 400:
            # Never log the request: it holds the code.
            raise SignInError(f"token endpoint {response.status_code}: {response.text[:300]}")
        token = response.json().get("id_token")
        if not token:
            raise SignInError("no id_token in Google's answer")
        return self.read(token, nonce)

    def read(self, id_token: str, nonce: str, now: float | None = None) -> Identity:
        """The ID token's claims, checked (see the module's note on signatures)."""
        try:
            payload = id_token.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        except (IndexError, ValueError) as error:
            raise SignInError("malformed id_token") from error
        now = time.time() if now is None else now
        if claims.get("iss") not in ISSUERS:
            raise SignInError(f"unexpected issuer {claims.get('iss')!r}")
        audience = claims.get("aud")
        if audience != self.client_id and not (
            isinstance(audience, list) and self.client_id in audience
        ):
            raise SignInError("id_token for another client")
        if float(claims.get("exp", 0)) < now:
            raise SignInError("id_token expired")
        if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
            raise SignInError("nonce mismatch")
        email = str(claims.get("email", "")).strip().lower()
        if not email or claims.get("email_verified") not in (True, "true"):
            raise SignInError("no verified email")
        return Identity(email=email, name=claims.get("name"))
