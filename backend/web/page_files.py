"""Each stage's files on the client's page (step 2.5).

    GET /api/pages/{slug}/files              every stage's files, read live
    GET /api/pages/{slug}/files/{key}        one file: download, or ?inline=1
    GET /api/pages/{slug}/files/{key}/thumb  its small preview image

A stage shows the files directly in its folder, and each subfolder as a titled
group (one level; Fabio, 16 Oct 2026). Names starting with "_" stay hidden (the
office's own, like `_capa`), and so do shortcuts (their target may lie outside
the office's folder) and Google formats that can't be exported.

A file is named by a signed key, never by its Drive id: the key carries the
project, its `access_version` and the item, so it opens only what this page
listed, and a new password or access mode ends every key handed out before.
Bytes come through the office's storage view (the reader identity on Drive),
which refuses anything outside the office's folder.
"""

from __future__ import annotations

import logging
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.projects.enums import AccessMode
from backend.projects.models import Project, ProjectStage
from backend.security import keys
from backend.storage.base import StorageError, StorageItem
from backend.storage.connections import storage_for
from backend.storage.models import StorageConnection
from backend.web.auth import CurrentStaff, optional_staff
from backend.web.errors import ApiError, ErrorCode, documented
from backend.web.office import image_type
from backend.web.pages import PAGE_HEADERS, _readable

log = logging.getLogger(__name__)
router = APIRouter()

KEY_PURPOSE = "page-file"
KEY_HOURS = 12  # a listed file's key; the page lists again on every visit
THUMB_SIZE = 480
# Shown in the page itself; everything else only downloads.
INLINE_IMAGES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
PDF = "application/pdf"


class FileOut(BaseModel):
    key: str
    name: str
    kind: str  # "image", "pdf" or "other"
    size: int | None
    modified_at: datetime


class GroupOut(BaseModel):
    folder: str | None  # None: files directly in the stage's folder
    files: list[FileOut]


class StageFilesOut(BaseModel):
    position: int  # the stage's place on the page, from 1
    groups: list[GroupOut]
    unavailable: bool = False  # Drive couldn't be read just now


class PageFilesOut(BaseModel):
    stages: list[StageFilesOut]


def _hidden(item: StorageItem) -> bool:
    return item.name.startswith("_") or item.is_shortcut


def _showable(item: StorageItem) -> bool:
    if _hidden(item) or item.is_folder:
        return False
    return not item.is_native or item.exports_as_pdf


def _kind(item: StorageItem) -> str:
    if item.mime_type in INLINE_IMAGES:
        return "image"
    if item.mime_type == PDF or item.is_native:  # Google's formats come as PDF
        return "pdf"
    return "other"


def _private(project: Project, staff: CurrentStaff | None) -> dict[str, str]:
    """Never in a shared cache; a short private one for a public page's files."""
    if staff is not None or project.access_mode is AccessMode.PASSWORD:
        return {"Cache-Control": "private, no-store"}
    return {"Cache-Control": "private, max-age=300"}


def _file(request: Request, project: Project, item: StorageItem) -> FileOut:
    key = keys.sign(
        request.app.state.settings.app_secret,
        KEY_PURPOSE,
        {"p": str(project.id), "v": project.access_version, "i": item.id},
        KEY_HOURS * 3600,
    )
    name = f"{item.name}.pdf" if item.is_native else item.name
    return FileOut(
        key=key, name=name, kind=_kind(item), size=item.size, modified_at=item.modified_at
    )


async def _storage(request: Request, db: AsyncSession):
    connection = await db.scalar(select(StorageConnection))
    if connection is None:
        return None
    google = getattr(request.app.state, "google", None)  # set up at app start
    return storage_for(connection, request.app.state.settings, google)


@router.get("/api/pages/{slug}/files", responses=documented(403, 404))
async def page_files(
    request: Request,
    slug: str,
    response: Response,
    staff: CurrentStaff | None = Depends(optional_staff),
    db: AsyncSession = Depends(get_tenant_session),
) -> PageFilesOut:
    project = await _readable(db, slug, staff, request)
    response.headers.update({**PAGE_HEADERS, **_private(project, staff)})
    storage = await _storage(request, db)
    folders = list(
        await db.scalars(
            select(ProjectStage.folder_id)
            .where(ProjectStage.project_id == project.id)
            .order_by(ProjectStage.position)
        )
    )
    stages = []
    for position, folder in enumerate(folders, start=1):
        shown = StageFilesOut(position=position, groups=[])
        if folder is None or storage is None:
            stages.append(shown)
            continue
        try:
            items = await storage.list_folder(folder)
            direct = [_file(request, project, i) for i in items if _showable(i)]
            if direct:
                shown.groups.append(GroupOut(folder=None, files=direct))
            for sub in (i for i in items if i.is_folder and not _hidden(i)):
                inside = await storage.list_folder(sub.id)
                inner = [_file(request, project, i) for i in inside if _showable(i)]
                if inner:
                    shown.groups.append(GroupOut(folder=sub.name, files=inner))
        except StorageError as error:
            log.warning(
                "stage %s of %s unreadable: %s %s", position, slug, error.problem, error.detail
            )
            shown.unavailable = True
            shown.groups = []
        stages.append(shown)
    return PageFilesOut(stages=stages)


async def _item(request: Request, db: AsyncSession, project: Project, key: str):
    """The storage and the item a key names, if it was issued for this project's
    current access."""
    try:
        found = keys.verify(request.app.state.settings.app_secret, KEY_PURPOSE, key)
    except keys.BadToken:
        raise ApiError(404, ErrorCode.FILE_NOT_FOUND) from None
    if found.get("p") != str(project.id) or found.get("v") != project.access_version:
        raise ApiError(404, ErrorCode.FILE_NOT_FOUND)
    storage = await _storage(request, db)
    if storage is None:
        raise ApiError(404, ErrorCode.FILE_NOT_FOUND)
    try:
        return storage, await storage.get(found["i"])
    except StorageError as error:
        log.warning("file unavailable: %s %s", error.problem, error.detail)
        raise ApiError(404, ErrorCode.FILE_NOT_FOUND) from None


def _disposition(name: str, inline: bool) -> str:
    ascii_name = name.encode("ascii", "replace").decode().replace('"', "'")
    how = "inline" if inline else "attachment"
    return f"{how}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"


@router.get("/api/pages/{slug}/files/{key}", include_in_schema=False)
async def page_file(
    request: Request,
    slug: str,
    key: str,
    inline: bool = False,
    staff: CurrentStaff | None = Depends(optional_staff),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    try:
        project = await _readable(db, slug, staff, request)
        storage, item = await _item(request, db, project, key)
        download = await storage.download(item)
    except (ApiError, StorageError):
        return Response(status_code=404, headers=PAGE_HEADERS)
    kind = _kind(item)
    shown_inline = inline and kind in ("image", "pdf")
    name = f"{item.name}.pdf" if item.is_native else item.name
    headers = {
        **PAGE_HEADERS,
        **_private(project, staff),
        "Content-Disposition": _disposition(name, shown_inline),
        "X-Content-Type-Options": "nosniff",
        # Nothing in a file may run on the office's address. A PDF keeps the
        # browser's own viewer, which a sandbox would block.
        "Content-Security-Policy": "default-src 'none'"
        + ("" if kind == "pdf" and shown_inline else "; sandbox"),
    }
    if download.size is not None:
        headers["Content-Length"] = str(download.size)
    media_type = download.media_type if shown_inline else "application/octet-stream"

    async def body():
        try:
            async for chunk in download.chunks:
                yield chunk
        finally:
            await download.aclose()

    return StreamingResponse(body(), media_type=media_type, headers=headers)


@router.get("/api/pages/{slug}/files/{key}/thumb", include_in_schema=False)
async def page_file_thumb(
    request: Request,
    slug: str,
    key: str,
    staff: CurrentStaff | None = Depends(optional_staff),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    try:
        project = await _readable(db, slug, staff, request)
        storage, item = await _item(request, db, project, key)
        small = await storage.thumbnail(item, THUMB_SIZE)
    except (ApiError, StorageError):
        return Response(status_code=404, headers=PAGE_HEADERS)
    kind = image_type(small) if small is not None else None
    if kind is None or kind not in INLINE_IMAGES:  # none here (local folders), or odd bytes
        return Response(status_code=404, headers=PAGE_HEADERS)
    return Response(
        small,
        media_type=kind,
        headers={
            **PAGE_HEADERS,
            **_private(project, staff),
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
