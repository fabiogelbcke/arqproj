"""A project's settings in the painel (A24): the "Projeto" dialog and the card's
photo button.

    PATCH  /api/projects/{id}         name, client; archive or restore
    POST   /api/projects/{id}/publish a draft goes live (from the page's staff bar)
    PUT    /api/projects/{id}/cover   upload the cover photo
    DELETE /api/projects/{id}/cover   back to the placeholder photo
    GET    /api/projects/{id}/cover   the cover (staff only until the client page)

Anyone signed in may change these. A change carries the `row_version` the screen
loaded; if someone else saved the project meanwhile, it is refused with
`project_changed` instead of silently overwriting their change (plan section 7).

The cover lives in the office's storage, in a `_capa` folder inside the
project's folder: Google Drive through the office's grant, or the local folder
in development. Like the office logo, its type is read from the bytes.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.projects.creation import NAME_MAX, project_named
from backend.projects.enums import CoverType, ProjectStatus
from backend.projects.models import CLIENT_NAME_MAX, Project
from backend.storage.base import StorageError
from backend.storage.connections import storage_for
from backend.storage.google_connect import ConnectError
from backend.storage.models import ReaderStatus, StorageConnection, StorageKind
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web.auth import CurrentStaff, current_staff, require_csrf
from backend.web.drive import writer_for
from backend.web.errors import ApiError, ErrorCode, documented
from backend.web.office import image_type
from backend.web.projects import ProjectSummary, summaries

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

COVER_MAX_BYTES = 10 * 1024 * 1024
COVER_FOLDER = "_capa"
COVER_SIZE = 1280  # pixels on the long side, from Drive's thumbnails: enough for a card
_EXTENSIONS = {CoverType.PNG: "png", CoverType.JPEG: "jpg", CoverType.WEBP: "webp"}
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


async def _project(db: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await db.scalar(
        select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
    )
    if project is None:
        raise ApiError(404, ErrorCode.PROJECT_NOT_FOUND)
    return project


async def _summary(db: AsyncSession, tenant: CurrentTenant, project_id: uuid.UUID):
    return (await summaries(db, tenant.locale, only=project_id))[0]


@router.patch("/projects/{project_id}", responses=documented(401, 404, 409, 422))
async def change_project(
    project_id: uuid.UUID,
    body: ProjectChange,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> ProjectSummary:
    project = await _project(db, project_id)
    values: dict = {}
    if body.name is not None:
        name = body.name.strip()
        if not name or len(name) > NAME_MAX:
            raise ApiError(422, ErrorCode.INVALID_PROJECT_NAME)
        if (other := await project_named(db, name, other_than=project.id)) is not None:
            raise ApiError(409, ErrorCode.PROJECT_NAME_TAKEN, other)
        values["name"] = name
    if body.client_name is not None:
        client = body.client_name.strip()
        if not client or len(client) > CLIENT_NAME_MAX:
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
    if values:
        # Only if nobody saved it since the screen loaded it.
        changed = await db.execute(
            update(Project)
            .where(Project.id == project.id, Project.row_version == body.row_version)
            .values(**values, row_version=Project.row_version + 1)
        )
        if changed.rowcount != 1:
            raise ApiError(409, ErrorCode.PROJECT_CHANGED)
        await db.commit()
    elif project.row_version != body.row_version:
        raise ApiError(409, ErrorCode.PROJECT_CHANGED)
    db.expire_all()
    return await _summary(db, tenant, project_id)


@router.post("/projects/{project_id}/publish", responses=documented(401, 404, 422))
async def publish(
    project_id: uuid.UUID,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> ProjectSummary:
    """A draft goes live: its page opens to anyone with the link (A24: from the
    project page's staff bar). Publishing twice changes nothing."""
    project = await _project(db, project_id)
    if project.status is ProjectStatus.DRAFT:
        await db.execute(
            update(Project)
            .where(Project.id == project.id, Project.status == ProjectStatus.DRAFT)
            .values(status=ProjectStatus.ACTIVE, row_version=Project.row_version + 1)
        )
        await db.commit()
    elif project.status is not ProjectStatus.ACTIVE:
        raise ApiError(422, ErrorCode.INVALID_STATUS_CHANGE)  # completed or archived
    db.expire_all()
    return await _summary(db, tenant, project_id)


async def _connection(request: Request, db: AsyncSession) -> StorageConnection | None:
    connection = await db.scalar(select(StorageConnection))
    if connection is not None and connection.kind is StorageKind.FOLDER:
        if request.app.state.settings.deployed:
            raise ApiError(409, ErrorCode.DRIVE_NOT_CONNECTED)
        return connection
    if connection is not None and connection.reader_status is not ReaderStatus.OK:
        # Uploaded through the office's grant, shown through the reader: it would
        # never display.
        raise ApiError(409, ErrorCode.DRIVE_UNREADABLE)
    return connection


def _local_root(request: Request, connection: StorageConnection) -> Path:
    return Path(request.app.state.settings.local_storage_root) / connection.root_id


@router.put("/projects/{project_id}/cover", responses=documented(401, 404, 409, 413, 415, 503))
async def upload_cover(
    request: Request,
    project_id: uuid.UUID,
    file: UploadFile,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> ProjectSummary:
    project = await _project(db, project_id)
    if project.status is ProjectStatus.ARCHIVED:
        raise ApiError(409, ErrorCode.PROJECT_ARCHIVED)
    content = await file.read(COVER_MAX_BYTES + 1)
    if len(content) > COVER_MAX_BYTES:
        raise ApiError(413, ErrorCode.COVER_TOO_LARGE)
    try:
        cover_type = CoverType(image_type(content))
    except ValueError:  # not an image, or an SVG
        raise ApiError(415, ErrorCode.COVER_WRONG_TYPE) from None
    if project.folder_id is None:
        raise ApiError(409, ErrorCode.PROJECT_HAS_NO_FOLDER)
    name = f"capa.{_EXTENSIONS[cover_type]}"
    connection = await _connection(request, db)
    previous = project.cover_file_id

    if connection is not None and connection.kind is StorageKind.FOLDER:
        root = _local_root(request, connection)
        folder = Path(project.folder_id) / COVER_FOLDER
        (root / folder).mkdir(parents=True, exist_ok=True)
        (root / folder / name).write_bytes(content)
        project.cover_folder_id = folder.as_posix()
        project.cover_file_id = (folder / name).as_posix()
        if previous and previous != project.cover_file_id:
            (root / previous).unlink(missing_ok=True)
    else:
        connection, writer = await writer_for(request, db)
        try:
            if not (project.cover_folder_id and await writer.can_open(project.cover_folder_id)):
                project.cover_folder_id = await writer.create_folder(
                    COVER_FOLDER, project.folder_id
                )
            project.cover_file_id = await writer.upload(
                name, project.cover_folder_id, content, cover_type
            )
        except ConnectError as error:
            log.error("cover upload to Drive failed for %s: %s", tenant.slug, error.detail)
            raise ApiError(503, ErrorCode.DRIVE_CONNECT_FAILED) from None
        if previous:
            await writer.trash(previous)
    project.cover_type = cover_type
    await db.commit()
    db.expire_all()
    return await _summary(db, tenant, project_id)


@router.delete("/projects/{project_id}/cover", responses=documented(401, 404, 409, 503))
async def remove_cover(
    request: Request,
    project_id: uuid.UUID,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> ProjectSummary:
    project = await _project(db, project_id)
    previous = project.cover_file_id
    if previous is not None:
        connection = await db.scalar(select(StorageConnection))
        if connection is not None and connection.kind is StorageKind.FOLDER:
            (_local_root(request, connection) / previous).unlink(missing_ok=True)
        else:
            # The photo goes to the office's Drive trash, where it can be recovered.
            _, writer = await writer_for(request, db)
            await writer.trash(previous)
        project.cover_file_id = project.cover_type = None
        await db.commit()
    db.expire_all()
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
    connection = await db.scalar(select(StorageConnection))
    if project is None or project.cover_file_id is None or connection is None:
        return Response(status_code=404)
    try:
        google = getattr(request.app.state, "google", None)  # set up at app start
        storage = storage_for(connection, request.app.state.settings, google)
        item = await storage.get(project.cover_file_id)
        small = await storage.thumbnail(item, size)
        if small is not None and (kind := image_type(small)) in set(CoverType):
            return Response(small, media_type=kind, headers=headers)
        download = await storage.download(item)
    except StorageError as error:
        log.warning("cover unavailable: %s %s", error.problem, error.detail)
        return Response(status_code=404)

    async def body():
        try:
            async for chunk in download.chunks:
                yield chunk
        finally:
            await download.aclose()

    return StreamingResponse(body(), media_type=project.cover_type.value, headers=headers)
