"""Parse the per-project `_project` doc.

Format (a Google Doc, or a .txt/.md file):

    Title: Casa Jardim
    Client: Família Oliveira
    Location: Florianópolis, SC
    Current stage: 3
    Slug: casa-jardim

    Free-form description. Each line becomes a paragraph;
    lines starting with "- " or "* " become bullet points.

The header block is "Key: value" lines up to the first blank line (or a line
that is just "---"). Known keys (English or Portuguese) are used for behavior;
every other key is shown to clients as a project detail.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

_ALIASES = {
    "title": {"title", "titulo", "project", "projeto", "nome do projeto"},
    "slug": {"slug", "link", "url"},
    "current_stage": {"current stage", "stage", "etapa atual", "etapa", "fase atual", "fase"},
}
_FIELD_RE = re.compile(r"^([^:]{1,40}):\s*(.*)$")
_BULLET_RE = re.compile(r"^\s*[-*•●]\s+(.*)$")


def _norm_key(key: str) -> str:
    key = unicodedata.normalize("NFKD", key).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", key).strip().lower()


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
    details: list[tuple[str, str]] = field(default_factory=list)
    description: list[DescriptionBlock] = field(default_factory=list)


def parse_config(text: str) -> ProjectConfig:
    cfg = ProjectConfig()
    lines = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n").split("\n")

    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    while i < len(lines):
        line = lines[i].strip()
        if not line or line == "---":
            i += 1
            break
        m = _FIELD_RE.match(line)
        if not m or m.group(1).strip().lower() in {"http", "https"}:
            break
        label, value = m.group(1).strip(), m.group(2).strip()
        key = _norm_key(label)
        for attr, names in _ALIASES.items():
            if key in names:
                setattr(cfg, attr, value or None)
                break
        else:
            if value:
                cfg.details.append((label, value))
        i += 1

    for raw in lines[i:]:
        line = raw.strip()
        if not line:
            continue
        bullet = _BULLET_RE.match(line)
        if bullet:
            if cfg.description and cfg.description[-1].kind == "ul":
                cfg.description[-1].items.append(bullet.group(1))
            else:
                cfg.description.append(DescriptionBlock("ul", [bullet.group(1)]))
        else:
            cfg.description.append(DescriptionBlock("p", [line]))
    return cfg
