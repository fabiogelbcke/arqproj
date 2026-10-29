"""Editing a project's stages and progress from its page (edit mode, part 2).

    POST   /api/projects/{id}/stages                  add a stage (built-in or the office's own)
    PATCH  /api/projects/{id}/stages/{n}              rename it
    POST   /api/projects/{id}/stages/{n}/move         one place up or down
    PUT    /api/projects/{id}/stages/order            every stage in a new order at once
    DELETE /api/projects/{id}/stages/{n}?row_version= remove it (its folder stays)
    PUT    /api/projects/{id}/stages/{n}/completion   mark it as completed, or reopen it
    PUT    /api/projects/{id}/completion              complete the project, once every stage is
    POST   /api/projects/{id}/progress                the previous release's (A30), for one release

Stage folders follow the stages in the office's Drive (Fabio, 16 Oct 2026):
renaming or reordering renames the "NN - title" folders, adding creates one, and
removing a stage keeps its folder and files. Drive goes first; if it fails, the
names already changed are put back and nothing is saved (`drive_connect_failed`).
Every change carries the page's `row_version` (plan section 7). Completing or
reopening a stage moves "Atualizado"; stage edits don't (the A28 interim rule).
Stages complete on their own, in any order (0032, for review). Staff complete the
project themselves once every stage is (asked when the last one is completed:
Fabio, 23 Oct 2026); reopening or adding a stage makes a completed project
active again.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics import capture
from backend.db.engine import get_tenant_session
from backend.notifications.events import record
from backend.notifications.models import EventKind
from backend.projects.enums import ProjectStatus
from backend.projects.models import (
    STAGE_TITLE_MAX,
    Project,
    ProjectStage,
    ProjectTypeStage,
    StageDef,
)
from backend.storage.google_connect import ConnectError
from backend.tenancy.models import Locale
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web.auth import CurrentStaff, require_csrf
from backend.web.errors import ApiError, ErrorCode, documented
from backend.web.page_edit import _change
from backend.web.projects import _folders

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def _text(texts: dict[str, str], locale: Locale) -> str:
    return texts.get(locale.value) or texts[Locale.PT_BR.value]


async def _stages(db: AsyncSession, project_id: uuid.UUID) -> list[ProjectStage]:
    return list(
        await db.scalars(
            select(ProjectStage)
            .where(ProjectStage.project_id == project_id)
            .order_by(ProjectStage.position)
        )
    )


async def _title(db: AsyncSession, stage: ProjectStage, locale: Locale) -> str:
    if stage.builtin_key is None:
        return stage.title or ""
    titles = await db.scalar(select(StageDef.titles).where(StageDef.key == stage.builtin_key))
    return _text(titles, locale)


def _folder_name(position: int, title: str) -> str:
    return f"{position:02d} - {title}"


class Renames:
    """Drive first, undone if anything after it fails."""

    def __init__(self, maker) -> None:
        self.maker = maker
        self.done: list[tuple[str, str]] = []  # (new id, old name)

    async def rename(self, stage: ProjectStage, old: str, new: str) -> None:
        """`old` is the conventional name; the folder's real one (staff may have
        named it themselves) is what an undo puts back."""
        if self.maker is None or stage.folder_id is None:
            return
        if not await self.maker.can_open(stage.folder_id):
            return  # deleted in Drive by hand: nothing to keep in step
        actual = await self.maker.name_of(stage.folder_id)
        if actual == new:
            return
        new_id = await self.maker.rename(stage.folder_id, new)
        self.done.append((new_id, actual))
        stage.folder_id = new_id

    async def undo(self) -> None:
        for item_id, old in reversed(self.done):
            try:
                await self.maker.rename(item_id, old)
            except Exception:  # noqa: BLE001 - the original failure is what matters
                log.exception("could not put back the name of folder %s", item_id)


async def _project(db: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await db.scalar(
        select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
    )
    if project is None:
        raise ApiError(404, ErrorCode.PROJECT_NOT_FOUND)
    return project


async def _maker(request: Request, db: AsyncSession, project: Project):
    """Where stage folders live, or None for a project without a folder."""
    if project.folder_id is None:
        return None
    maker, _root = await _folders(request, db)
    return maker


def _drive_failed(operation: str, tenant: CurrentTenant, project_id: uuid.UUID, error) -> ApiError:
    """AGENTS.md: the detail in the log at ERROR with the office and the
    operation (the request id comes with every line); staff see "try again"."""
    log.error(
        "stage folders: %s failed for %s/%s: %s", operation, tenant.id, project_id, error.detail
    )
    return ApiError(503, ErrorCode.DRIVE_CONNECT_FAILED)


async def _run(
    db: AsyncSession,
    renames: Renames,
    work,
    operation: str,
    tenant: CurrentTenant,
    project_id: uuid.UUID,
) -> None:
    try:
        await work()
        await db.commit()
    except ConnectError as error:
        await db.rollback()
        await renames.undo()
        raise _drive_failed(operation, tenant, project_id, error) from None
    except BaseException:
        await db.rollback()
        await renames.undo()
        raise


class NewStageIn(BaseModel):
    row_version: int
    builtin_key: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=STAGE_TITLE_MAX)


@router.post(
    "/projects/{project_id}/stages", status_code=204, responses=documented(401, 404, 409, 422, 503)
)
async def add_stage(
    request: Request,
    project_id: uuid.UUID,
    body: NewStageIn,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """At the end: a built-in stage (not already in the project) or the office's own.
    A new stage is open, so a completed project is active again (stages complete
    independently)."""
    stages = await _stages(db, project_id)
    if body.builtin_key is not None:
        titles = await db.scalar(select(StageDef.titles).where(StageDef.key == body.builtin_key))
        if titles is None or any(s.builtin_key == body.builtin_key for s in stages):
            raise ApiError(422, ErrorCode.INVALID_STAGE)
        title, values = _text(titles, tenant.locale), {"builtin_key": body.builtin_key}
    else:
        title = (body.title or "").strip()
        if not title:
            raise ApiError(422, ErrorCode.INVALID_STAGE)
        values = {"title": title}
    # The Drive connection first: getting it may itself save (an expired grant).
    current = await _project(db, project_id)
    maker = await _maker(request, db, current)
    reopens = current.status is ProjectStatus.COMPLETED
    project = await _change(
        db, project_id, body.row_version, {"status": ProjectStatus.ACTIVE} if reopens else None
    )
    position = len(stages) + 1
    folder = None
    try:
        if maker is not None:
            folder = await maker.create_folder(_folder_name(position, title), project.folder_id)
        db.add(ProjectStage(project_id=project_id, position=position, folder_id=folder, **values))
        await db.commit()
    except BaseException as error:
        await db.rollback()
        if folder is not None:
            await maker.trash(folder)  # nothing saved: the new folder goes too
        if isinstance(error, ConnectError):
            raise _drive_failed("add stage", tenant, project_id, error) from None
        raise
    posthog_client = getattr(request.app.state, "posthog", None)
    if posthog_client is not None:
        posthog_client.capture(
            "stage_added",
            properties={
                "stage_kind": "builtin" if body.builtin_key is not None else "custom",
                "stage_position": position,
                "reopened_project": reopens,
            },
        )
    return Response(status_code=204)


class RenameIn(BaseModel):
    row_version: int
    title: str = Field(max_length=STAGE_TITLE_MAX)


@router.patch(
    "/projects/{project_id}/stages/{position}",
    status_code=204,
    responses=documented(401, 404, 409, 422, 503),
)
async def rename_stage(
    request: Request,
    project_id: uuid.UUID,
    position: int,
    body: RenameIn,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """A built-in stage renamed becomes the office's own, keeping its description."""
    title = body.title.strip()
    if not title:
        raise ApiError(422, ErrorCode.INVALID_STAGE)
    stage = next((s for s in await _stages(db, project_id) if s.position == position), None)
    if stage is None:
        raise ApiError(404, ErrorCode.PROJECT_NOT_FOUND)
    maker = await _maker(request, db, await _project(db, project_id))
    project = await _change(db, project_id, body.row_version)
    old_title = await _title(db, stage, tenant.locale)
    about = stage.about
    if stage.builtin_key is not None:
        own = await db.scalar(
            select(ProjectTypeStage.about).where(
                ProjectTypeStage.project_type == project.project_type,
                ProjectTypeStage.stage_key == stage.builtin_key,
            )
        )
        general = await db.scalar(select(StageDef.about).where(StageDef.key == stage.builtin_key))
        about = _text(own or general, tenant.locale)
    renames = Renames(maker)

    async def work():
        await renames.rename(
            stage, _folder_name(position, old_title), _folder_name(position, title)
        )
        await db.execute(
            update(ProjectStage)
            .where(ProjectStage.id == stage.id)
            .values(builtin_key=None, title=title, about=about, folder_id=stage.folder_id)
        )

    await _run(db, renames, work, "rename stage", tenant, project_id)
    capture(request, "stage_renamed")
    return Response(status_code=204)


class MoveIn(BaseModel):
    row_version: int
    direction: Literal[-1, 1]


@router.post(
    "/projects/{project_id}/stages/{position}/move",
    status_code=204,
    responses=documented(401, 404, 409, 422, 503),
)
async def move_stage(
    request: Request,
    project_id: uuid.UUID,
    position: int,
    body: MoveIn,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """Swap with its neighbour. The current stage stays the same stage."""
    stages = {s.position: s for s in await _stages(db, project_id)}
    other_position = position + body.direction
    if position not in stages or other_position not in stages:
        raise ApiError(422, ErrorCode.INVALID_STAGE)
    maker = await _maker(request, db, await _project(db, project_id))
    await _change(db, project_id, body.row_version)
    moving, other = stages[position], stages[other_position]
    moving_title = await _title(db, moving, tenant.locale)
    other_title = await _title(db, other, tenant.locale)
    renames = Renames(maker)

    async def work():
        await renames.rename(
            moving, _folder_name(position, moving_title), _folder_name(other_position, moving_title)
        )
        await renames.rename(
            other, _folder_name(other_position, other_title), _folder_name(position, other_title)
        )
        # The unique position check is deferred to the commit, so a swap passes.
        await db.execute(
            update(ProjectStage)
            .where(ProjectStage.id == moving.id)
            .values(position=other_position, folder_id=moving.folder_id)
        )
        await db.execute(
            update(ProjectStage)
            .where(ProjectStage.id == other.id)
            .values(position=position, folder_id=other.folder_id)
        )

    await _run(db, renames, work, "move stage", tenant, project_id)
    capture(request, "stage_moved")
    return Response(status_code=204)


class OrderIn(BaseModel):
    row_version: int
    # The stages' present positions, in their new order: [2, 1, 3] swaps the first two.
    order: list[int] = Field(max_length=100)


@router.put(
    "/projects/{project_id}/stages/order",
    status_code=204,
    responses=documented(401, 404, 409, 422, 503),
)
async def reorder_stages(
    request: Request,
    project_id: uuid.UUID,
    body: OrderIn,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """Every stage in its new place at once (edit mode's "Reordenar etapas"), their
    folders renumbered. The current stage stays the same stage, wherever it goes."""
    stages = {s.position: s for s in await _stages(db, project_id)}
    if sorted(body.order) != sorted(stages):
        raise ApiError(422, ErrorCode.INVALID_STAGE)  # each stage once, none missing
    maker = await _maker(request, db, await _project(db, project_id))
    await _change(db, project_id, body.row_version)
    moves = [(stages[old], old, new) for new, old in enumerate(body.order, start=1) if old != new]
    titles = {stage.id: await _title(db, stage, tenant.locale) for stage, _, _ in moves}
    renames = Renames(maker)

    async def work():
        for stage, old, new in moves:
            title = titles[stage.id]
            await renames.rename(stage, _folder_name(old, title), _folder_name(new, title))
        # The unique position check is deferred to the commit, so stages can trade places.
        for stage, _old, new in moves:
            await db.execute(
                update(ProjectStage)
                .where(ProjectStage.id == stage.id)
                .values(position=new, folder_id=stage.folder_id)
            )

    await _run(db, renames, work, "reorder stages", tenant, project_id)
    capture(request, "stages_reordered")
    return Response(status_code=204)


@router.delete(
    "/projects/{project_id}/stages/{position}",
    status_code=204,
    responses=documented(401, 404, 409, 503),
)
async def remove_stage(
    request: Request,
    project_id: uuid.UUID,
    position: int,
    row_version: int,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """The stage leaves the page; its folder and files stay in Drive. The stages
    after it move up, and their folders are renumbered."""
    stages = await _stages(db, project_id)
    removed = next((s for s in stages if s.position == position), None)
    if removed is None:
        raise ApiError(404, ErrorCode.PROJECT_NOT_FOUND)
    maker = await _maker(request, db, await _project(db, project_id))
    await _change(db, project_id, row_version)
    later = [s for s in stages if s.position > position]
    titles = {s.id: await _title(db, s, tenant.locale) for s in later}
    renames = Renames(maker)

    async def work():
        for stage in later:
            title = titles[stage.id]
            await renames.rename(
                stage,
                _folder_name(stage.position, title),
                _folder_name(stage.position - 1, title),
            )
        await db.execute(delete(ProjectStage).where(ProjectStage.id == removed.id))
        for stage in later:
            await db.execute(
                update(ProjectStage)
                .where(ProjectStage.id == stage.id)
                .values(position=stage.position - 1, folder_id=stage.folder_id)
            )

    await _run(db, renames, work, "remove stage", tenant, project_id)
    capture(request, "stage_removed")
    return Response(status_code=204)


class CompletionIn(BaseModel):
    row_version: int
    completed: bool


@router.put(
    "/projects/{project_id}/stages/{position}/completion",
    status_code=204,
    responses=documented(401, 404, 409, 422),
)
async def set_completion(
    request: Request,
    project_id: uuid.UUID,
    position: int,
    body: CompletionIn,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """Mark a stage as completed, or reopen it, whatever the other stages are. The
    client sees it at once; "Atualizado" moves. Either is recorded for the client's
    email (A32; reopening too since 25 Oct 2026). The last stage completed completes the project (an
    active one), and reopening one makes a completed project active again."""
    stages = await _stages(db, project_id)
    stage = next((s for s in stages if s.position == position), None)
    if stage is None:
        raise ApiError(404, ErrorCode.PROJECT_NOT_FOUND)  # as the other stage routes
    await _complete(db, tenant, project_id, stages, stage, body.completed, body.row_version)
    posthog_client = getattr(request.app.state, "posthog", None)
    if posthog_client is not None:
        posthog_client.capture(
            "stage_completion_changed",
            properties={"completed": body.completed, "stage_position": position},
        )
    return Response(status_code=204)


async def _complete(
    db: AsyncSession,
    tenant: CurrentTenant,
    project_id: uuid.UUID,
    stages: list[ProjectStage],
    stage: ProjectStage,
    completed: bool,
    row_version: int,
) -> None:
    """Mark `stage` as completed or reopen it, and commit. Reopening a stage makes a
    completed project active again; completing the last one leaves the project to
    staff ("Concluir projeto")."""
    project = await db.scalar(
        select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
    )
    if project is None:
        raise ApiError(404, ErrorCode.PROJECT_NOT_FOUND)
    if (stage.completed_at is not None) == completed:
        raise ApiError(422, ErrorCode.INVALID_STATUS_CHANGE)  # already so
    now = datetime.now(UTC)
    values: dict = {"last_activity_at": now}
    if not completed and project.status is ProjectStatus.COMPLETED:
        values["status"] = ProjectStatus.ACTIVE
    await _change(db, project_id, row_version, values)
    await db.execute(
        update(ProjectStage)
        .where(ProjectStage.id == stage.id)
        .values(completed_at=now if completed else None)
    )
    record(
        db,
        project,
        EventKind.STAGE_COMPLETED if completed else EventKind.STAGE_REOPENED,
        stage_position=stage.position,
        stage_id=stage.id,
        title=await _title(db, stage, tenant.locale),
    )
    await db.commit()


class ProjectCompletionIn(BaseModel):
    row_version: int


@router.put(
    "/projects/{project_id}/completion",
    status_code=204,
    responses=documented(401, 404, 409, 422),
)
async def complete_project(
    request: Request,
    project_id: uuid.UUID,
    body: ProjectCompletionIn,
    _staff: CurrentStaff = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """ "Concluir projeto": an active project whose stages are all completed. Staff
    are asked when they complete the last stage, and can do it later; the client
    sees it at once and is told by email (A32)."""
    await _finish(db, project_id, body.row_version)
    posthog_client = getattr(request.app.state, "posthog", None)
    if posthog_client is not None:
        posthog_client.capture("project_completed")
    return Response(status_code=204)


async def _finish(db: AsyncSession, project_id: uuid.UUID, row_version: int) -> None:
    project = await _project(db, project_id)
    stages = await _stages(db, project_id)
    if project.status is ProjectStatus.ARCHIVED:
        raise ApiError(409, ErrorCode.PROJECT_ARCHIVED)  # as every change (section 22)
    if project.status is not ProjectStatus.ACTIVE or any(s.completed_at is None for s in stages):
        raise ApiError(422, ErrorCode.INVALID_STATUS_CHANGE)
    values = {"status": ProjectStatus.COMPLETED, "last_activity_at": datetime.now(UTC)}
    await _change(db, project_id, row_version, values)
    record(db, project, EventKind.PROJECT_COMPLETED)
    await db.commit()


class ProgressIn(BaseModel):
    row_version: int
    action: Literal["advance", "back", "complete", "reopen"]


@router.post(
    "/projects/{project_id}/progress",
    status_code=204,
    responses=documented(401, 404, 409, 422),
    deprecated=True,
)
async def progress(
    project_id: uuid.UUID,
    body: ProgressIn,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """The previous release's progress, for a tab still running its code during a
    deploy (A30); remove in the release after independent stages. "advance" and
    "complete" complete the first open stage; "back" and "reopen" reopen the last
    completed one."""
    stages = await _stages(db, project_id)
    finishing = body.action in ("advance", "complete")
    candidates = [s for s in stages if (s.completed_at is None) == finishing]
    if not candidates:
        raise ApiError(422, ErrorCode.INVALID_STATUS_CHANGE)
    stage = candidates[0] if finishing else candidates[-1]
    await _complete(db, tenant, project_id, stages, stage, finishing, body.row_version)
    if body.action == "complete" and len(candidates) == 1:  # it completed the project
        await _finish(db, project_id, body.row_version + 1)
    return Response(status_code=204)
