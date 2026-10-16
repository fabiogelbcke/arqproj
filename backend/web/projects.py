"""Projects in the painel: the list, and creating one.

    GET  /api/projects    the office's projects, for the list (anyone signed in)
    GET  /api/project-types   the types and stages a new project chooses from
    POST /api/projects    create a draft project with its folders (anyone signed in)

Built-in texts (project types, stage titles) come in the office's
language; what the office typed comes as typed.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.projects.creation import (
    CreationProblem,
    FolderMaker,
    LocalFolders,
    NewProject,
    create_project,
)
from backend.projects.enums import AccessMode, ProjectStatus
from backend.projects.models import (
    Meeting,
    Project,
    ProjectSlug,
    ProjectStage,
    ProjectTypeDef,
    ProjectTypeStage,
    StageDef,
)
from backend.storage.google_connect import ConnectError
from backend.storage.models import ReaderStatus, StorageConnection, StorageKind
from backend.tenancy.models import Locale
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web.auth import CurrentStaff, current_staff, require_csrf
from backend.web.drive import writer_for
from backend.web.errors import ApiError, ErrorCode, documented

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def _text(texts: dict[str, str], locale: Locale) -> str:
    return texts.get(locale.value) or texts[Locale.PT_BR.value]


class NextMeeting(BaseModel):
    title: str
    starts_at: datetime


class ProjectSummary(BaseModel):
    id: uuid.UUID
    name: str
    client_name: str
    slug: str
    status: ProjectStatus
    project_type: str
    project_type_label: str
    stage_count: int
    current_position: int | None
    current_stage_title: str | None
    next_meeting: NextMeeting | None
    created_at: datetime
    # The last change a client can see (A28); None until there is one.
    last_activity_at: datetime | None
    # Sent back with a change, so a change made meanwhile by someone else is caught.
    row_version: int
    # Changes when the cover does, so browsers fetch the new one; None: placeholder.
    cover_url: str | None
    access_mode: AccessMode


class StageOption(BaseModel):
    key: str
    title: str


class ProjectTypeOption(BaseModel):
    key: str
    label: str
    # Its usual stages, ticked when it is chosen.
    stages: list[str]


class CreationOptions(BaseModel):
    types: list[ProjectTypeOption]
    # Every built-in stage, in the order a project lists them.
    stages: list[StageOption]


class ProjectIn(BaseModel):
    name: str = Field(max_length=500)
    client_name: str = Field(max_length=500)
    project_type: str = Field(max_length=100)
    stages: list[str] = Field(max_length=50)
    slug: str = Field(max_length=200)
    # Made by the screen once per dialog: a retried or double-sent request
    # returns the project already created.
    creation_key: str = Field(min_length=16, max_length=100)


async def summaries(
    db: AsyncSession, locale: Locale, only: uuid.UUID | None = None
) -> list[ProjectSummary]:
    query = (
        select(Project, ProjectSlug.slug, ProjectTypeDef.labels)
        .join(ProjectSlug, (ProjectSlug.project_id == Project.id) & ProjectSlug.is_current)
        .join(ProjectTypeDef, ProjectTypeDef.key == Project.project_type)
        .where(Project.deleted_at.is_(None))
    )
    # The list leaves archived projects out; one asked for by id is returned as is.
    if only is not None:
        query = query.where(Project.id == only)
    else:
        query = query.where(Project.status != ProjectStatus.ARCHIVED)
    rows = (await db.execute(query)).all()
    ids = [project.id for project, _, _ in rows]
    if not ids:
        return []

    counts = dict(
        (
            await db.execute(
                select(ProjectStage.project_id, func.count())
                .where(ProjectStage.project_id.in_(ids))
                .group_by(ProjectStage.project_id)
            )
        ).all()
    )
    current = {
        stage.project_id: stage.title or (_text(titles, locale) if titles else None)
        for stage, titles in (
            await db.execute(
                select(ProjectStage, StageDef.titles)
                .outerjoin(StageDef, StageDef.key == ProjectStage.builtin_key)
                .join(
                    Project,
                    (Project.id == ProjectStage.project_id)
                    & (Project.current_position == ProjectStage.position),
                )
                .where(ProjectStage.project_id.in_(ids))
            )
        ).all()
    }
    meetings = {
        meeting.project_id: NextMeeting(title=meeting.title, starts_at=meeting.starts_at)
        for meeting in await db.scalars(
            select(Meeting)
            .where(Meeting.project_id.in_(ids), Meeting.starts_at > datetime.now(UTC))
            .order_by(Meeting.project_id, Meeting.starts_at)
            .ext(distinct_on(Meeting.project_id))
        )
    }
    return [
        ProjectSummary(
            id=project.id,
            name=project.name,
            client_name=project.client_name,
            slug=slug,
            status=project.status,
            project_type=project.project_type,
            project_type_label=_text(labels, locale),
            stage_count=counts.get(project.id, 0),
            current_position=project.current_position,
            current_stage_title=current.get(project.id),
            next_meeting=meetings.get(project.id),
            created_at=project.created_at,
            last_activity_at=project.last_activity_at,
            row_version=project.row_version,
            cover_url=cover_url(project),
            access_mode=project.access_mode,
        )
        for project, slug, labels in rows
    ]


def cover_url(project: Project) -> str | None:
    if project.cover_file_id is None:
        return None
    # Microseconds: two changes within a second still get different addresses.
    return f"/api/projects/{project.id}/cover?v={project.updated_at.timestamp():.6f}"


@router.get("/projects", responses=documented(401))
async def projects(
    _staff: CurrentStaff = Depends(current_staff),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> list[ProjectSummary]:
    return await summaries(db, tenant.locale)


@router.get("/project-types", responses=documented(401))
async def project_types(
    _staff: CurrentStaff = Depends(current_staff),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> CreationOptions:
    stages = list(await db.scalars(select(StageDef).order_by(StageDef.position)))
    usual: dict[str, set[str]] = {}
    for kind, stage in await db.execute(
        select(ProjectTypeStage.project_type, ProjectTypeStage.stage_key)
    ):
        usual.setdefault(kind, set()).add(stage)
    return CreationOptions(
        types=[
            ProjectTypeOption(
                key=kind.key,
                label=_text(kind.labels, tenant.locale),
                stages=[stage.key for stage in stages if stage.key in usual.get(kind.key, set())],
            )
            for kind in await db.scalars(select(ProjectTypeDef).order_by(ProjectTypeDef.position))
        ],
        stages=[
            StageOption(key=stage.key, title=_text(stage.titles, tenant.locale)) for stage in stages
        ],
    )


async def _folders(request: Request, db: AsyncSession) -> tuple[FolderMaker, str | None]:
    """Where the new folders go: the office's Drive folder, or locally its folder."""
    connection = await db.scalar(select(StorageConnection))
    if connection is not None and connection.kind is StorageKind.FOLDER:
        if request.app.state.settings.deployed:
            raise ApiError(409, ErrorCode.DRIVE_NOT_CONNECTED)
        root = Path(request.app.state.settings.local_storage_root) / connection.root_id
        return LocalFolders(root), None
    if connection is not None and connection.reader_status is not ReaderStatus.OK:
        # Created through the office's grant but shown through the reader: if the
        # reader cannot read the folder, the project's files would never show.
        raise ApiError(409, ErrorCode.DRIVE_UNREADABLE)
    connection, writer = await writer_for(request, db)
    return writer, connection.root_id


@router.post("/projects", status_code=201, responses=documented(401, 409, 422, 503))
async def new_project(
    request: Request,
    body: ProjectIn,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> ProjectSummary:
    maker, root = await _folders(request, db)
    new = NewProject(
        name=body.name,
        client_name=body.client_name,
        project_type=body.project_type,
        stages=tuple(body.stages),
        slug=body.slug.strip().lower(),
        creation_key=body.creation_key,
    )
    try:
        project = await create_project(db, maker, root, tenant.locale, new)
    except CreationProblem as problem:
        taken = problem.code in (ErrorCode.SLUG_TAKEN, ErrorCode.PROJECT_NAME_TAKEN)
        status = 409 if taken else 422
        raise ApiError(status, ErrorCode(problem.code), problem.conflict_name) from None
    except ConnectError as error:
        log.error("creating project folders failed for %s: %s", tenant.slug, error.detail)
        raise ApiError(503, ErrorCode.DRIVE_CONNECT_FAILED) from None
    log.info("project %s created in %s", project.id, tenant.slug)
    return (await summaries(db, tenant.locale, only=project.id))[0]
