"""Uploading files from the project page's edit mode, and hiding them (A31).

    POST /api/projects/{id}/stages/{n}/uploads   open an upload; says where to send the file
    PUT  /api/local-uploads/{token}              local folders only (never deployed): take it
    POST /api/pages/{slug}/files/{key}/hide      "Ocultar do cliente": a leading "_"

Any staff member uploads, at most 100 MB a file (Fabio, 16 Oct 2026). The app
checks the request and opens a Google resumable upload in the stage's folder
through the office's grant; the browser then sends the bytes straight to Google,
so they never pass through Cloud Run (32 MB a request). With local folders the
app stands in for Google at `/api/local-uploads/{token}`. Nothing is recorded:
the page lists Drive live (A10), so a finished upload shows on the next load.

A file named like one already there is kept beside it until versions (A25).
Hiding renames it with a leading "_", which the page never shows (A05). The
office's grant (drive.file) reaches only files the app created, so a file put
straight into Drive is hidden by renaming it there (`file_not_ours`).
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
from backend.projects.creation import LocalFolders
from backend.projects.enums import ProjectStatus
from backend.projects.models import Project, ProjectStage
from backend.security import keys
from backend.storage.google_connect import ConnectError
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web.auth import CurrentStaff, require_csrf
from backend.web.errors import ApiError, ErrorCode, documented
from backend.web.page_files import _item
from backend.web.pages import _origin, _readable
from backend.web.projects import _folders

log = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_MAX_MB = 100
UPLOAD_MAX = UPLOAD_MAX_MB * 1024 * 1024
LOCAL_PURPOSE = "local-upload"
LOCAL_SECONDS = 3600  # like Google's session, it is used at once


class UploadIn(BaseModel):
    name: str = Field(max_length=255)
    size: int = Field(ge=0)
    mime_type: str = Field(default="", max_length=255)


class UploadOut(BaseModel):
    # Send the file here with one PUT: Google's upload session, or the app's own
    # stand-in for local folders.
    upload_url: str


def _clean(name: str) -> str:
    """A file name, never a path."""
    cleaned = "".join(ch for ch in name if ch.isprintable()).replace("/", "-").replace("\\", "-")
    cleaned = cleaned.strip()
    if cleaned in ("", ".", ".."):
        raise ApiError(422, ErrorCode.INVALID_FILE_NAME)
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
    await _changeable(db, project_id)
    stage = await db.scalar(
        select(ProjectStage).where(
            ProjectStage.project_id == project_id, ProjectStage.position == position
        )
    )
    if stage is None:
        raise ApiError(404, ErrorCode.PROJECT_NOT_FOUND)
    if stage.folder_id is None:
        raise ApiError(409, ErrorCode.STAGE_HAS_NO_FOLDER)
    maker, _root = await _folders(request, db)
    if isinstance(maker, LocalFolders):
        token = keys.encrypt(
            request.app.state.settings.app_secret,
            LOCAL_PURPOSE,
            json.dumps(
                {
                    "t": str(tenant.id),
                    "f": stage.folder_id,
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
            name, stage.folder_id, body.size, body.mime_type or "application/octet-stream", origin
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
