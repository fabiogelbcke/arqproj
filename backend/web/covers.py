"""Storing a project's cover, and the stock photos staff can choose from.

    GET /api/cover-photos                 the stock photos, for the picker
    GET /api/cover-photos/{name}/{size}   one of them (`full` or `small`)

The cover lives in the office's storage, in a `_capa` folder inside the
project's folder: Google Drive through the office's grant, or the local folder
in development. Like the office logo, its type is read from the bytes. A stock
photo chosen as the cover is copied there like an uploaded one, so the client
page, its preview tags and "Remover foto" treat both alike.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.projects.cover_photos import (
    PhotoSize,
    cover_photo,
    cover_photo_names,
    cover_photo_version,
    random_cover_photo,
)
from backend.projects.enums import CoverType
from backend.projects.models import Project
from backend.storage.base import StorageError
from backend.storage.google_connect import ConnectError
from backend.storage.models import ReaderStatus, StorageConnection, StorageKind
from backend.tenancy.resolve import CurrentTenant
from backend.web.auth import CurrentStaff, current_staff
from backend.web.drive import writer_for
from backend.web.errors import ApiError, ErrorCode
from backend.web.office import image_type

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

COVER_MAX_BYTES = 10 * 1024 * 1024
COVER_FOLDER = "_capa"
_EXTENSIONS = {CoverType.PNG: "png", CoverType.JPEG: "jpg", CoverType.WEBP: "webp"}
# The same files for every office; the address carries the file's fingerprint.
PHOTO_HEADERS = {"Cache-Control": "private, max-age=86400"}


async def storage_connection(request: Request, db: AsyncSession) -> StorageConnection | None:
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


def local_root(request: Request, connection: StorageConnection) -> Path:
    return Path(request.app.state.settings.local_storage_root) / connection.root_id


async def store_cover(
    request: Request, db: AsyncSession, tenant: CurrentTenant, project: Project, content: bytes
) -> None:
    """Make `content` the project's cover, in its `_capa` folder; the previous
    one is removed (to the Drive trash). Committed."""
    if len(content) > COVER_MAX_BYTES:
        raise ApiError(413, ErrorCode.COVER_TOO_LARGE)
    try:
        cover_type = CoverType(image_type(content))
    except ValueError:  # not an image, or an SVG
        raise ApiError(415, ErrorCode.COVER_WRONG_TYPE) from None
    if project.folder_id is None:
        raise ApiError(409, ErrorCode.PROJECT_HAS_NO_FOLDER)
    name = f"capa.{_EXTENSIONS[cover_type]}"
    connection = await storage_connection(request, db)
    previous = project.cover_file_id
    writer = None  # Drive's, whose old file is trashed once the new one is saved

    if connection is not None and connection.kind is StorageKind.FOLDER:
        root = local_root(request, connection)
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
    project.cover_type = cover_type
    # Always an UPDATE, so the trigger moves `updated_at` and the cover's address
    # (its `?v=`) changes even when the file kept its name (locally, capa.jpg).
    flag_modified(project, "cover_file_id")
    await db.commit()
    db.expire_all()
    if previous and writer is not None:
        # Only once the project points at the new one, as the office's logo.
        await writer.trash(previous)


def stock_photo_bytes(name: str) -> bytes:
    """A stock photo at cover size; 404 for a name that is not one of them."""
    path = cover_photo(name)
    if path is None:
        raise ApiError(404, ErrorCode.COVER_PHOTO_NOT_FOUND)
    return path.read_bytes()


async def give_default_cover(
    request: Request, db: AsyncSession, tenant: CurrentTenant, project: Project
) -> None:
    """A new project's first cover: a stock photo picked at random. The project
    is already saved, so a failure here only leaves it without a cover (the
    painel shows a placeholder and staff can add one); it never fails creation."""
    name, project_id = random_cover_photo(), project.id
    try:
        await store_cover(request, db, tenant, project, stock_photo_bytes(name))
    except (ApiError, ConnectError, StorageError, OSError) as error:
        await db.rollback()
        log.warning(
            "default cover %s not set on %s in %s: %r", name, project_id, tenant.slug, error
        )


class CoverPhoto(BaseModel):
    name: str
    small_url: str


@router.get("/cover-photos", responses={401: {}})
async def cover_photos(_staff: CurrentStaff = Depends(current_staff)) -> list[CoverPhoto]:
    return [
        CoverPhoto(
            name=name,
            small_url=f"/api/cover-photos/{name}/{PhotoSize.SMALL}"
            f"?v={cover_photo_version(name, PhotoSize.SMALL)}",
        )
        for name in cover_photo_names()
    ]


@router.get("/cover-photos/{name}/{size}", include_in_schema=False)
async def cover_photo_file(
    name: str, size: PhotoSize, _staff: CurrentStaff = Depends(current_staff)
) -> FileResponse:
    path = cover_photo(name, size)
    if path is None:
        raise ApiError(404, ErrorCode.COVER_PHOTO_NOT_FOUND)
    return FileResponse(path, media_type=CoverType.JPEG.value, headers=PHOTO_HEADERS)
