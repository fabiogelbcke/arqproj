"""Creating a project: its folders in the office's storage, then its rows.

All or nothing (plan A07): folders are created first; if any folder or the
database step fails, the folders made so far are trashed and nothing is saved.
Within the request for the pilot (agreed 15 Oct 2026); a durable background job
can replace this when there is a worker. New folders sit inside the office's
root, already shared with the reader, so they inherit its access.
"""

from __future__ import annotations

import logging
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.projects.enums import RESERVED_SLUGS, ProjectStatus
from backend.projects.models import (
    CLIENT_NAME_MAX,
    Project,
    ProjectSlug,
    ProjectStage,
    ProjectTypeDef,
    StageDef,
)
from backend.tenancy.models import Locale

log = logging.getLogger(__name__)

NAME_MAX = 120
_SLUG = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


def valid_slug(slug: str) -> bool:
    """Lowercase letters, digits and inner hyphens; never one of the app's words."""
    return bool(_SLUG.match(slug)) and slug not in RESERVED_SLUGS


class CreationProblem(Exception):
    def __init__(self, code: str, conflict_name: str | None = None) -> None:
        super().__init__(code)
        self.code = code  # an ErrorCode value
        self.conflict_name = conflict_name


class FolderMaker(Protocol):
    async def create_folder(self, name: str, parent: str | None = None) -> str: ...
    async def trash(self, item_id: str) -> None: ...
    async def rename(self, item_id: str, name: str) -> str:
        """The item's id afterwards (on Drive the same; locally its new path)."""
        ...

    async def name_of(self, item_id: str) -> str: ...

    async def can_open(self, folder_id: str) -> bool:
        """False when the folder is gone (deleted, trashed, out of reach)."""
        ...


class LocalFolders:
    """Local development: ordinary folders under the office's local root."""

    def __init__(self, root: Path) -> None:
        self.root = root

    async def create_folder(self, name: str, parent: str | None = None) -> str:
        base = Path(parent) if parent else Path()
        name = name.replace("/", "-").replace("\\", "-")  # a name, never a path
        candidate, n = base / name, 2
        while (self.root / candidate).exists():  # Drive allows duplicates; disks do not
            candidate, n = base / f"{name} ({n})", n + 1
        (self.root / candidate).mkdir(parents=True)
        return candidate.as_posix()

    async def trash(self, item_id: str) -> None:
        shutil.rmtree(self.root / item_id, ignore_errors=True)

    async def name_of(self, item_id: str) -> str:
        return Path(item_id).name

    async def can_open(self, folder_id: str) -> bool:
        return (self.root / folder_id).is_dir()

    async def rename(self, item_id: str, name: str) -> str:
        current = Path(item_id)
        name = name.replace("/", "-").replace("\\", "-")
        if current.name == name:
            return item_id
        candidate, n = current.with_name(name), 2
        while (self.root / candidate).exists():
            candidate, n = current.with_name(f"{name} ({n})"), n + 1
        (self.root / current).rename(self.root / candidate)
        return candidate.as_posix()


@dataclass(frozen=True)
class NewProject:
    name: str
    client_name: str
    project_type: str
    stages: tuple[str, ...]  # built-in stage keys; listed in their fixed order
    slug: str
    creation_key: str


async def _validate(db: AsyncSession, new: NewProject) -> list[StageDef]:
    """The project's stages, in order, once everything in `new` checks out."""
    if not new.name.strip() or len(new.name.strip()) > NAME_MAX:
        raise CreationProblem("invalid_project_name")
    if not new.client_name.strip() or len(new.client_name.strip()) > CLIENT_NAME_MAX:
        raise CreationProblem("invalid_client_name")
    if await db.get(ProjectTypeDef, new.project_type) is None:
        raise CreationProblem("unknown_project_type")
    chosen = set(new.stages)
    stages = list(
        await db.scalars(
            select(StageDef).where(StageDef.key.in_(chosen)).order_by(StageDef.position)
        )
    )
    if len(chosen) != len(new.stages) or len(stages) != len(chosen):
        raise CreationProblem("unknown_stage")  # unknown or repeated
    if not valid_slug(new.slug):
        raise CreationProblem("invalid_slug")
    taken = await db.scalar(
        select(Project.name)
        .join(ProjectSlug, ProjectSlug.project_id == Project.id)
        .where(ProjectSlug.slug == new.slug)
    )
    if taken is not None:
        raise CreationProblem("slug_taken", conflict_name=taken)
    if (same_name := await project_named(db, new.name)) is not None:
        raise CreationProblem("project_name_taken", conflict_name=same_name)
    return stages


async def project_named(
    db: AsyncSession, name: str, other_than: uuid.UUID | None = None
) -> str | None:
    """The name of another project already called `name`, if any.

    Plan section 10: two projects with one name are ambiguous in the painel and
    in Drive. Case and surrounding spaces don't make a different name.
    """
    query = select(Project.name).where(
        Project.deleted_at.is_(None),
        func.lower(func.btrim(Project.name)) == name.strip().lower(),
    )
    if other_than is not None:
        query = query.where(Project.id != other_than)
    return await db.scalar(query.limit(1))


async def create_project(
    db: AsyncSession, maker: FolderMaker, root: str | None, locale: Locale, new: NewProject
) -> Project:
    """The new draft project (or the one this creation key already made)."""
    existing = await db.scalar(select(Project).where(Project.creation_key == new.creation_key))
    if existing is not None:
        return existing
    stages = list(enumerate(await _validate(db, new), start=1))

    project_folder: str | None = None
    try:
        project_folder = await maker.create_folder(new.name.strip(), root)
        stage_folders = []
        for position, stage in stages:
            title = stage.titles.get(locale.value) or stage.titles["pt-BR"]
            folder = await maker.create_folder(f"{position:02d} - {title}", project_folder)
            stage_folders.append(folder)

        project = Project(
            name=new.name.strip(),
            client_name=new.client_name.strip(),
            project_type=new.project_type,
            status=ProjectStatus.DRAFT,
            current_position=1 if stages else None,
            folder_id=project_folder,
            creation_key=new.creation_key,
        )
        db.add(project)
        await db.flush()
        db.add(ProjectSlug(project_id=project.id, slug=new.slug))
        for (position, stage), folder in zip(stages, stage_folders, strict=True):
            db.add(
                ProjectStage(
                    project_id=project.id,
                    position=position,
                    builtin_key=stage.key,
                    folder_id=folder,
                )
            )
        await db.commit()
        return project
    except BaseException as error:
        await db.rollback()
        if project_folder is not None:
            try:
                await maker.trash(project_folder)  # its stage folders go with it
            except Exception:  # noqa: BLE001 - the original failure is what matters
                log.exception("could not trash new folder %s", project_folder)
        if isinstance(error, IntegrityError):
            if "creation_key" in str(error.orig):  # the same request, sent twice at once
                found = await db.scalar(
                    select(Project).where(Project.creation_key == new.creation_key)
                )
                if found is not None:
                    return found
            if "slug" in str(error.orig):
                raise CreationProblem("slug_taken") from None  # taken in the meantime
        raise
