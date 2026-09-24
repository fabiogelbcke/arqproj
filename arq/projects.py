"""Turn the Drive folder tree into projects and stages.

    <root>/
      <Project folder>/          one per project
        _project                 config doc (see config.py)
        01 - Briefing/           stage folders, ordered by numeric prefix
          file.pdf
          Renders/               subfolders inside a stage become file groups
        _internal/               anything starting with "_" or "." is hidden
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime

from .cache import TTLCache
from .config import ProjectConfig, parse_config, slugify
from .drive import Drive, DriveFile

log = logging.getLogger(__name__)

_CONFIG_NAME_RE = re.compile(r"^_project(\.(txt|md))?$", re.IGNORECASE)
_STAGE_RE = re.compile(r"^\s*(\d{1,3})\s*[-–—._):]*\s*(.*)$")
_ALL_DONE = {"done", "complete", "completed", "finished", "concluido", "concluído", "finalizado", "entregue"}
MAX_SUBFOLDER_DEPTH = 3

_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="drive")


def is_hidden(name: str) -> bool:
    return name.startswith(("_", "."))


@dataclass
class ProjectSummary:
    id: str
    folder_name: str
    slug: str
    title: str
    config: ProjectConfig
    children: list[DriveFile]


@dataclass
class FileGroup:
    path: list[str]  # subfolder names below the stage folder; [] = stage root
    files: list[DriveFile]


@dataclass
class Stage:
    folder_id: str
    number: int | None
    label: str
    groups: list[FileGroup]
    status: str | None = None  # "done" | "current" | "upcoming" | None

    @property
    def anchor(self) -> str:
        return f"stage-{self.number:02d}" if self.number is not None else f"stage-{slugify(self.label)}"

    @property
    def files(self) -> list[DriveFile]:
        return [f for g in self.groups for f in g.files]

    @property
    def last_modified(self) -> datetime | None:
        return max((f.modified for f in self.files if f.modified), default=None)


@dataclass
class Project:
    summary: ProjectSummary
    stages: list[Stage]
    files: dict[str, DriveFile] = field(default_factory=dict)

    @property
    def title(self) -> str:
        return self.summary.title

    @property
    def config(self) -> ProjectConfig:
        return self.summary.config

    @property
    def last_modified(self) -> datetime | None:
        return max((s.last_modified for s in self.stages if s.last_modified), default=None)


def parse_stage_name(name: str) -> tuple[int | None, str]:
    m = _STAGE_RE.match(name)
    if not m:
        return None, name.strip()
    return int(m.group(1)), (m.group(2).strip() or name.strip())


def assign_statuses(stages: list[Stage], current: str | None) -> None:
    if not current:
        return
    wanted = current.strip().lower()
    if wanted in _ALL_DONE:
        for s in stages:
            s.status = "done"
        return
    idx = None
    for i, s in enumerate(stages):
        if wanted.isdigit() and s.number == int(wanted):
            idx = i
            break
        if wanted in (s.label.lower(), slugify(s.label)) or slugify(wanted) == slugify(s.label):
            idx = i
            break
    if idx is None:
        log.warning("current stage %r matches no stage folder", current)
        return
    for i, s in enumerate(stages):
        s.status = "done" if i < idx else "current" if i == idx else "upcoming"


class ProjectStore:
    def __init__(self, drive: Drive, root_folder_id: str, ttl_seconds: float = 60, cache: TTLCache | None = None):
        if not root_folder_id:
            raise RuntimeError("DRIVE_ROOT_FOLDER_ID is not set")
        self.drive = drive
        self.root_id = root_folder_id
        self.ttl = ttl_seconds
        self.cache = cache or TTLCache()

    # -- Drive access (cached) --------------------------------------------

    def _children(self, folder_id: str) -> list[DriveFile]:
        return self.cache.get_or_set(("ls", folder_id), self.ttl, lambda: self.drive.list_children(folder_id))

    def _text(self, f: DriveFile) -> str:
        # Keyed on modifiedTime, so edits show up as soon as the listing refreshes.
        key = ("txt", f.id, f.modified.isoformat() if f.modified else None)
        return self.cache.get_or_set(key, self.ttl * 30, lambda: self.drive.read_text(f))

    # -- Projects -----------------------------------------------------------

    def _summarize(self, folder: DriveFile) -> ProjectSummary:
        children = self._children(folder.id)
        cfg_file = next((f for f in children if not f.is_folder and _CONFIG_NAME_RE.match(f.name)), None)
        config = parse_config(self._text(cfg_file)) if cfg_file else ProjectConfig()
        return ProjectSummary(
            id=folder.id,
            folder_name=folder.name,
            slug=slugify(config.slug or folder.name) or folder.id,
            title=config.title or folder.name,
            config=config,
            children=children,
        )

    def index(self) -> dict[str, ProjectSummary]:
        def build() -> dict[str, ProjectSummary]:
            folders = [f for f in self._children(self.root_id) if f.is_folder and not is_hidden(f.name)]
            by_slug: dict[str, ProjectSummary] = {}
            for summary in _pool.map(self._summarize, folders):
                if summary.slug in by_slug:
                    log.warning("duplicate slug %r (%s); keeping %s", summary.slug, summary.folder_name,
                                by_slug[summary.slug].folder_name)
                    continue
                by_slug[summary.slug] = summary
            return by_slug

        return self.cache.get_or_set(("index",), self.ttl, build)

    def find(self, key: str) -> ProjectSummary | None:
        index = self.index()
        return index.get(key) or next((p for p in index.values() if p.id == key), None)

    def _collect(self, folder_id: str, path: list[str], depth: int) -> list[FileGroup]:
        children = self._children(folder_id)
        files = [f for f in children if not f.is_folder and not is_hidden(f.name)]
        groups = [FileGroup(path, files)] if files or not path else []
        if depth < MAX_SUBFOLDER_DEPTH:
            for sub in (f for f in children if f.is_folder and not is_hidden(f.name)):
                groups.extend(self._collect(sub.id, path + [sub.name], depth + 1))
        return groups

    def _load_stage(self, folder: DriveFile) -> Stage:
        number, label = parse_stage_name(folder.name)
        return Stage(folder_id=folder.id, number=number, label=label, groups=self._collect(folder.id, [], 0))

    def load(self, key: str) -> Project | None:
        summary = self.find(key)
        if summary is None:
            return None
        stage_folders = [f for f in summary.children if f.is_folder and not is_hidden(f.name)]
        stages = list(_pool.map(self._load_stage, stage_folders))
        stages.sort(key=lambda s: (s.number is None, s.number or 0, s.label.lower()))
        assign_statuses(stages, summary.config.current_stage)
        files = {f.id: f for s in stages for f in s.files}
        return Project(summary=summary, stages=stages, files=files)
