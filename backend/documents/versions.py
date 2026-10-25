"""Versions from names (A25, revised 25 Oct 2026; plan section 12).

Nothing about files is stored: each time a folder is listed, its files are
grouped by name. `Planta.pdf`, `Planta v2.pdf` and `Planta v3.pdf` in one folder
are one document, "Planta.pdf", whose current version is the highest (v3). An
unnumbered name counts as v1, and v1 is never shown on its own: a version shows
from v2 (Fabio, 25 Oct 2026: "for v1 we can skip").

Only a `v` number at the end of the name groups: `v2`, `_v02`, `(v3)`. Nothing
else marks a version, not `rev B` either (Fabio, 25 Oct 2026: "just use v1, v2,
v3"); anything else, like `Planta_final_v2_final.pdf`, is a document of its
own. The extension must match too: `Planta v2.dwg` is not a version of
`Planta.pdf`. Two files claiming the same version are never merged: each shows
on its own, flagged for staff, who rename one. A wrong grouping is fixed by
renaming the file, nothing else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from backend.storage.base import StorageItem

# "Atualizado" on a file with a new version, for a few days (Fabio, 25 Oct 2026).
UPDATED_DAYS = 7

_TOKEN = re.compile(
    r"^(?P<base>.*?)[\s_\-–—.(\[]+"
    r"v\.?\s?(?P<number>\d{1,3})"
    r"[)\]]?$",
    re.IGNORECASE,
)


def shown_name(item: StorageItem) -> str:
    """The name the page shows: a Google format downloads as PDF."""
    return f"{item.name}.pdf" if item.is_native else item.name


@dataclass(frozen=True)
class Name:
    """A file name read for its version."""

    base: str  # as written, without the version or the extension: "Planta"
    extension: str  # with its dot, or "": ".pdf"
    number: int | None  # None: the name carries no version

    @property
    def key(self) -> str:
        """What names of one document share: case and separators don't count."""
        return re.sub(r"[\s_\-–—.]+", " ", self.base).strip().casefold() + self.extension.casefold()

    @property
    def version(self) -> int:
        return self.number or 1  # an unnumbered original is v1


def _split(name: str) -> tuple[str, str]:
    if "." in name[1:]:
        stem, extension = name.rsplit(".", 1)
        if 1 <= len(extension) <= 5 and extension.isalnum():
            return stem, f".{extension}"
    return name, ""


def parse(name: str) -> Name:
    stem, extension = _split(name)
    found = _TOKEN.match(stem)
    if found and found["base"].strip():
        number = int(found["number"])
        if number >= 1:
            return Name(found["base"].strip(), extension, number)
    return Name(stem.strip(), extension, None)


@dataclass
class Document:
    """One document of a folder: its versions, the current one first."""

    versions: list[tuple[int, StorageItem]]
    named: Name  # the current version's name
    numbered: bool  # its names carry versions, or it has more than one
    clash: bool = False  # another file of the folder claims the same version

    @property
    def current(self) -> StorageItem:
        return self.versions[0][1]

    @property
    def version(self) -> int | None:
        """The current version's number, from v2: a file still on its first
        version shows none, whatever its name."""
        number = self.versions[0][0]
        return number if self.numbered and number >= 2 else None

    @property
    def name(self) -> str:
        """The clean name the page shows ("Planta.pdf"); a clashing file keeps its own."""
        if self.clash or not self.numbered:
            return shown_name(self.current)
        return self.named.base + self.named.extension

    @property
    def older(self) -> list[tuple[int, StorageItem]]:
        return self.versions[1:]

    def updated(self, now: datetime) -> bool:
        """A new version (v2 or later) from the last few days: "Atualizado"."""
        return self.version is not None and self.current.modified_at > now - timedelta(
            days=UPDATED_DAYS
        )


def group(items: list[StorageItem]) -> list[Document]:
    """One folder's files as documents, in the order their first file was listed."""
    by_key: dict[str, list[tuple[Name, StorageItem]]] = {}
    for item in items:
        name = parse(shown_name(item))
        by_key.setdefault(name.key, []).append((name, item))
    documents = []
    for named in by_key.values():
        numbers = [name.version for name, _item in named]
        if len(set(numbers)) < len(numbers):
            # Never merged: each on its own, so staff see which to rename.
            documents.extend(
                Document([(name.version, item)], name, numbered=False, clash=True)
                for name, item in named
            )
            continue
        named.sort(key=lambda pair: pair[0].version, reverse=True)
        documents.append(
            Document(
                [(name.version, item) for name, item in named],
                named[0][0],
                numbered=len(named) > 1 or named[0][0].number is not None,
            )
        )
    return documents


def same_document(documents: list[Document], name: str) -> Document | None:
    """The document an uploaded name would join, if any (by name, as `group`)."""
    key = parse(name).key
    return next((d for d in documents if d.named.key == key), None)


def next_name(documents: list[Document], document: Document) -> str:
    """The name its new version is saved with in Drive: "Planta v4.pdf", one past
    every version of that name in the folder (clashing ones too)."""
    highest = max(d.versions[0][0] for d in documents if d.named.key == document.named.key)
    return f"{document.named.base} v{highest + 1}{document.named.extension}"


def apart(documents: list[Document], name: str) -> str:
    """A name that joins no document: "Planta (2).pdf" next to "Planta.pdf"."""
    if same_document(documents, name) is None:
        return name
    stem, extension = _split(name)
    n = 2
    while same_document(documents, f"{stem} ({n}){extension}") is not None:
        n += 1
    return f"{stem} ({n}){extension}"
