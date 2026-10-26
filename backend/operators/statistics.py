"""On-demand file counts. No file names or file catalogue leave this module."""

from collections import defaultdict
from datetime import UTC, datetime
from pathlib import PurePosixPath

from pydantic import BaseModel
from sqlalchemy import select

from backend.projects.models import Project, ProjectStage
from backend.storage.base import StorageError, StorageItem, StorageProblem
from backend.web.page_files import _in_project, stage_groups


class FileTypeStats(BaseModel):
    kind: str
    files: int = 0
    known_bytes: int = 0
    unknown_sizes: int = 0


class FileStats(BaseModel):
    loaded_at: datetime
    projects: int
    projects_with_files: int
    files: int
    known_bytes: int
    unknown_sizes: int
    types: list[FileTypeStats]
    account_used: int | None = None
    account_limit: int | None = None


def file_type(item: StorageItem) -> str:
    if item.is_native:
        return "google"
    extension = PurePosixPath(item.name).suffix.lower().lstrip(".")
    if extension in {
        "pdf",
        "dwg",
        "dxf",
        "rvt",
        "rfa",
        "ifc",
        "skp",
        "zip",
        "doc",
        "docx",
        "xls",
        "xlsx",
        "ppt",
        "pptx",
    }:
        return extension
    if item.mime_type.startswith("image/"):
        return "image"
    if item.mime_type.startswith("video/"):
        return "video"
    return "other"


async def load_files(db, storage) -> FileStats:
    projects = list(await db.scalars(select(Project).where(Project.deleted_at.is_(None))))
    stages = (await db.execute(select(ProjectStage.project_id, ProjectStage.folder_id))).all()
    folders = defaultdict(list)
    for project_id, folder in stages:
        if folder:
            folders[project_id].append(folder)
    # Release the database connection before walking storage. ORM objects are
    # loaded above; nothing is written and no file metadata is persisted.
    await db.close()
    types: dict[str, FileTypeStats] = {}
    seen: set[str] = set()
    populated = 0
    for project in projects:
        try:
            inside = await _in_project(storage, project)
        except StorageError as error:
            # A project folder deleted from Drive holds no client-visible files (its
            # page shows them as unavailable); any other failure makes the scan partial.
            if error.problem is not StorageProblem.NOT_FOUND:
                raise
            inside = set()
        has_files = False
        for folder in folders[project.id]:
            if folder not in inside:
                continue
            for _name, _folder, items in await stage_groups(storage, folder):
                has_files |= bool(items)
                for item in items:
                    if item.identity in seen:
                        continue
                    seen.add(item.identity)
                    kind = file_type(item)
                    bucket = types.setdefault(kind, FileTypeStats(kind=kind))
                    bucket.files += 1
                    bucket.known_bytes += item.size or 0
                    bucket.unknown_sizes += int(item.size is None)
        populated += int(has_files)
    return FileStats(
        loaded_at=datetime.now(UTC),
        projects=len(projects),
        projects_with_files=populated,
        files=len(seen),
        known_bytes=sum(t.known_bytes for t in types.values()),
        unknown_sizes=sum(t.unknown_sizes for t in types.values()),
        types=sorted(types.values(), key=lambda t: (-t.files, t.kind)),
    )
