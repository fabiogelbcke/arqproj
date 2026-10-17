"""Each stage's files on the client's page (step 2.5).

    GET /api/pages/{slug}/files              every stage's files, read live
    GET /api/pages/{slug}/files/{key}        one file: download, or ?inline=1
    GET /api/pages/{slug}/files/{key}/thumb  its small preview image

A stage shows the files directly in its folder, and each subfolder as a titled
group (one level; Fabio, 16 Oct 2026). Names starting with "_" stay hidden (the
office's own, like `_capa`), and so do shortcuts (their target may lie outside
the office's folder) and Google formats that can't be exported.

A file is named by an encrypted key, never by its Drive id: the key carries the
project, its `access_version`, the stage, the folder and the item, so it opens
only what this page listed (rechecked against Drive on every request), and a
new password or access mode ends every key handed out before.
Bytes come through the office's storage view (the reader identity on Drive),
which refuses anything outside the office's folder; a stage's folder shows only
while it is still directly in its project's folder.

The page links straight to a file, so a failure there answers with a short page
in the office's language (and the support code), not the API's JSON.
"""

from __future__ import annotations

import html
import json
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.notifications.models import EventKind, ProjectEvent
from backend.projects.enums import AccessMode, ProjectStatus
from backend.projects.models import Project, ProjectStage
from backend.security import keys
from backend.storage.base import StorageError, StorageItem, StorageProblem
from backend.storage.connections import storage_for
from backend.storage.models import StorageConnection
from backend.tenancy.models import Locale
from backend.tenancy.resolve import CurrentTenant, current_tenant
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
# The page's own words, for the one answer a browser shows directly: a file
# link that fails (AGENTS.md, user-facing errors).
_TEXTS = {
    locale: json.loads((Path(__file__).parent.parent / "i18n" / f"{locale.value}.json").read_text())
    for locale in Locale
}


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


class UpdateOut(BaseModel):
    """One entry of the page's "Atualizações" (A28), newest first. The page words
    it from what it shows now (the stage's title and note, the meeting)."""

    id: uuid.UUID  # what the visitor's browser remembers as read
    kind: EventKind
    occurred_at: datetime
    stage_position: int | None  # a file's: the stage it is in now
    # A file's name as the page shows it now; a cancelled meeting's title.
    name: str | None = None


class PageFilesOut(BaseModel):
    stages: list[StageFilesOut]
    # The support code, when a stage couldn't be read (its detail is in the log).
    reference: str | None = None
    # The latest client-visible changes (A28): files only while the page shows them.
    updates: list[UpdateOut] = []


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


NO_STORE = {"Cache-Control": "private, no-store"}


def _listing_cache(project: Project, staff: CurrentStaff | None) -> dict[str, str]:
    """Never in a shared cache; a short private one for a public page's list: a
    file added in Drive reaches a returning visitor within two minutes (A10).
    The files themselves are never kept, so one removed in Drive stops opening
    at once (A05)."""
    if staff is not None or project.access_mode is AccessMode.PASSWORD:
        return NO_STORE
    return {"Cache-Control": "private, max-age=120"}


async def _list(storage, folder: str) -> list[StorageItem]:
    """Always Drive's current listing: what a key may open is decided now."""
    return await storage.list_folder(folder)


async def _in_project(storage, project: Project) -> set[str]:
    """The folders directly in the project's folder, where its stage folders
    live: a stage folder moved elsewhere (say, into another project's folder)
    stops showing here (A05, plan section 6)."""
    if project.folder_id is None:
        return set()
    return {i.id for i in await _list(storage, project.folder_id) if i.is_folder}


async def stage_groups(storage, folder: str) -> list[tuple[str | None, str, list[StorageItem]]]:
    """What the page shows of one stage folder: its own files, then each visible
    subfolder's (one level), as (group name or None, folder listed, files). The
    maintenance scan reads the same, so it notices exactly what clients see."""
    items = await _list(storage, folder)
    groups = []
    direct = [i for i in items if _showable(i)]
    if direct:
        groups.append((None, folder, direct))
    for sub in (i for i in items if i.is_folder and not _hidden(i)):
        inner = [i for i in await _list(storage, sub.id) if _showable(i)]
        if inner:
            groups.append((sub.name, sub.id, inner))
    return groups


def _file(
    request: Request, project: Project, item: StorageItem, stage: int, folder: str
) -> FileOut:
    """The file with its key: project, access version, stage, the folder it was
    listed in, and the item, so a download can check it's still there."""
    # Encrypted, not just signed: the key never reveals Drive or project ids.
    key = keys.encrypt(
        request.app.state.settings.app_secret,
        KEY_PURPOSE,
        json.dumps(
            {
                "p": str(project.id),
                "v": project.access_version,
                "s": stage,
                "f": folder,
                "i": item.id,
                "exp": int(time.time()) + KEY_HOURS * 3600,
            }
        ),
    )
    name = f"{item.name}.pdf" if item.is_native else item.name
    return FileOut(
        key=key, name=name, kind=_kind(item), size=item.size, modified_at=item.modified_at
    )


async def _storage(request: Request, db: AsyncSession):
    """The office's storage view, or None when there is none to read (no
    connection, or Drive disconnected)."""
    # `google` is set up at app start.
    return await storage_view(
        db, request.app.state.settings, getattr(request.app.state, "google", None)
    )


async def storage_view(db: AsyncSession, settings, google):
    """As `_storage`, outside a request too (the maintenance scan)."""
    connection = await db.scalar(select(StorageConnection))
    if connection is None:
        return None
    try:
        return storage_for(connection, settings, google)
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
    response.headers.update({**PAGE_HEADERS, **_listing_cache(project, staff)})
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
    visible: dict[str, tuple[int, str]] = {}  # each file shown: its stage and name
    in_project: set[str] | None = None
    if storage is not None and any(folders):
        try:
            in_project = await _in_project(storage, project)
        except StorageError as error:
            log.error(
                "files: listing the folder of %s/%s failed: %s %s",
                project.tenant_id,
                slug,
                error.problem,
                error.detail,
            )
            storage = None  # every bound stage shows as unavailable
            has_connection = True
    for position, folder in enumerate(folders, start=1):
        shown = StageFilesOut(position=position, groups=[])
        if folder is None:
            stages.append(shown)
            continue
        if storage is None:  # a bound folder that can't be read at all
            shown.unavailable = has_connection
            stages.append(shown)
            continue
        if folder not in (in_project or set()):
            log.warning(
                "files: stage %s of %s/%s is not in its project folder",
                position,
                project.tenant_id,
                slug,
            )
            stages.append(shown)  # moved out of the project: nothing to show
            continue
        try:
            for group, parent, files in await stage_groups(storage, folder):
                for item in files:
                    name = f"{item.name}.pdf" if item.is_native else item.name
                    visible.setdefault(item.identity, (position, name))
                shown.groups.append(
                    GroupOut(
                        folder=group,
                        files=[_file(request, project, i, position, parent) for i in files],
                    )
                )
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
    return PageFilesOut(
        stages=stages,
        reference=current_request_id() if unavailable else None,
        updates=await _updates(db, project, visible),
    )


UPDATES_SHOWN = 30
UPDATES_DAYS = 180


async def _updates(db: AsyncSession, project: Project, visible: dict) -> list[UpdateOut]:
    """The latest changes the client can see now. A file appears only while the
    page shows it, under its current name and stage; one taken down, or in a stage
    that couldn't be read just now, is left out. A note or a stage advance points at
    where its stage is now, and is left out if the stage was removed. Like the
    panel, only a stage's latest note, the latest advance that still holds and the
    latest meeting change count, so repeated edits never crowd out older news."""
    since = datetime.now(UTC) - timedelta(days=UPDATES_DAYS)
    stages = (
        await db.execute(
            select(ProjectStage.id, ProjectStage.position, ProjectStage.notes).where(
                ProjectStage.project_id == project.id
            )
        )
    ).all()
    positions = {stage.id: stage.position for stage in stages}
    with_notes = {stage.id for stage in stages if stage.notes}
    events = await db.stream_scalars(
        select(ProjectEvent)
        .where(ProjectEvent.project_id == project.id, ProjectEvent.occurred_at >= since)
        .order_by(ProjectEvent.occurred_at.desc())
    )
    updates = []
    counted = set()  # the notes, advance and meeting already listed
    async for event in events:  # until 30 survive the filtering, however many it takes
        position, name = event.stage_position, None
        if event.kind is EventKind.FILE_PUBLISHED:
            if event.item_id not in visible:
                continue
            position, name = visible[event.item_id]
        elif event.stage_id is not None:
            if event.stage_id not in positions:
                continue  # its stage was removed
            position = positions[event.stage_id]
        if event.kind is EventKind.NOTE_CHANGED:
            if event.stage_id is not None and event.stage_id not in with_notes:
                continue  # removed since: the panel shows a note as it is now
            once = ("note", event.stage_id or position)  # older events: by position
        elif event.kind is EventKind.STAGE_ADVANCED:
            if position is None or position > (project.current_position or 0):
                continue  # taken back since
            once = "advance"
        elif event.kind is EventKind.PROJECT_COMPLETED:
            if project.status is not ProjectStatus.COMPLETED:
                continue
            once = "completed"
        elif event.kind is not EventKind.FILE_PUBLISHED:
            once = "meeting"  # the latest change says what the meeting is now
        else:
            once = None
        if once is not None:
            if once in counted:
                continue
            counted.add(once)
        if event.kind is EventKind.MEETING_CLEARED:
            name = event.title
        updates.append(
            UpdateOut(
                id=event.id,
                kind=event.kind,
                occurred_at=event.occurred_at,
                stage_position=position,
                name=name,
            )
        )
        if len(updates) == UPDATES_SHOWN:
            break
    await events.close()
    return updates


async def _item(request: Request, db: AsyncSession, project: Project, key: str):
    """The storage and the item a key names, if it was issued for this project's
    current access."""
    try:
        found = json.loads(keys.decrypt(request.app.state.settings.app_secret, KEY_PURPOSE, key))
    except (keys.BadToken, ValueError):
        raise ApiError(404, ErrorCode.FILE_NOT_FOUND) from None
    if not isinstance(found, dict) or found.get("exp", 0) < time.time():
        raise ApiError(404, ErrorCode.FILE_NOT_FOUND)  # the page lists again on every visit
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
        raise _storage_failure(error, project, "open") from None


def _storage_failure(error: StorageError, project: Project, operation: str) -> ApiError:
    """Gone is "not found"; Drive down or throttled is a failure to report: logged
    at ERROR with the office and operation, answered with the support code."""
    if error.problem in (StorageProblem.NOT_FOUND, StorageProblem.NO_ACCESS):
        return ApiError(404, ErrorCode.FILE_NOT_FOUND)
    log.error(
        "files: %s failed for %s/%s: %s %s",
        operation,
        project.tenant_id,
        project.id,
        error.problem,
        error.detail,
    )
    return ApiError(503, ErrorCode.FILES_UNAVAILABLE)


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
    if stage_folder not in await _in_project(storage, project):
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


def _failure_page(tenant: CurrentTenant, slug: str, code: ErrorCode, status: int) -> Response:
    """What the browser shows when a file link fails: the reason in the office's
    language, the support code for a failure, and the way back; never the API's
    answer. (The page's links open this address directly.)"""
    texts = _TEXTS[tenant.locale]
    lines = [texts["errors"][code.value]]
    if status >= 500:
        lines.append(texts["errors"]["reference"].replace("{{id}}", current_request_id()))
    body = "".join(f"<p>{html.escape(line)}</p>" for line in lines)
    back = html.escape(texts["page"]["backToProject"])
    return HTMLResponse(
        f'<!doctype html><html lang="{tenant.locale.value}"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(lines[0])}</title>"
        '<body style="font: 16px/1.5 system-ui, sans-serif; max-width: 32rem; margin: 15vh auto;'
        f' padding: 0 16px">{body}<p><a href="/{quote(slug)}">{back}</a></p>',
        status_code=status,
        headers={
            **PAGE_HEADERS,
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
        },
    )


@router.get("/api/pages/{slug}/files/{key}", include_in_schema=False)
async def page_file(
    request: Request,
    slug: str,
    key: str,
    inline: bool = False,
    staff: CurrentStaff | None = Depends(optional_staff),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    try:
        project = await _readable(db, slug, staff, request)
        storage, item = await _item(request, db, project, key)
        try:
            download = await storage.download(item)
        except StorageError as error:
            raise _storage_failure(error, project, "download") from None
    except ApiError as error:
        if error.code is ErrorCode.FILES_UNAVAILABLE:
            return _failure_page(tenant, slug, error.code, 503)  # "try again", with the code
        return _failure_page(tenant, slug, ErrorCode.FILE_NOT_FOUND, 404)
    kind = _kind(item)
    shown_inline = inline and kind in ("image", "pdf")
    name = f"{item.name}.pdf" if item.is_native else item.name
    headers = {
        **PAGE_HEADERS,
        **NO_STORE,
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
        except StorageError as error:  # Drive gave up partway: the client sees a cut download
            log.error(
                "files: download broke off for %s/%s, item %s: %s %s",
                project.tenant_id,
                project.id,
                item.id,
                error.problem,
                error.detail,
            )
            raise
        finally:
            await download.aclose()

    # Everything is checked: let the database connection go before the bytes
    # flow, so slow downloads never hold the small pool (plan section 15).
    await db.close()
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
        try:
            small = await storage.thumbnail(item, THUMB_SIZE)
        except StorageError as error:
            raise _storage_failure(error, project, "preview") from None
    except ApiError as error:
        if error.code is ErrorCode.FILES_UNAVAILABLE:
            raise
        return Response(status_code=404, headers=PAGE_HEADERS)
    kind = image_type(small) if small is not None else None
    if kind is None or kind not in INLINE_IMAGES:  # none here (local folders), or odd bytes
        return Response(status_code=404, headers=PAGE_HEADERS)
    return Response(
        small,
        media_type=kind,
        headers={
            **PAGE_HEADERS,
            **NO_STORE,
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
