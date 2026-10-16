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
import time
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
from backend.web.request_id import current_request_id

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
    # The support code, when a stage couldn't be read (its detail is in the log).
    reference: str | None = None


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


# Folder listings, kept a minute: checking a file is still where its key says
# (on every download and preview) would otherwise list Drive once per card.
LISTING_SECONDS = 60
_listings: dict[str, tuple[float, list[StorageItem]]] = {}


async def _list(storage, folder: str, fresh: bool = False) -> list[StorageItem]:
    now = time.monotonic()
    cached = _listings.get(folder)
    if not fresh and cached and now - cached[0] < LISTING_SECONDS:
        return cached[1]
    items = await storage.list_folder(folder)
    _listings[folder] = (now, items)
    return items


def forget_listings() -> None:
    """For tests."""
    _listings.clear()


def _file(
    request: Request, project: Project, item: StorageItem, stage: int, folder: str
) -> FileOut:
    """The file with its key: project, access version, stage, the folder it was
    listed in, and the item, so a download can check it's still there."""
    key = keys.sign(
        request.app.state.settings.app_secret,
        KEY_PURPOSE,
        {
            "p": str(project.id),
            "v": project.access_version,
            "s": stage,
            "f": folder,
            "i": item.id,
        },
        KEY_HOURS * 3600,
    )
    name = f"{item.name}.pdf" if item.is_native else item.name
    return FileOut(
        key=key, name=name, kind=_kind(item), size=item.size, modified_at=item.modified_at
    )


async def _storage(request: Request, db: AsyncSession):
    """The office's storage view, or None when there is none to read (no
    connection, or Drive disconnected)."""
    connection = await db.scalar(select(StorageConnection))
    if connection is None:
        return None
    google = getattr(request.app.state, "google", None)  # set up at app start
    try:
        return storage_for(connection, request.app.state.settings, google)
    except StorageError as error:  # e.g. the office disconnected Drive
        log.error(
            "files: storage unusable for %s: %s %s",
            connection.tenant_id,
            error.problem,
            error.detail,
        )
        return None


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
    has_connection = await db.scalar(select(StorageConnection.id)) is not None
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
        if folder is None:
            stages.append(shown)
            continue
        if storage is None:  # a bound folder that can't be read at all
            shown.unavailable = has_connection
            stages.append(shown)
            continue
        try:
            items = await _list(storage, folder, fresh=True)
            direct = [_file(request, project, i, position, folder) for i in items if _showable(i)]
            if direct:
                shown.groups.append(GroupOut(folder=None, files=direct))
            for sub in (i for i in items if i.is_folder and not _hidden(i)):
                inside = await _list(storage, sub.id, fresh=True)
                inner = [
                    _file(request, project, i, position, sub.id) for i in inside if _showable(i)
                ]
                if inner:
                    shown.groups.append(GroupOut(folder=sub.name, files=inner))
        except StorageError as error:
            # AGENTS.md: the detail in the log at ERROR, with the support code shown.
            log.error(
                "files: listing stage %s of %s/%s failed: %s %s",
                position,
                project.tenant_id,
                slug,
                error.problem,
                error.detail,
            )
            shown.unavailable = True
            shown.groups = []
        stages.append(shown)
    unavailable = any(stage.unavailable for stage in stages)
    return PageFilesOut(stages=stages, reference=current_request_id() if unavailable else None)


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
        if not await _still_listed(db, storage, project, found):
            raise ApiError(404, ErrorCode.FILE_NOT_FOUND)  # moved, hidden or removed
        return storage, await storage.get(found["i"])
    except StorageError as error:
        log.warning("file unavailable: %s %s", error.problem, error.detail)
        raise ApiError(404, ErrorCode.FILE_NOT_FOUND) from None


async def _still_listed(db: AsyncSession, storage, project: Project, found: dict) -> bool:
    """The item is still where the page would list it (A05, plan section 6): in
    the stage's folder, or in a visible subfolder of it, and still shown."""
    stage_folder = await db.scalar(
        select(ProjectStage.folder_id).where(
            ProjectStage.project_id == project.id, ProjectStage.position == found.get("s")
        )
    )
    folder = found.get("f")
    if stage_folder is None or folder is None:
        return False
    if folder != stage_folder:
        siblings = await _list(storage, stage_folder)
        if not any(i.id == folder and i.is_folder and not _hidden(i) for i in siblings):
            return False
    return any(i.id == found.get("i") and _showable(i) for i in await _list(storage, folder))


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
