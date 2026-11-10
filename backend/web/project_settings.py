"""A project's settings in the painel (A24): the "Projeto" dialog and the card's
photo button.

    PATCH  /api/projects/{id}         name, client, address, access, members; archive or restore
    POST   /api/projects/{id}/publish a draft goes live (from the page's staff bar)
    PUT    /api/projects/{id}/cover   upload the cover photo
    PUT    /api/projects/{id}/cover/stock  one of the bundled photos as the cover
    DELETE /api/projects/{id}/cover   no cover (the painel shows a placeholder)
    GET    /api/projects/{id}/cover   the cover (staff only until the client page)

Anyone signed in may change these. A change carries the `row_version` the screen
loaded; if someone else saved the project meanwhile, it is refused with
`project_changed` instead of silently overwriting their change (plan section 7).

The cover lives in the office's storage (see `backend/web/covers.py`). A new
project starts with a stock photo as its cover; staff can choose another stock
photo or upload their own.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics import AnalyticsEvent, capture
from backend.db.engine import get_tenant_session
from backend.identity.emails import InvalidEmail, email_list
from backend.identity.models import User
from backend.identity.passwords import hash_password
from backend.notifications.models import (
    RECIPIENTS_MAX,
    ProjectRecipient,
    RecipientStatus,
)
from backend.projects.creation import CLIENT_NAME_LIMIT, NAME_MAX, project_named, valid_slug
from backend.projects.enums import AccessMode, CoverType, ProjectStatus
from backend.projects.models import Project, ProjectMember, ProjectSlug
from backend.storage.base import StorageError
from backend.storage.connections import storage_for
from backend.storage.models import StorageConnection, StorageKind
from backend.tenancy.models import Feature
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web.access import changeable_project
from backend.web.auth import CurrentStaff, current_staff, require_csrf
from backend.web.covers import COVER_MAX_BYTES, local_root, stock_photo_bytes, store_cover
from backend.web.drive import writer_for
from backend.web.errors import ApiError, ErrorCode, documented
from backend.web.office import image_type
from backend.web.projects import ProjectSummary, summaries

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

PAGE_PASSWORD_MIN = 6  # Fabio, 16 Oct 2026
PAGE_PASSWORD_MAX = 25  # Fabio, 20 Oct 2026
MEMBERS_MAX = 100  # more than any office's team
COVER_SIZE = 1280  # pixels on the long side, from Drive's thumbnails: enough for a card
COVER_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "X-Content-Type-Options": "nosniff",
    # Only staff see covers for now; the address changes with the cover.
    "Cache-Control": "private, max-age=86400",
}


class ProjectChange(BaseModel):
    row_version: int
    name: str | None = Field(default=None, max_length=500)
    client_name: str | None = Field(default=None, max_length=500)
    # "archived", or back from archived to what it was (the toast's "Desfazer").
    status: ProjectStatus | None = None
    # The client's link: a new address, or one the project had before. Old ones
    # keep redirecting here (A29).
    slug: str | None = Field(default=None, max_length=200)
    access_mode: AccessMode | None = None
    # Required when switching to password access; a new one locks out every
    # device that unlocked the page before.
    password: str | None = Field(default=None, max_length=PAGE_PASSWORD_MAX)
    # The client's addresses for email updates, the whole list (A32).
    recipients: list[Annotated[str, Field(max_length=500)]] | None = Field(
        default=None, max_length=RECIPIENTS_MAX
    )
    # Who works on it: the whole list of staff accounts (A41), if the office has
    # the feature (A40).
    members: list[uuid.UUID] | None = Field(default=None, max_length=MEMBERS_MAX)


async def _project(db: AsyncSession, project_id: uuid.UUID, lock: bool = False) -> Project:
    query = select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
    project = await db.scalar(query.with_for_update() if lock else query)
    if project is None:
        raise ApiError(404, ErrorCode.PROJECT_NOT_FOUND)
    return project


def _addresses(given: list[str]) -> list[str]:
    """Trimmed, lowercase, each once, in the order given."""
    try:
        return email_list(given)
    except InvalidEmail:
        raise ApiError(422, ErrorCode.INVALID_EMAIL) from None


async def _set_recipients(db: AsyncSession, project_id: uuid.UUID, wanted: list[str]) -> bool:
    """Add the new addresses, remove the ones left out; an unsubscribed one stays
    (so it is never written to again). Whether anything changed."""
    have = {
        r.email: r
        for r in await db.scalars(
            select(ProjectRecipient).where(ProjectRecipient.project_id == project_id)
        )
    }
    changed = False
    for email, recipient in have.items():
        if email not in wanted and recipient.status is RecipientStatus.SUBSCRIBED:
            await db.delete(recipient)
            changed = True
    for email in wanted:
        if email not in have:
            db.add(ProjectRecipient(project_id=project_id, email=email))
            changed = True
    return changed


async def _set_members(db: AsyncSession, project_id: uuid.UUID, wanted: list[uuid.UUID]) -> bool:
    """Add the new members, remove the ones left out. Each must be one of the
    office's accounts (another office's don't exist here). Whether anything changed."""
    wanted = list(dict.fromkeys(wanted))
    known = set(await db.scalars(select(User.id).where(User.id.in_(wanted)))) if wanted else set()
    if len(known) != len(wanted):
        raise ApiError(422, ErrorCode.UNKNOWN_MEMBER)
    have = {
        m.user_id: m
        for m in await db.scalars(
            select(ProjectMember).where(ProjectMember.project_id == project_id)
        )
    }
    for user_id, member in have.items():
        if user_id not in known:
            await db.delete(member)
    for user_id in wanted:
        if user_id not in have:
            db.add(ProjectMember(project_id=project_id, user_id=user_id))
    return set(have) != known


async def _summary(db: AsyncSession, tenant: CurrentTenant, project_id: uuid.UUID):
    return (await summaries(db, tenant, only=project_id))[0]


@router.patch("/projects/{project_id}", responses=documented(401, 404, 409, 422))
async def change_project(
    project_id: uuid.UUID,
    body: ProjectChange,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> ProjectSummary:
    if body.members is not None and not tenant.has(Feature.PROJECT_MEMBERS):
        raise ApiError(409, ErrorCode.FEATURE_OFF)
    # Locked until this save ends: a second dialog saving at the same moment
    # waits, then finds the new version and gets `project_changed`, rather than
    # colliding on the same new address.
    project = await _project(db, project_id, lock=True)
    values: dict = {}
    if body.name is not None:
        name = body.name.strip()
        # The limit is for names entered from now on: one saved before it stays as is.
        if not name or (name != project.name and len(name) > NAME_MAX):
            raise ApiError(422, ErrorCode.INVALID_PROJECT_NAME)
        if (other := await project_named(db, name, other_than=project.id)) is not None:
            raise ApiError(409, ErrorCode.PROJECT_NAME_TAKEN, other)
        values["name"] = name
    if body.client_name is not None:
        client = body.client_name.strip()
        # The limit is for names entered from now on: one saved before it stays as is.
        if not client or (client != project.client_name and len(client) > CLIENT_NAME_LIMIT):
            raise ApiError(422, ErrorCode.INVALID_CLIENT_NAME)
        values["client_name"] = client
    if body.status is not None and body.status is not project.status:
        # Archiving, or undoing it back to exactly what it was. Publishing and
        # completing belong to the project page (A24).
        if body.status is ProjectStatus.ARCHIVED:
            values |= {"status": body.status, "archived_from": project.status}
        elif body.status is project.archived_from:
            values |= {"status": body.status, "archived_from": None}
        else:
            raise ApiError(422, ErrorCode.INVALID_STATUS_CHANGE)
    access_changed = False
    if body.access_mode is AccessMode.PASSWORD:
        if body.password is not None:
            if len(body.password) < PAGE_PASSWORD_MIN:
                raise ApiError(422, ErrorCode.PASSWORD_TOO_SHORT)
            values["password_hash"] = await hash_password(body.password)
            access_changed = True
        elif project.password_hash is None:
            raise ApiError(422, ErrorCode.PASSWORD_REQUIRED)
        if project.access_mode is not AccessMode.PASSWORD:
            values["access_mode"] = AccessMode.PASSWORD
            access_changed = True
    elif body.access_mode is AccessMode.PUBLIC and project.access_mode is not AccessMode.PUBLIC:
        values |= {"access_mode": AccessMode.PUBLIC, "password_hash": None}
        access_changed = True
    if access_changed:
        values["access_version"] = Project.access_version + 1  # ends every unlock
    recipients = _addresses(body.recipients) if body.recipients is not None else None
    new_slug = None
    if body.slug is not None:
        new_slug = body.slug.strip().lower()
        current = await db.scalar(
            select(ProjectSlug.slug).where(
                ProjectSlug.project_id == project.id, ProjectSlug.is_current
            )
        )
        if new_slug == current:
            new_slug = None
        elif not valid_slug(new_slug):
            raise ApiError(422, ErrorCode.INVALID_SLUG)
        else:
            holder = await db.scalar(
                select(Project.name)
                .join(ProjectSlug, ProjectSlug.project_id == Project.id)
                .where(ProjectSlug.slug == new_slug, Project.id != project.id)
            )
            if holder is not None:  # never another project's, old or current (A29)
                raise ApiError(409, ErrorCode.SLUG_TAKEN, holder)
    recipients_changed = recipients is not None and await _set_recipients(
        db, project.id, recipients
    )
    members_changed = body.members is not None and await _set_members(db, project.id, body.members)
    if values or new_slug or recipients_changed or members_changed:
        # Only if nobody saved it since the screen loaded it.
        changed = await db.execute(
            update(Project)
            .where(Project.id == project.id, Project.row_version == body.row_version)
            .values(**values, row_version=Project.row_version + 1)
        )
        if changed.rowcount != 1:
            await db.rollback()
            raise ApiError(409, ErrorCode.PROJECT_CHANGED)
        try:
            if new_slug:
                await _move_address(db, project.id, new_slug)
            await db.commit()
        except IntegrityError as error:
            # Two people gave the same new address at once: the second loses.
            await db.rollback()
            if "slug" in str(error.orig):
                raise ApiError(409, ErrorCode.SLUG_TAKEN) from None
            raise
    elif project.row_version != body.row_version:
        raise ApiError(409, ErrorCode.PROJECT_CHANGED)
    db.expire_all()
    return await _summary(db, tenant, project_id)


async def _move_address(db: AsyncSession, project_id: uuid.UUID, slug: str) -> None:
    """Make `slug` the project's current address; the previous one stays as an
    old address that redirects (A29). An address it had before is reused."""
    await db.execute(
        update(ProjectSlug)
        .where(ProjectSlug.project_id == project_id, ProjectSlug.is_current)
        .values(is_current=False)
    )
    reused = await db.execute(
        update(ProjectSlug)
        .where(ProjectSlug.project_id == project_id, ProjectSlug.slug == slug)
        .values(is_current=True)
    )
    if reused.rowcount == 0:
        db.add(ProjectSlug(project_id=project_id, slug=slug))
        await db.flush()


@router.post("/projects/{project_id}/publish", responses=documented(401, 404, 409, 422))
async def publish(
    request: Request,
    project_id: uuid.UUID,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> ProjectSummary:
    """A draft goes live: its page opens to anyone with the link. New projects are
    published at once (A35), so only a draft left over shows the staff bar's
    button: one created by the previous release during a deploy, or an open tab
    of it (A30). Publishing twice changes nothing."""
    project = await _project(db, project_id)
    if project.status is ProjectStatus.DRAFT:
        published = await db.execute(
            update(Project)
            .where(Project.id == project.id, Project.status == ProjectStatus.DRAFT)
            .values(status=ProjectStatus.ACTIVE, row_version=Project.row_version + 1)
        )
        if published.rowcount != 1:  # someone archived it meanwhile
            raise ApiError(409, ErrorCode.PROJECT_CHANGED)
        await db.commit()
        capture(request, AnalyticsEvent.PROJECT_PUBLISHED)
    elif project.status is not ProjectStatus.ACTIVE:
        raise ApiError(422, ErrorCode.INVALID_STATUS_CHANGE)  # completed or archived
    db.expire_all()
    return await _summary(db, tenant, project_id)


@router.put("/projects/{project_id}/cover", responses=documented(401, 404, 409, 413, 415, 503))
async def upload_cover(
    request: Request,
    project_id: uuid.UUID,
    file: UploadFile,
    project: Project = Depends(changeable_project),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> ProjectSummary:
    content = await file.read(COVER_MAX_BYTES + 1)
    await store_cover(request, db, tenant, project, content)
    capture(request, AnalyticsEvent.PROJECT_COVER_SET)
    return await _summary(db, tenant, project_id)


class StockCoverChoice(BaseModel):
    name: str = Field(max_length=40)  # one of GET /api/cover-photos


@router.put("/projects/{project_id}/cover/stock", responses=documented(401, 404, 409, 503))
async def choose_stock_cover(
    request: Request,
    project_id: uuid.UUID,
    body: StockCoverChoice,
    project: Project = Depends(changeable_project),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> ProjectSummary:
    """One of the bundled photos as the cover, stored like an uploaded one."""
    await store_cover(request, db, tenant, project, stock_photo_bytes(body.name))
    capture(request, AnalyticsEvent.PROJECT_COVER_SET, {"stock": True})
    return await _summary(db, tenant, project_id)


@router.delete("/projects/{project_id}/cover", responses=documented(401, 404, 409, 503))
async def remove_cover(
    request: Request,
    project_id: uuid.UUID,
    project: Project = Depends(changeable_project),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> ProjectSummary:
    """The cover goes; an archived project keeps its own, as its other content."""
    previous = project.cover_file_id
    if previous is not None:
        connection = await db.scalar(select(StorageConnection))
        if connection is not None and connection.kind is StorageKind.FOLDER:
            (local_root(request, connection) / previous).unlink(missing_ok=True)
        else:
            # The photo goes to the office's Drive trash, where it can be recovered.
            _, writer = await writer_for(request, db)
            await writer.trash(previous)
        project.cover_file_id = project.cover_type = None
        await db.commit()
    db.expire_all()
    capture(request, AnalyticsEvent.PROJECT_COVER_REMOVED)
    return await _summary(db, tenant, project_id)


@router.get("/projects/{project_id}/cover", include_in_schema=False)
async def cover(
    request: Request,
    project_id: uuid.UUID,
    _staff: CurrentStaff = Depends(current_staff),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    project = await db.scalar(
        select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
    )
    return await serve_cover(request, db, project, COVER_SIZE, COVER_HEADERS)


async def serve_cover(
    request: Request,
    db: AsyncSession,
    project: Project | None,
    size: int,
    headers: dict[str, str],
) -> Response:
    """The cover through the office's storage, shrunk by Drive to `size` pixels
    where it can; otherwise the original. 404 when there is none to show."""
    if project is None or project.cover_file_id is None:
        return Response(status_code=404)
    return await serve_stored_image(
        request, db, project.cover_file_id, project.cover_type, size, headers
    )


async def serve_stored_image(
    request: Request,
    db: AsyncSession,
    file_id: str,
    media_type: CoverType,
    size: int,
    headers: dict[str, str],
) -> Response:
    """A photo kept in the office's storage (a cover, a portfolio photo), shrunk
    by Drive to `size` pixels where it can; otherwise the original. 404 when it
    can't be read."""
    connection = await db.scalar(select(StorageConnection))
    if connection is None:
        return Response(status_code=404)
    try:
        google = getattr(request.app.state, "google", None)  # set up at app start
        storage = storage_for(connection, request.app.state.settings, google)
        item = await storage.get(file_id)
        small = await storage.thumbnail(item, size)
        if small is not None and (kind := image_type(small)) in set(CoverType):
            return Response(small, media_type=kind, headers=headers)
        download = await storage.download(item)
    except StorageError as error:
        log.warning("photo unavailable: %s %s", error.problem, error.detail)
        return Response(status_code=404)

    async def body():
        try:
            async for chunk in download.chunks:
                yield chunk
        finally:
            await download.aclose()

    await db.close()  # before streaming: never hold a database connection meanwhile
    return StreamingResponse(body(), media_type=media_type.value, headers=headers)
