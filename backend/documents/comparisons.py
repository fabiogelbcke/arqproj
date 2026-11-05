"""Before-and-after comparisons from names (A46).

Like versions (A25), nothing about a comparison is stored: two images of one
folder are a comparison when their names say so. `Cozinha (antes).jpg` and
`Cozinha (depois).jpg` are the comparison "Cozinha"; the page shows it as one
card that opens on a slider between them. A side's label is in its name too:
`Cozinha (antes - Projeto).jpg` reads "Projeto" where the slider would say
"Antes". English names work the same: `Kitchen (before).jpg`, `(after)`.

Each side is a document of its own, so it keeps its versions (`Cozinha
(antes) v2.jpg`): the version token comes after the marker. A comparison takes
exactly one "before" and one "after" document of the same title; a second
"before", a clash or a file that isn't an image leaves those files on their own
cards, as plain files, until the names are put right.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from backend.documents import versions

LABEL_MAX = 40
TITLE_MAX = 120


class Side(StrEnum):
    BEFORE = "before"
    AFTER = "after"


# The marker's words, in the languages the site speaks (Locale): the app writes
# the office's, and reads either.
WORDS = {"antes": Side.BEFORE, "before": Side.BEFORE, "depois": Side.AFTER, "after": Side.AFTER}
WRITTEN = {"pt-BR": {Side.BEFORE: "antes", Side.AFTER: "depois"}, "en": {s: s.value for s in Side}}

_MARKER = re.compile(
    r"^(?P<title>.*?\S)\s*\(\s*(?P<word>antes|depois|before|after)"
    r"(?:\s*[-–—:]\s*(?P<label>[^()]*?))?\s*\)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Marked:
    """A document's base name read for a comparison: "Cozinha (antes - Projeto)"."""

    title: str  # "Cozinha"
    side: Side
    label: str | None  # "Projeto"; None: the page's own word ("Antes")

    @property
    def key(self) -> str:
        """What the two sides' titles share: case and separators don't count."""
        return re.sub(r"[\s_\-–—.]+", " ", self.title).strip().casefold()


def marked(base: str) -> Marked | None:
    """The comparison a name without its version or extension belongs to, if any."""
    found = _MARKER.match(base.strip())
    if found is None:
        return None
    label = (found["label"] or "").strip() or None
    return Marked(found["title"].strip(), WORDS[found["word"].casefold()], label)


@dataclass
class Comparison:
    title: str  # the "before" side's, as written
    before: versions.Document
    after: versions.Document
    before_label: str | None
    after_label: str | None


def pair(documents: list[versions.Document], is_image) -> list[versions.Document | Comparison]:
    """One folder's documents with each comparison in place of its two sides, at
    its "before" side's place. `is_image` says whether a file shows in the page
    itself (only images compare)."""
    sides: dict[str, dict[Side, list[tuple[versions.Document, Marked]]]] = {}
    for document in documents:
        found = marked(document.named.base)
        if found is not None:
            sides.setdefault(found.key, {}).setdefault(found.side, []).append((document, found))
    paired: dict[int, Comparison | None] = {}  # by id of each side's document
    for both in sides.values():
        befores, afters = both.get(Side.BEFORE, []), both.get(Side.AFTER, [])
        if len(befores) != 1 or len(afters) != 1:
            continue  # unclear which goes with which: each file shows on its own
        if any(d.clash or not is_image(d.current) for d, _m in befores + afters):
            continue  # a clash or a file that isn't an image: the names need fixing first
        (before, b), (after, a) = befores[0], afters[0]
        comparison = Comparison(b.title, before, after, b.label, a.label)
        paired[id(before)] = comparison
        paired[id(after)] = None  # shown on the "before" side's card
    entries: list[versions.Document | Comparison] = []
    for document in documents:
        if id(document) not in paired:
            entries.append(document)
        elif (comparison := paired[id(document)]) is not None:
            entries.append(comparison)
    return entries


def find(entries: list[versions.Document | Comparison], key: str) -> Comparison | None:
    """The folder's comparison of this title (as `Marked.key`), if any."""
    return next(
        (e for e in entries if isinstance(e, Comparison) and title_key(e.title) == key), None
    )


def title_key(title: str) -> str:
    return Marked(title, Side.BEFORE, None).key


def clean_label(label: str | None) -> str | None:
    """A label as it can go in a name: no brackets (they'd end the marker), one
    line. Empty is no label."""
    if label is None:
        return None
    cleaned = re.sub(r"[()\[\]/\\]", "", " ".join(label.split())).strip()
    return cleaned[:LABEL_MAX] or None


def base_name(title: str, side: Side, label: str | None, locale: str) -> str:
    """A side's base name, which `marked` reads back: "Cozinha (antes - Projeto)"."""
    word = WRITTEN.get(locale, WRITTEN["pt-BR"])[side]
    return f"{title} ({word} - {label})" if label else f"{title} ({word})"


def reads_back(title: str, side: Side, label: str | None, base: str) -> bool:
    """Whether a name written for this side reads back as it, after the version
    is taken off as the page does (A25): a label ending like a version ("Projeto
    v2") would lose it and the marker's bracket with it."""
    found = marked(versions.parse(base + ".jpg").base)
    return found is not None and (found.key, found.side, found.label) == (
        title_key(title),
        side,
        label,
    )


def renamed(document: versions.Document, base: str) -> list[tuple[str, str]]:
    """(item id, new name) for every version of a side, so they stay one
    document under the new base: `Cozinha (antes - Obra) v2.jpg`. Google formats
    never compare (they aren't images), so Drive's name is the shown name."""
    names = []
    for number, item in document.versions:
        extension = versions.parse(item.name).extension
        has_token = versions.parse(item.name).number is not None
        names.append((item.id, f"{base} v{number}{extension}" if has_token else base + extension))
    return names
