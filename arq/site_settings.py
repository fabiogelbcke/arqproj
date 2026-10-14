"""Office settings edited from the painel: the office name and its logo.

Stored as one small JSON object next to the Drive connection state (a local file
in development, the same GCS bucket on Cloud Run). Environment variables and the
`_site/logo` file in Drive remain the defaults when nothing has been saved.
"""

from __future__ import annotations

import base64
import os
import threading
import time

from .oauth_drive import FileStateStore, GcsStateStore

LOGO_MAX_BYTES = 512 * 1024


class InvalidLogo(ValueError):
    """The upload is not an image we accept. `key` is the i18n message to show."""

    def __init__(self, key: str):
        super().__init__(key)
        self.key = key


def sniff_logo(data: bytes) -> str:
    """The logo's media type, judged from its bytes rather than the browser's claim."""
    if len(data) > LOGO_MAX_BYTES:
        raise InvalidLogo("settings.logo_too_big")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    head = data[:1024].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in head):
        return "image/svg+xml"
    raise InvalidLogo("settings.logo_bad_type")


def default_settings_store():
    bucket = os.environ.get("PORTAL_STATE_BUCKET", "").strip()
    if bucket:
        return GcsStateStore(bucket, name="portal-settings.json")
    return FileStateStore(os.environ.get("PORTAL_SETTINGS_FILE", ".portal-settings.json"))


class SiteSettings:
    """Read on every page, written rarely, so reads are cached for a short while.

    With several Cloud Run instances, a change shows up on the others within `ttl`.
    """

    def __init__(self, store=None, default_name: str = "", ttl: float = 30.0):
        self.store = store or default_settings_store()
        self.default_name = default_name
        self.ttl = ttl
        self._cached: dict | None = None
        self._loaded_at = 0.0
        self._lock = threading.Lock()

    def _data(self) -> dict:
        with self._lock:
            if self._cached is not None and time.monotonic() - self._loaded_at < self.ttl:
                return self._cached
        try:
            data = self.store.load()
        except Exception:
            # Settings must never take a page down: fall back to the defaults.
            data = {}
        with self._lock:
            self._cached, self._loaded_at = data, time.monotonic()
        return data

    def name(self) -> str:
        return self._data().get("name") or self.default_name

    def logo(self) -> tuple[bytes, str] | None:
        logo = self._data().get("logo")
        if not logo:
            return None
        return base64.b64decode(logo["data"]), logo["type"]

    def logo_version(self) -> str:
        """Changes whenever the logo does, so browsers fetch the new one."""
        logo = self._data().get("logo")
        return logo.get("version", "") if logo else ""

    def save(self, name: str, logo: bytes | None = None, remove_logo: bool = False) -> None:
        # Validate before touching storage, so a bad upload changes nothing.
        logo_type = sniff_logo(logo) if logo else None
        data = dict(self.store.load())
        data["name"] = name
        if remove_logo:
            data.pop("logo", None)
        elif logo:
            data["logo"] = {
                "type": logo_type,
                "data": base64.b64encode(logo).decode("ascii"),
                "version": str(int(time.time())),
            }
        self.store.save(data)
        with self._lock:
            self._cached, self._loaded_at = data, time.monotonic()
