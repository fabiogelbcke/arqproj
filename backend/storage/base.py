"""What the app needs from a file store, whichever store it is.

Read-only for now: uploads arrive with slice 3, change feeds with slice 4.
Failures are a `StorageError` with a `StorageProblem`; the provider's own text
stays in the log and never reaches a screen (AGENTS.md, "User-facing errors").
"""

from __future__ import annotations

import unicodedata
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

FOLDER_TYPE = "application/vnd.google-apps.folder"
# A link to another item; nothing to download itself. Not followed here: whoever
# follows one (downloads, step 2.5) must first check the target lies inside the
# office's own folder, since one reader identity can see several offices' files.
SHORTCUT_TYPE = "application/vnd.google-apps.shortcut"
# Google's own formats (Docs, Sheets, Slides…) have no file to download; they are
# exported as PDF.
NATIVE_PREFIX = "application/vnd.google-apps."


class StorageProblem(StrEnum):
    NOT_FOUND = "not_found"  # also: an id that is not well formed
    NO_ACCESS = "no_access"  # the reader identity was not given access
    UNAVAILABLE = "unavailable"  # the provider failed, even after retries
    RATE_LIMITED = "rate_limited"  # still throttled after retries


class StorageError(Exception):
    """`str()` is only the problem code. `detail` holds the provider's own words
    for the server log at the request boundary, never for a screen."""

    def __init__(self, problem: StorageProblem, detail: str = "") -> None:
        super().__init__(problem.value)
        self.problem = problem
        self.detail = detail


@dataclass(frozen=True)
class StorageItem:
    id: str
    name: str
    mime_type: str
    size: int | None  # None for folders and Google-native documents
    modified_at: datetime
    checksum: str | None = None  # MD5 where the provider has one
    shortcut_target: str | None = None  # the item a shortcut points to

    @property
    def is_folder(self) -> bool:
        return self.mime_type == FOLDER_TYPE

    @property
    def is_shortcut(self) -> bool:
        return self.mime_type == SHORTCUT_TYPE

    @property
    def is_native(self) -> bool:
        """A Google format with no file of its own, exported as PDF to download."""
        return (
            self.mime_type.startswith(NATIVE_PREFIX) and not self.is_folder and not self.is_shortcut
        )


@dataclass(frozen=True)
class Download:
    """A file's bytes, streamed. For a native document: its PDF export."""

    media_type: str
    size: int | None
    chunks: AsyncIterator[bytes]


class Storage(Protocol):
    async def list_folder(self, folder_id: str) -> list[StorageItem]:
        """The folder's direct children (not trashed), sorted by name."""
        ...

    async def get(self, item_id: str) -> StorageItem: ...

    async def download(self, item: StorageItem) -> Download: ...

    async def thumbnail(self, item: StorageItem, size: int = 640) -> bytes | None:
        """A small preview image, or None where the store has none."""
        ...


def sorted_items(items: list[StorageItem]) -> list[StorageItem]:
    """By name as people read it: ignoring case and accents ("área" before "Planta")."""
    return sorted(items, key=lambda item: (_reading_order(item.name), item.id))


def _reading_order(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()
