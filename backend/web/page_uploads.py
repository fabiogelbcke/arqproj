"""Uploading files from the project page's edit mode, and hiding them (A31).

    POST /api/projects/{id}/stages/{n}/uploads   open an upload; says where to send the file
    POST .../uploads/check                       which names would be a new version (A25)
    POST .../uploads/failed                      the browser's report of one that failed
    PUT  /api/local-uploads/{token}              local folders only (never deployed): take it
    POST /api/pages/{slug}/files/{key}/hide      "Ocultar do cliente": a leading "_"
    POST /api/pages/{slug}/files/{key}/move      "Mover para outra etapa"

Any staff member uploads, at most 100 MB a file (Fabio, 16 Oct 2026). The app
checks the request and opens a Google resumable upload in the stage's folder
through the office's grant; the browser then sends the bytes straight to Google,
so they never pass through Cloud Run (32 MB a request). With local folders the
app stands in for Google at `/api/local-uploads/{token}`. Nothing is recorded:
the page lists Drive live (A10), so a finished upload shows on the next load.

Versions (A25, plan section 12) are worked out from names, so an upload is a
version by the name it is saved with. "Enviar nova versão" on a file
(`version_of`, its key) saves the chosen file as the next version in that
file's folder: `Planta v3.pdf` after `Planta v2.pdf`. Before an upload the page
asks `uploads/check` which names match a document already in the stage, and
asks staff "É uma nova versão de Planta.pdf?"; yes sends `version_of`, no a
plain upload, which is saved apart ("Planta (2).pdf") so it never joins it.
Nothing reserves a number while the bytes travel to Google: two new versions of
one document opened at the same moment both get the next number, and the page
flags the clash for staff to rename one (plan section 12).
Hiding renames it with a leading "_", which the page never shows (A05); moving
puts it in another stage's folder, where the page shows it next. The office's
grant (drive.file) reaches only files the app created, so a file put straight
into Drive is hidden or moved there (`file_not_ours`, `file_not_ours_to_move`).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.documents import versions
from backend.documents.versions import shown_name
from backend.projects.creation import LocalFolders
from backend.projects.enums import ProjectStatus
from backend.projects.models import Project, ProjectStage
from backend.security import keys
from backend.storage.base import StorageError
from backend.storage.google_connect import ConnectError
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web.auth import CurrentStaff, require_csrf
from backend.web.errors import ApiError, ErrorCode, documented
from backend.web.page_files import _file, _in_project, _item, _item_at, _list, _showable, _storage
from backend.web.pages import _origin, _readable
from backend.web.projects import _folders

log = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_MAX_MB = 100
UPLOAD_MAX = UPLOAD_MAX_MB * 1024 * 1024
LOCAL_PURPOSE = "local-upload"
LOCAL_SECONDS = 3600  # like Google's session, it is used at once


class UploadIn(BaseModel):
    # The page's: stages may have moved since it loaded (plan section 7).
    row_version: int
    name: str = Field(max_length=255)
    size: int = Field(ge=0)
    mime_type: str = Field(default="", max_length=255)
    # "Enviar nova versão": a file's key from the page; saved as the next version
    # of its document, in its folder.
    version_of: str | None = Field(default=None, max_length=2000)


class UploadOut(BaseModel):
    # Send the file here with one PUT: Google's upload session, or the app's own
    # stand-in for local folders.
    upload_url: str


def _clean(name: str) -> str:
    """A file name, never a path. Invisible spaces (macOS puts a narrow one before
    "PM" in screenshot names) become plain ones; other invisible characters go."""
    shown = (ch if ch.isprintable() else " " if ch.isspace() else "" for ch in name)
    cleaned = "".join(shown).replace("/", "-").replace("\\", "-")
    cleaned = cleaned.strip()
    if cleaned in ("", ".", ".."):
        raise ApiError(422, ErrorCode.INVALID_FILE_NAME)
    if cleaned.startswith("_"):
        raise ApiError(422, ErrorCode.HIDDEN_FILE_NAME)  # the page would never show it (A05)
    return cleaned


async def _changeable(db: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await db.scalar(
        select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
    )
    if project is None:
        raise ApiError(404, ErrorCode.PROJECT_NOT_FOUND)
    if project.status is ProjectStatus.ARCHIVED:
        raise ApiError(409, ErrorCode.PROJECT_ARCHIVED)  # viewable, not changed (section 22)
    return project


async def _stage_for_upload(
    request: Request, db: AsyncSession, tenant: CurrentTenant, project_id, position, row_version
):
    """The project, the stage and the office's storage view, if files may go in."""
    project = await _changeable(db, project_id)
    if project.row_version != row_version:
        # Someone moved or removed stages meanwhile: this position may now be
        # another stage, and the file would go to its folder.
        raise ApiError(409, ErrorCode.PROJECT_CHANGED)
    stage = await db.scalar(
        select(ProjectStage).where(
            ProjectStage.project_id == project_id, ProjectStage.position == position
        )
    )
    if stage is None:
        raise ApiError(404, ErrorCode.PROJECT_NOT_FOUND)
    if stage.folder_id is None:
        raise ApiError(409, ErrorCode.STAGE_HAS_NO_FOLDER)
    # Only into a folder the page shows: one moved out of the project in Drive
    # would take the file where no one sees it (A05, section 11).
    reader = await _storage(request, db)
    try:
        if reader is not None and stage.folder_id not in await _in_project(reader, project):
            raise ApiError(409, ErrorCode.STAGE_HAS_NO_FOLDER)
    except StorageError as error:
        raise _listing_failed(error, tenant, project_id, position) from None
    return project, stage, reader


def _listing_failed(error: StorageError, tenant: CurrentTenant, project_id, position) -> ApiError:
    log.error(
        "uploads: checking the stage folder failed for %s/%s, stage %s: %s %s",
        tenant.id,
        project_id,
        position,
        error.problem,
        error.detail,
    )
    return ApiError(503, ErrorCode.FILES_UNAVAILABLE)


async def _documents(reader, folder: str) -> list[versions.Document]:
    """The folder's documents, as the page shows them."""
    return versions.group([i for i in await _list(reader, folder) if _showable(i)])


async def _as_new_version(
    request: Request, db: AsyncSession, tenant: CurrentTenant, project: Project, position, key, name
) -> tuple[str, str]:
    """The folder and the name a new version of the file the key names goes in
    with: the next version of its document, in the file's own folder."""
    reader, item, found = await _item_at(request, db, project, key)  # still listed
    if found.get("s") != position:
        raise ApiError(409, ErrorCode.PROJECT_CHANGED)  # the page's stages are out of date
    try:
        documents = await _documents(reader, found["f"])
    except StorageError as error:
        raise _listing_failed(error, tenant, project.id, position) from None
    document = next((d for d in documents if any(i.id == item.id for _n, i in d.versions)), None)
    if document is None:
        raise ApiError(404, ErrorCode.FILE_NOT_FOUND)  # gone since
    extension = versions.parse(name).extension.casefold()
    if extension != document.named.extension.casefold():
        raise ApiError(422, ErrorCode.VERSION_TYPE_MISMATCH)  # it would not group
    return found["f"], versions.next_name(documents, document)


@router.post(
    "/api/projects/{project_id}/stages/{position}/uploads",
    responses=documented(401, 404, 409, 422, 503),
)
async def start_upload(
    request: Request,
    project_id: uuid.UUID,
    position: int,
    body: UploadIn,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> UploadOut:
    if body.size > UPLOAD_MAX:
        raise ApiError(422, ErrorCode.FILE_TOO_LARGE)
    name = _clean(body.name)
    project, stage, reader = await _stage_for_upload(
        request, db, tenant, project_id, position, body.row_version
    )
    folder = stage.folder_id
    if body.version_of is not None:
        folder, name = await _as_new_version(
            request, db, tenant, project, position, body.version_of, name
        )
    elif reader is not None:
        try:
            # Never joins a document by accident: that is what "yes" is for.
            name = versions.apart(await _documents(reader, folder), name)
        except StorageError as error:
            raise _listing_failed(error, tenant, project_id, position) from None
    maker, _root = await _folders(request, db)
    if isinstance(maker, LocalFolders):
        token = keys.encrypt(
            request.app.state.settings.app_secret,
            LOCAL_PURPOSE,
            json.dumps(
                {
                    "t": str(tenant.id),
                    "f": folder,
                    "n": name,
                    "s": body.size,
                    "exp": int(time.time()) + LOCAL_SECONDS,
                }
            ),
        )
        return UploadOut(upload_url=f"/api/local-uploads/{token}")
    # The browser's own origin, so Google lets that page send the bytes (CORS).
    origin = request.headers.get("origin") or _origin(request, tenant)
    try:
        url = await maker.start_upload(
            name, folder, body.size, body.mime_type or "application/octet-stream", origin
        )
    except ConnectError as error:
        log.error(
            "uploads: opening an upload failed for %s/%s, stage %s: %s",
            tenant.id,
            project_id,
            position,
            error.detail,
        )
        raise ApiError(503, ErrorCode.DRIVE_CONNECT_FAILED) from None
    log.info(
        "uploads: opened for %s/%s, stage %s, %s bytes", tenant.id, project_id, position, body.size
    )
    return UploadOut(upload_url=url)


class CheckIn(BaseModel):
    row_version: int
    names: list[str] = Field(max_length=100)


class MatchOut(BaseModel):
    name: str  # as chosen
    document: str  # the document it matches, as the page names it: "Planta.pdf"
    current: str  # its current version's name in Drive: "Planta v2.pdf"
    current_version: int
    saved_as: str  # its name in Drive as a new version: "Planta v3.pdf"
    next_version: int
    key: str  # the document's current version: `version_of` for "yes"


class CheckOut(BaseModel):
    matches: list[MatchOut]


@router.post(
    "/api/projects/{project_id}/stages/{position}/uploads/check",
    responses=documented(401, 404, 409, 503),
)
async def check_upload(
    request: Request,
    project_id: uuid.UUID,
    position: int,
    body: CheckIn,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> CheckOut:
    """Which of these names match a document in the stage's folder, so the page
    can ask "É uma nova versão de Planta.pdf?" (A25)."""
    project, stage, reader = await _stage_for_upload(
        request, db, tenant, project_id, position, body.row_version
    )
    if reader is None:
        return CheckOut(matches=[])
    try:
        documents = await _documents(reader, stage.folder_id)
    except StorageError as error:
        raise _listing_failed(error, tenant, project_id, position) from None
    matches = []
    for name in body.names:
        try:
            saved = _clean(name)  # as the upload will save it
        except ApiError:
            continue  # refused when sent, with its reason
        document = versions.same_document(documents, saved)
        if document is not None:
            saved_as = versions.next_name(documents, document)
            matches.append(
                MatchOut(
                    name=name,
                    document=document.name,
                    current=shown_name(document.current),
                    current_version=document.versions[0][0],
                    saved_as=saved_as,
                    next_version=versions.parse(saved_as).version,
                    key=_file(request, project, document.current, position, stage.folder_id).key,
                )
            )
    return CheckOut(matches=matches)


class UploadFailedIn(BaseModel):
    name: str = Field(max_length=255)
    size: int = Field(ge=0)
    status: int  # Google's answer; 0 when the connection kept breaking
    detail: str = Field(default="", max_length=500)  # the start of Google's answer


@router.post(
    "/api/projects/{project_id}/stages/{position}/uploads/failed",
    status_code=502,
    responses=documented(401, 502),
)
async def upload_failed(
    project_id: uuid.UUID,
    position: int,
    body: UploadFailedIn,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
) -> Response:
    """The bytes go from the browser to Google, past the app; when sending fails
    for good, the browser reports it here, so it is logged with the office and the
    operation, and staff get the support code that the log line carries."""
    log.error(
        "uploads: sending failed for %s/%s, stage %s: %r (%s bytes), status %s: %s",
        tenant.id,
        project_id,
        position,
        body.name,
        body.size,
        body.status,
        body.detail,
    )
    raise ApiError(502, ErrorCode.UPLOAD_FAILED)


def _free_name(folder: Path, name: str) -> Path:
    """Drive keeps two files of one name; a disk can't, so the new one is "(2)"."""
    stem, dot, extension = name.rpartition(".") if "." in name[1:] else (name, "", "")
    candidate, n = folder / name, 2
    while candidate.exists():
        candidate, n = folder / f"{stem} ({n}){dot}{extension}", n + 1
    return candidate


@router.put("/api/local-uploads/{token}", status_code=201, include_in_schema=False)
async def receive_local_upload(
    request: Request,
    token: str,
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """Google's part, for local folders: the token, like Google's session
    address, is what allows the upload."""
    if request.app.state.settings.deployed:
        return Response(status_code=404)  # never a way onto the server's disk
    try:
        found = json.loads(
            keys.decrypt(request.app.state.settings.app_secret, LOCAL_PURPOSE, token)
        )
    except (keys.BadToken, ValueError):
        return Response(status_code=404)
    if found.get("t") != str(tenant.id) or found.get("exp", 0) < time.time():
        return Response(status_code=404)
    maker, _root = await _folders(request, db)
    if not isinstance(maker, LocalFolders):
        return Response(status_code=404)
    root = maker.root.resolve()
    folder = (root / found["f"]).resolve()
    if not folder.is_relative_to(root) or not folder.is_dir():
        return Response(status_code=404)
    await db.close()  # the body may be slow to arrive: keep no connection meanwhile
    expected = found["s"]
    partial = folder / f"_upload-{uuid.uuid4().hex}.part"  # hidden from the page meanwhile
    received = 0
    try:
        with partial.open("wb") as out:
            async for chunk in request.stream():
                received += len(chunk)
                if received > expected:
                    raise ApiError(413, ErrorCode.FILE_TOO_LARGE)
                out.write(chunk)
        if received != expected:
            raise ApiError(400, ErrorCode.INVALID_REQUEST)
        target = _free_name(folder, found["n"])
        partial.rename(target)
    finally:
        partial.unlink(missing_ok=True)
    return JSONResponse({"id": target.relative_to(root).as_posix()}, status_code=201)


@router.post(
    "/api/pages/{slug}/files/{key}/hide", status_code=204, responses=documented(401, 404, 409, 503)
)
async def hide_file(
    request: Request,
    slug: str,
    key: str,
    staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """The file stays in Drive, renamed "_name", which the page doesn't show."""
    project = await _readable(db, slug, staff, request)
    await _changeable(db, project.id)
    _storage, item = await _item(request, db, project, key)
    maker, _root = await _folders(request, db)
    try:
        if not await maker.can_rename(item.id):
            raise ApiError(409, ErrorCode.FILE_NOT_OURS)
        await maker.rename(item.id, f"_{item.name}")
    except ConnectError as error:
        log.error(
            "uploads: hiding %s failed for %s/%s: %s", item.id, tenant.id, project.id, error.detail
        )
        raise ApiError(503, ErrorCode.DRIVE_CONNECT_FAILED) from None
    return Response(status_code=204)


class MoveIn(BaseModel):
    # The page's: stages may have moved since it loaded (plan section 7).
    row_version: int
    position: int  # the stage it goes to, from 1


@router.post(
    "/api/pages/{slug}/files/{key}/move", status_code=204, responses=documented(401, 404, 409, 503)
)
async def move_file(
    request: Request,
    slug: str,
    key: str,
    body: MoveIn,
    staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """Into another stage's folder, at its top. The file keeps its identity, so
    it is not "new" again and sends no email (A10)."""
    project = await _readable(db, slug, staff, request)
    await _changeable(db, project.id)
    if project.row_version != body.row_version:
        raise ApiError(409, ErrorCode.PROJECT_CHANGED)  # that position may be another stage now
    stage = await db.scalar(
        select(ProjectStage).where(
            ProjectStage.project_id == project.id, ProjectStage.position == body.position
        )
    )
    if stage is None:
        raise ApiError(404, ErrorCode.PROJECT_NOT_FOUND)
    if stage.folder_id is None:
        raise ApiError(409, ErrorCode.STAGE_HAS_NO_FOLDER)
    reader, item = await _item(request, db, project, key)
    try:
        if stage.folder_id not in await _in_project(reader, project):
            raise ApiError(409, ErrorCode.STAGE_HAS_NO_FOLDER)  # moved out of the project in Drive
    except StorageError as error:
        log.error(
            "uploads: checking the stage folder failed for %s/%s, stage %s: %s %s",
            tenant.id,
            project.id,
            body.position,
            error.problem,
            error.detail,
        )
        raise ApiError(503, ErrorCode.FILES_UNAVAILABLE) from None
    maker, _root = await _folders(request, db)
    try:
        if not await maker.can_rename(item.id):
            raise ApiError(409, ErrorCode.FILE_NOT_OURS_TO_MOVE)
        await maker.move(item.id, stage.folder_id)
    except ConnectError as error:
        log.error(
            "uploads: moving %s failed for %s/%s: %s", item.id, tenant.id, project.id, error.detail
        )
        raise ApiError(503, ErrorCode.DRIVE_CONNECT_FAILED) from None
    return Response(status_code=204)
