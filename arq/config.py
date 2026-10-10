"""Parse the per-project `_project` doc.

Format (a Google Doc, or a .txt/.md file):

    Title: Casa Jardim
    Client: Família Oliveira
    Location: Florianópolis, SC
    Current stage: 3
    Slug: casa-jardim

    Free-form description. Each line becomes a paragraph;
    lines starting with "- " or "* " become bullet points.

The header block is the "Key: value" lines at the top (blank lines between them
are fine); it ends at the first other line, or a line that is just "---".
Known keys (English or Portuguese) are used for behavior; every other key is
shown to clients as a project detail. Problems (a known key stranded in the
description, a repeated key, a file that isn't UTF-8) are collected in
`issues` for the dashboard instead of failing silently.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from .meetings import Meeting, build_meeting

_ALIASES = {
    "title": {"title", "titulo", "project", "projeto", "nome do projeto"},
    "slug": {"slug", "link", "url"},
    "current_stage": {"current stage", "stage", "etapa atual", "etapa", "fase atual", "fase"},
    "meeting_start": {"meeting start", "reuniao", "reuniao agendada", "inicio da reuniao"},
    "meeting_end": {"meeting end", "fim da reuniao"},
    "meeting_title": {"meeting title", "assunto da reuniao"},
    "meeting_location": {"meeting location", "local da reuniao"},
    "meeting_link": {"meeting link", "link da reuniao"},
}
_FIELD_RE = re.compile(r"^([^:]{1,40}):\s*(.*)$")
_BULLET_RE = re.compile(r"^\s*[-*•●]\s+(.*)$")


def _norm_key(key: str) -> str:
    key = unicodedata.normalize("NFKD", key).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", key).strip().lower()


_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def is_valid_slug(value: str) -> bool:
    """Lowercase letters, digits and single hyphens; no spaces or accents."""
    return bool(_SLUG_RE.match(value))


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


@dataclass
class DescriptionBlock:
    kind: str  # "p" or "ul"
    items: list[str]


@dataclass
class ProjectConfig:
    title: str | None = None
    slug: str | None = None
    current_stage: str | None = None
    meeting_start: str | None = None
    meeting_end: str | None = None
    meeting_title: str | None = None
    meeting_location: str | None = None
    meeting_link: str | None = None
    meeting: Meeting | None = None
    details: list[tuple[str, str]] = field(default_factory=list)
    description: list[DescriptionBlock] = field(default_factory=list)
    slug_invalid: bool = False
    # Problems found while parsing, as (i18n key, params). Shown in the dashboard.
    issues: list[tuple[str, dict]] = field(default_factory=list)


def _known_attr(label: str) -> str | None:
    key = _norm_key(label)
    return next((attr for attr, names in _ALIASES.items() if key in names), None)


def parse_config(text: str) -> ProjectConfig:
    """Lenient parser: the header is every `Key: value` line from the top, blank
    lines between them allowed; it ends at the first other line (or `---`)."""
    cfg = ProjectConfig()
    if "\x00" in text or "\ufffd" in text:
        cfg.issues.append(("cfg.encoding", {}))
        text = text.replace("\x00", "")
    lines = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").split("\n")

    seen: set[str] = set()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line == "---":
            i += 1
            break
        m = _FIELD_RE.match(line)
        if not m or m.group(1).strip().lower() in {"http", "https"}:
            break
        label, value = m.group(1).strip(), m.group(2).strip()
        attr = _known_attr(label)
        if attr:
            if attr in seen:
                cfg.issues.append(("cfg.duplicate_key", {"key": label}))
            seen.add(attr)
            setattr(cfg, attr, value or None)
        elif value:
            cfg.details.append((label, value))
        i += 1

    if cfg.slug is not None and not is_valid_slug(cfg.slug):
        # Never rewrite what the architect typed: flag it and don't publish.
        cfg.issues.append(("cfg.invalid_slug", {"value": cfg.slug}))
        cfg.slug_invalid = True

    for n, raw in enumerate(lines[i:], start=i + 1):
        line = raw.strip()
        if not line:
            continue
        m = _FIELD_RE.match(line)
        if m and _known_attr(m.group(1)):
            cfg.issues.append(("cfg.key_in_description", {"key": m.group(1).strip(), "line": n}))
            continue  # never show a config line to clients
        bullet = _BULLET_RE.match(line)
        if bullet:
            if cfg.description and cfg.description[-1].kind == "ul":
                cfg.description[-1].items.append(bullet.group(1))
            else:
                cfg.description.append(DescriptionBlock("ul", [bullet.group(1)]))
        else:
            cfg.description.append(DescriptionBlock("p", [line]))
    try:
        cfg.meeting = build_meeting(cfg.meeting_start, cfg.meeting_end, cfg.meeting_title,
                                   cfg.meeting_location, cfg.meeting_link)
    except ValueError as exc:
        cfg.issues.append(("cfg.invalid_meeting", {"detail": str(exc)}))
    return cfg
