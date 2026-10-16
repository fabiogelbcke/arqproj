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
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.projects.enums import RESERVED_SLUGS, ProjectStatus
from backend.projects.models import (
    CLIENT_NAME_MAX,
    Project,
    ProjectSlug,
    ProjectStage,
    StageDef,
    StageTemplateDef,
    TemplateStage,
)
from backend.tenancy.models import Locale

log = logging.getLogger(__name__)

NAME_MAX = 120
_SLUG = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


class CreationProblem(Exception):
    def __init__(self, code: str, conflict_name: str | None = None) -> None:
        super().__init__(code)
        self.code = code  # an ErrorCode value
        self.conflict_name = conflict_name


class FolderMaker(Protocol):
    async def create_folder(self, name: str, parent: str | None = None) -> str: ...
    async def trash(self, item_id: str) -> None: ...


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


@dataclass(frozen=True)
class NewProject:
    name: str
    client_name: str
    template: str
    slug: str
    creation_key: str


async def _validate(db: AsyncSession, new: NewProject) -> StageTemplateDef:
    if not new.name.strip() or len(new.name.strip()) > NAME_MAX:
        raise CreationProblem("invalid_project_name")
    if not new.client_name.strip() or len(new.client_name.strip()) > CLIENT_NAME_MAX:
        raise CreationProblem("invalid_client_name")
    template = await db.get(StageTemplateDef, new.template)
    if template is None:
        raise CreationProblem("unknown_template")
    if not _SLUG.match(new.slug) or new.slug in RESERVED_SLUGS:
        raise CreationProblem("invalid_slug")
    taken = await db.scalar(
        select(Project.name)
        .join(ProjectSlug, ProjectSlug.project_id == Project.id)
        .where(ProjectSlug.slug == new.slug)
    )
    if taken is not None:
        raise CreationProblem("slug_taken", conflict_name=taken)
    return template


async def create_project(
    db: AsyncSession, maker: FolderMaker, root: str | None, locale: Locale, new: NewProject
) -> Project:
    """The new draft project (or the one this creation key already made)."""
    existing = await db.scalar(select(Project).where(Project.creation_key == new.creation_key))
    if existing is not None:
        return existing
    template = await _validate(db, new)
    stages = (
        await db.execute(
            select(TemplateStage.position, StageDef)
            .join(StageDef, StageDef.key == TemplateStage.stage_key)
            .where(TemplateStage.template_key == template.key)
            .order_by(TemplateStage.position)
        )
    ).all()

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
            project_type=template.default_project_type,
            stage_template=template.key,
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
