"""Turn the Drive folder tree into projects and stages.

    <root>/
      _site/logo.png             optional firm logo (shown in the header)
      <Project folder>/          one per project
        _project                 config doc (see config.py)
        01 - Briefing/           stage folders, ordered by numeric prefix
          _stage                 optional stage notes (same format as _project)
          Plans rev A.pdf        versions: same name + version token are grouped
          Plans rev B.pdf
          Model.skp
          Model.jpg              same-name image = preview for Model.skp
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
from .drive import Drive, DriveError, DriveFile

log = logging.getLogger(__name__)

_CONFIG_NAME_RE = re.compile(r"^_project(\.(txt|md))?$", re.IGNORECASE)
_STAGE_NOTES_RE = re.compile(r"^_(stage|etapa)(\.(txt|md))?$", re.IGNORECASE)
_LOGO_RE = re.compile(r"^logo\.(png|jpe?g|webp|svg)$", re.IGNORECASE)
_LOGO_DARK_RE = re.compile(r"^logo[-_]dark\.(png|jpe?g|webp|svg)$", re.IGNORECASE)
_STAGE_RE = re.compile(r"^\s*(\d{1,3})\s*[-–—._):]*\s*(.*)$")
# "Plans rev B", "Plans - rev.3", "Plans_v02", "Plans R03", "Plans (rev A)", "Planta revisão 2"
_VERSION_RE = re.compile(
    r"^(?P<base>.*?)[\s_\-–—.(\[]+"
    r"(?P<token>(?:rev(?:is[aã]o|ision)?\.?\s*[-_]?\s*(?:\d{1,3}|[A-Za-z])|(?:r|v|ver)\.?\s*[-_]?\s*\d{1,3}))"
    r"[)\]]?\s*$",
    re.IGNORECASE,
)
_PREVIEW_EXTS = {"jpg", "jpeg", "png", "webp"}
_ALL_DONE = {"done", "complete", "completed", "finished", "concluido", "concluído", "finalizado", "entregue"}
MAX_SUBFOLDER_DEPTH = 3

_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="drive")
_project_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="project")  # dashboard fan-out


def describe_error(exc: Exception) -> tuple[str, dict]:
    """Turn a Drive/network failure into an i18n key the dashboard can show."""
    if isinstance(exc, DriveError) and exc.status == 404:
        return "err.not_found", {}
    if isinstance(exc, DriveError) and exc.status in (401, 403):
        return "err.forbidden", {}
    return "err.other", {"detail": str(exc)[:200]}


def is_hidden(name: str) -> bool:
    return name.startswith(("_", "."))


def split_name(name: str) -> tuple[str, str]:
    """('Plans rev B', 'pdf') for 'Plans rev B.pdf'."""
    if "." in name:
        stem, ext = name.rsplit(".", 1)
        if 1 <= len(ext) <= 5 and ext.isalnum():
            return stem, ext.lower()
    return name, ""


def parse_version(stem: str) -> tuple[str, str | None, tuple]:
    """Returns (grouping key, version label, sort key)."""
    m = _VERSION_RE.match(stem)
    if not m or not m.group("base").strip():
        return _norm(stem), None, (0, 0)
    token = m.group("token")
    tail = re.search(r"(\d{1,3}|[A-Za-z])$", token).group(1)
    order = int(tail) if tail.isdigit() else ord(tail.upper()) - ord("A") + 1
    return _norm(m.group("base")), token.strip(), (1, order)


def _norm(text: str) -> str:
    return re.sub(r"[\s_\-–—.]+", " ", text).strip().lower()


@dataclass
class ProjectSummary:
    id: str
    folder_name: str
    slug: str
    title: str
    config: ProjectConfig
    children: list[DriveFile]
    has_config: bool = False
    explicit_slug: bool = False
    issues: list[tuple[str, dict]] = field(default_factory=list)  # (i18n key, params)
    error: str | None = None          # folder couldn't be read at all
    duplicate_of: str | None = None   # folder name of the project that owns our slug
    invalid_slug: str | None = None   # the invalid `Slug:` value, when there is one
    same_name: int = 1                # how many project folders share this folder's name
    wanted_slug: str | None = None    # the slug we asked for, when it was taken

    @property
    def hidden(self) -> bool:
        """Not reachable through its intended link (clients can't find it)."""
        return bool(self.error or self.duplicate_of or self.invalid_slug)

    @property
    def public(self) -> bool:
        """Reachable from a client link (by slug, or by folder ID for duplicates)."""
        return self.error is None


@dataclass
class FileEntry:
    """One card: the latest version of a file, its older versions, and an optional preview image."""

    file: DriveFile
    version: str | None = None
    older: list[tuple[DriveFile, str | None]] = field(default_factory=list)
    preview: DriveFile | None = None

    @property
    def thumb(self) -> DriveFile | None:
        if self.preview is not None:
            return self.preview
        return self.file if self.file.thumbnail_link else None

    @property
    def all_files(self) -> list[DriveFile]:
        return [self.file, *(f for f, _ in self.older), *([self.preview] if self.preview else [])]


@dataclass
class FileGroup:
    path: list[str]  # subfolder names below the stage folder; [] = stage root
    entries: list[FileEntry]


@dataclass
class Stage:
    folder_id: str
    number: int | None
    label: str
    groups: list[FileGroup]
    notes: ProjectConfig | None = None
    status: str | None = None  # "done" | "current" | "upcoming" | None
    error: str | None = None   # i18n key when the folder couldn't be read
    error_params: dict = field(default_factory=dict)
    anchor_override: str | None = None

    @property
    def explanation(self):
        from . import i18n
        from .stages import stage_explanation
        return stage_explanation(self.number, self.label, i18n.lang())

    @property
    def anchor(self) -> str:
        if self.anchor_override:
            return self.anchor_override
        return f"stage-{self.number:02d}" if self.number is not None else f"stage-{slugify(self.label)}"

    @property
    def entries(self) -> list[FileEntry]:
        return [e for g in self.groups for e in g.entries]

    @property
    def all_files(self) -> list[DriveFile]:
        return [f for e in self.entries for f in e.all_files]

    @property
    def last_modified(self) -> datetime | None:
        return max((e.file.modified for e in self.entries if e.file.modified), default=None)


@dataclass
class Project:
    summary: ProjectSummary
    stages: list[Stage]
    files: dict[str, DriveFile] = field(default_factory=dict)
    warnings: list[tuple[str, dict]] = field(default_factory=list)  # (i18n key, params)

    @property
    def title(self) -> str:
        return self.summary.title

    @property
    def slug(self) -> str:
        return self.summary.slug

    @property
    def config(self) -> ProjectConfig:
        return self.summary.config

    @property
    def last_modified(self) -> datetime | None:
        return max((s.last_modified for s in self.stages if s.last_modified), default=None)

    @property
    def current_stage(self) -> Stage | None:
        return next((s for s in self.stages if s.status == "current"), None)

    @property
    def entry_count(self) -> int:
        return sum(len(s.entries) for s in self.stages)


def parse_stage_name(name: str) -> tuple[int | None, str]:
    m = _STAGE_RE.match(name)
    if not m:
        return None, name.strip()
    return int(m.group(1)), (m.group(2).strip() or name.strip())


def assign_statuses(stages: list[Stage], current: str | None) -> str:
    """Set stage statuses. Returns "ok", "unmatched" (`current` names no stage) or
    "ambiguous" (`current` names more than one stage; we don't guess which).

    Without a usable `current`, it's inferred: the last stage with files is in
    progress, earlier ones are completed, later ones upcoming.
    """
    result = "ok"
    idx = None
    if current:
        wanted = current.strip().lower()
        if wanted in _ALL_DONE:
            for s in stages:
                s.status = "done"
            return "ok"
        hits = [i for i, s in enumerate(stages)
                if (wanted.isdigit() and s.number == int(wanted)) or slugify(wanted) == slugify(s.label)]
        if len(hits) == 1:
            idx = hits[0]
        elif hits:
            result = "ambiguous"
            log.warning("current stage %r matches %d stage folders", current, len(hits))
        else:
            result = "unmatched"
            log.warning("current stage %r matches no stage folder", current)
    if idx is None:
        with_files = [i for i, s in enumerate(stages) if s.entries]
        if not with_files:
            return result
        idx = with_files[-1]
    for i, s in enumerate(stages):
        s.status = "done" if i < idx else "current" if i == idx else "upcoming"
    return result


def build_entries(files: list[DriveFile]) -> list[FileEntry]:
    """Pair previews with their files, then group versions of the same file."""
    images = {}
    for f in files:
        stem, ext = split_name(f.name)
        if ext in _PREVIEW_EXTS:
            images.setdefault(stem.lower(), f)

    previews: dict[str, DriveFile] = {}
    used: set[str] = set()
    for f in files:
        stem, ext = split_name(f.name)
        if ext in _PREVIEW_EXTS:
            continue
        img = images.get(stem.lower())
        if img is not None:
            previews[f.id] = img
            used.add(img.id)

    groups: dict[tuple[str, str], list[tuple[tuple, DriveFile, str | None]]] = {}
    order: list[tuple[str, str]] = []
    for f in files:
        if f.id in used:
            continue
        stem, ext = split_name(f.name)
        key, label, sort_key = parse_version(stem)
        gkey = (key, ext)
        if gkey not in groups:
            groups[gkey] = []
            order.append(gkey)
        groups[gkey].append((sort_key, f, label))

    entries = []
    for gkey in order:
        versions = sorted(
            groups[gkey],
            key=lambda v: (v[0], v[1].modified.timestamp() if v[1].modified else 0),
            reverse=True,
        )
        (_, latest, label), rest = versions[0], versions[1:]
        preview = previews.get(latest.id) or next((previews[f.id] for _, f, _ in rest if f.id in previews), None)
        entries.append(FileEntry(file=latest, version=label if rest else None,
                                 older=[(f, lbl) for _, f, lbl in rest], preview=preview))
    entries.sort(key=lambda e: e.file.name.lower())
    return entries


class ProjectStore:
    def __init__(self, drive: Drive, root_folder_id: str, ttl_seconds: float = 60, cache: TTLCache | None = None):
        root_folder_id = (root_folder_id or "").strip()
        # Accept a pasted folder URL: https://drive.google.com/drive/folders/<id>?usp=...
        m = re.search(r"/folders/([A-Za-z0-9_-]+)", root_folder_id)
        if m:
            root_folder_id = m.group(1)
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,}", root_folder_id):
            raise RuntimeError(
                f"DRIVE_ROOT_FOLDER_ID={root_folder_id!r} doesn't look like a Drive folder ID. "
                "Use the ID from the folder's URL (drive.google.com/drive/folders/<ID>), not its name."
            )
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

    def refresh(self) -> None:
        self.cache.clear()

    # -- Site assets --------------------------------------------------------

    def logo(self, dark: bool = False) -> DriveFile | None:
        """`_site/logo.(png|jpg|webp|svg)` in the root folder, if present.
        `_site/logo-dark.*` is an optional variant for dark mode."""
        pattern = _LOGO_DARK_RE if dark else _LOGO_RE
        try:
            site = next((f for f in self._children(self.root_id) if f.is_folder and f.name.lower() == "_site"), None)
            if site is None:
                return None
            return next((f for f in self._children(site.id) if not f.is_folder and pattern.match(f.name)), None)
        except Exception:  # a missing logo must never break a page
            log.exception("could not look up logo")
            return None

    # -- Projects -----------------------------------------------------------

    def _summarize(self, folder: DriveFile) -> ProjectSummary:
        """Never raises: a folder that can't be read becomes a summary with `error`."""
        try:
            children = self._children(folder.id)
        except Exception as exc:  # e.g. a shortcut to a folder the site can't see
            log.warning("cannot read project folder %r: %s", folder.name, exc)
            key, params = describe_error(exc)
            return ProjectSummary(id=folder.id, folder_name=folder.name, slug=folder.id, title=folder.name,
                                  config=ProjectConfig(), children=[], error=key,
                                  issues=[("warn.folder_unreadable", {"reason": key, **params})])

        issues: list[tuple[str, dict]] = []
        cfg_files = [f for f in children if not f.is_folder and _CONFIG_NAME_RE.match(f.name)]
        cfg_file = None
        if cfg_files:
            # Prefer a Google Doc, then the most recently edited file.
            cfg_files.sort(key=lambda f: (f.mime_type != "application/vnd.google-apps.document",
                                          -(f.modified.timestamp() if f.modified else 0)))
            cfg_file = cfg_files[0]
            if len(cfg_files) > 1:
                issues.append(("warn.multiple_configs", {"n": len(cfg_files), "used": _display_name(cfg_file)}))
        config = ProjectConfig()
        if cfg_file is not None:
            try:
                config = parse_config(self._text(cfg_file))
            except Exception as exc:
                key, params = describe_error(exc)
                issues.append(("warn.config_unreadable", {"name": _display_name(cfg_file), "reason": key, **params}))
            for key, params in config.issues:
                issues.append((key, {"name": _display_name(cfg_file), **params}))

        if config.slug and not config.slug_invalid:
            slug, explicit = config.slug, True
        elif config.slug_invalid:
            slug, explicit = folder.id, False  # unpublished until fixed; folder-ID link only
        else:
            slug, explicit = slugify(folder.name) or folder.id, False
        return ProjectSummary(
            id=folder.id,
            folder_name=folder.name,
            slug=slug,
            title=config.title or folder.name,
            config=config,
            children=children,
            has_config=cfg_file is not None,
            explicit_slug=explicit,
            invalid_slug=config.slug if config.slug_invalid else None,
            issues=issues,
        )

    def _build_index(self) -> tuple[dict[str, ProjectSummary], list[ProjectSummary]]:
        """Returns (public projects by slug, every project folder including broken ones).

        When two folders ask for the same slug, the first (alphabetically) keeps it
        and the other is still listed, reachable only by its folder ID, and flagged.
        """
        folders = [f for f in self._children(self.root_id) if f.is_folder and not is_hidden(f.name)]
        summaries = list(_pool.map(self._summarize, folders))
        name_counts: dict[str, int] = {}
        for summary in summaries:
            key = summary.folder_name.strip().casefold()
            name_counts[key] = name_counts.get(key, 0) + 1
        by_slug: dict[str, ProjectSummary] = {}
        for summary in summaries:
            summary.same_name = name_counts[summary.folder_name.strip().casefold()]
            if summary.error or summary.invalid_slug:
                continue
            owner = by_slug.get(summary.slug)
            if owner is not None:
                log.warning("duplicate slug %r: %r loses to %r", summary.slug, summary.folder_name, owner.folder_name)
                summary.duplicate_of = owner.folder_name
                summary.wanted_slug = summary.slug
                summary.slug = summary.id
                continue
            by_slug[summary.slug] = summary
        return by_slug, summaries

    def _index_full(self):
        return self.cache.get_or_set(("index",), self.ttl, self._build_index)

    def index(self) -> dict[str, ProjectSummary]:
        return self._index_full()[0]

    def all_summaries(self) -> list[ProjectSummary]:
        return self._index_full()[1]

    def find(self, key: str) -> ProjectSummary | None:
        index = self.index()
        if key in index:
            return index[key]
        return next((p for p in self.all_summaries() if p.id == key and p.public), None)

    def _collect(self, folder_id: str, path: list[str], depth: int) -> list[FileGroup]:
        children = self._children(folder_id)
        files = [f for f in children if not f.is_folder and not is_hidden(f.name)]
        groups = [FileGroup(path, build_entries(files))] if files or not path else []
        if depth < MAX_SUBFOLDER_DEPTH:
            for sub in (f for f in children if f.is_folder and not is_hidden(f.name)):
                groups.extend(self._collect(sub.id, path + [sub.name], depth + 1))
        return groups

    def _load_stage(self, folder: DriveFile) -> Stage:
        number, label = parse_stage_name(folder.name)
        try:
            children = self._children(folder.id)
            notes_file = next((f for f in children if not f.is_folder and _STAGE_NOTES_RE.match(f.name)), None)
            notes = parse_config(self._text(notes_file)) if notes_file else None
            groups = self._collect(folder.id, [], 0)
        except Exception as exc:
            log.warning("cannot read stage folder %r: %s", folder.name, exc)
            key, params = describe_error(exc)
            stage = Stage(folder_id=folder.id, number=number, label=label, groups=[])
            stage.error = key
            stage.error_params = params
            return stage
        return Stage(folder_id=folder.id, number=number, label=label, groups=groups, notes=notes)

    def load(self, key: str) -> Project | None:
        summary = self.find(key)
        return self._load_summary(summary) if summary else None

    def _load_summary(self, summary: ProjectSummary) -> Project:
        if summary.error:
            return Project(summary=summary, stages=[], warnings=list(summary.issues))

        stage_folders = [f for f in summary.children if f.is_folder and not is_hidden(f.name)]
        stages = list(_pool.map(self._load_stage, stage_folders))
        stages.sort(key=lambda s: (s.number is None, s.number or 0, s.label.lower()))
        matched = assign_statuses(stages, summary.config.current_stage)
        files = {f.id: f for s in stages for f in s.all_files}

        # Two stages with the same number (or the same unnumbered name): flag them,
        # and keep page anchors unique so both stay clickable.
        clashes: dict[object, list[Stage]] = {}
        for st in stages:
            clashes.setdefault(st.number if st.number is not None else st.label.casefold(), []).append(st)
        used: set[str] = set()
        for st in stages:
            anchor, n = st.anchor, 2
            while anchor in used:
                anchor, n = f"{st.anchor}-{n}", n + 1
            used.add(anchor)
            st.anchor_override = anchor if anchor != st.anchor else None

        warnings: list[tuple[str, dict]] = []
        if summary.duplicate_of:
            warnings.append(("warn.slug_taken", {"slug": summary.wanted_slug, "other": summary.duplicate_of}))
        for other in self.all_summaries():
            if other.duplicate_of and other.duplicate_of == summary.folder_name and not summary.duplicate_of:
                warnings.append(("warn.duplicate_slug", {"slug": summary.slug, "other": other.folder_name}))
        if summary.same_name > 1:
            warnings.append(("warn.duplicate_folder_name", {"name": summary.folder_name.strip(), "n": summary.same_name}))
        for key, group in clashes.items():
            if len(group) > 1 and isinstance(key, int):
                warnings.append(("warn.duplicate_stage", {"stage": f"{key:02d}",
                                                          "names": ", ".join(f"“{g.label}”" for g in group)}))
            elif len(group) > 1:
                warnings.append(("warn.duplicate_stage_name", {"name": group[0].label, "n": len(group)}))
        if not summary.has_config:
            warnings.append(("warn.no_config", {}))
        warnings.extend(summary.issues)
        if not summary.explicit_slug and not summary.duplicate_of and not summary.invalid_slug:
            warnings.append(("warn.guessable_link", {}))
        if matched == "unmatched":
            warnings.append(("warn.stage_unmatched", {"value": summary.config.current_stage}))
        elif matched == "ambiguous":
            warnings.append(("warn.stage_ambiguous", {"value": summary.config.current_stage}))
        for stage in stages:
            if stage.error:
                warnings.append(("warn.stage_unreadable", {"stage": stage.label, "reason": stage.error,
                                                           **stage.error_params}))
        if not stages:
            warnings.append(("warn.no_stages", {}))
        loose = [f for f in summary.children if not f.is_folder and not is_hidden(f.name)]
        if loose:
            warnings.append(("warn.root_files", {"n": len(loose)}))
        return Project(summary=summary, stages=stages, files=files, warnings=warnings)

    def load_all(self) -> list[Project]:
        """Every project folder, including broken or shadowed ones (for the dashboard)."""
        summaries = sorted(self.all_summaries(), key=lambda s: s.folder_name.lower())
        return list(_project_pool.map(self._load_summary, summaries))


def _display_name(f: DriveFile) -> str:
    return f.name
