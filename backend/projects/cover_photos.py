"""The stock cover photos bundled with the app (plan section 10).

A new project starts with one of them, picked at random, as its real cover;
staff can later choose another from the same set or upload their own. The
painel also shows one, chosen per project, while a project has no cover.

Each photo is a 3:2 JPEG in two sizes: `full` (the cover itself, at most
1800x1200) and `small` (720x480, for cards and the picker). `LICENSES.json`
records where each one comes from.
"""

from __future__ import annotations

import hashlib
import random
from enum import StrEnum
from functools import cache
from pathlib import Path

PHOTOS_DIR = Path(__file__).parent / "covers"


class PhotoSize(StrEnum):
    FULL = "full"
    SMALL = "small"


@cache
def cover_photo_names() -> tuple[str, ...]:
    """Every photo's name (`capa-01`), in order."""
    return tuple(sorted(p.stem for p in (PHOTOS_DIR / PhotoSize.FULL).glob("*.jpg")))


def cover_photo(name: str, size: PhotoSize = PhotoSize.FULL) -> Path | None:
    """The photo's file, or None for a name that is not one of them."""
    if name not in cover_photo_names():
        return None
    return PHOTOS_DIR / size / f"{name}.jpg"


def random_cover_photo() -> str:
    return random.choice(cover_photo_names())


@cache
def cover_photo_version(name: str, size: PhotoSize) -> str:
    """A short fingerprint of the file, for its address: browsers keep a photo
    for a day, so a name that now holds another picture needs a new address."""
    path = cover_photo(name, size)
    assert path is not None
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
