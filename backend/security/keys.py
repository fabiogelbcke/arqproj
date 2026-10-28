"""Signing and encryption with keys derived from one app secret (APP_SECRET).

Each purpose gets its own key (HKDF), so a signature can never be replayed as a
ciphertext or the other way round. Ciphertexts carry a version prefix, so the
key or algorithm can change later (e.g. to Cloud KMS) with old values still
readable.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_VERSION = "v1"


class BadToken(Exception):
    """A signed note or ciphertext that is forged, tampered with or expired."""


def _key(secret: str, purpose: str) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=purpose.encode()).derive(
        secret.encode()
    )


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def keyed_hash(secret: str, purpose: str, data: str) -> str:
    """A hex digest of `data` that only the app can recompute (HMAC-SHA256)."""
    return hmac.new(_key(secret, purpose), data.encode(), hashlib.sha256).hexdigest()


def sign(secret: str, purpose: str, payload: dict, ttl_seconds: int) -> str:
    """A tamper-proof note that expires (e.g. OAuth `state`)."""
    body = _b64(json.dumps(payload | {"exp": int(time.time()) + ttl_seconds}).encode())
    mac = hmac.new(_key(secret, purpose), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(mac)}"


def verify(secret: str, purpose: str, token: str) -> dict:
    try:
        body, mac = token.split(".")
        expected = hmac.new(_key(secret, purpose), body.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_unb64(mac), expected):
            raise BadToken("signature")
        payload = json.loads(_unb64(body))
    except (ValueError, TypeError) as error:
        raise BadToken("malformed") from error
    if payload.get("exp", 0) < time.time():
        raise BadToken("expired")
    return payload


def encrypt(secret: str, purpose: str, plaintext: str) -> str:
    nonce = os.urandom(12)
    sealed = AESGCM(_key(secret, purpose)).encrypt(nonce, plaintext.encode(), purpose.encode())
    return f"{_VERSION}:{_b64(nonce + sealed)}"


def decrypt(secret: str, purpose: str, ciphertext: str) -> str:
    try:
        version, data = ciphertext.split(":", 1)
        if version != _VERSION:
            raise BadToken("version")
        raw = _unb64(data)
        return AESGCM(_key(secret, purpose)).decrypt(raw[:12], raw[12:], purpose.encode()).decode()
    except BadToken:
        raise
    except Exception as error:  # wrong key, tampered bytes
        raise BadToken("undecryptable") from error
