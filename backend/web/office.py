"""The office's details in the painel (Configurações → Escritório).

    GET   /api/office        name, contact email, logo; anyone signed in
    PATCH /api/office        change name and contact email (owners)
    PUT   /api/office/logo   upload the logo (owners; needs the office's storage)
    GET   /api/office/logo   the logo itself, public (client pages show it)

The logo is stored in the office's own storage, in a `_marca` folder inside its
root: Google Drive (through the office's grant), or the local folder in
development. An SVG may contain scripts, so the logo is only ever served with a
policy that forbids running anything, and the painel shows it as an image.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.identity.models import Role
from backend.office.models import NAME_MAX, LogoType, OfficeProfile
from backend.office.profile import profile as load_profile
from backend.storage.base import StorageError
from backend.storage.connections import storage_for
from backend.storage.google_connect import ConnectError
from backend.storage.models import ReaderStatus, StorageConnection, StorageKind
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web.auth import CurrentStaff, current_staff, require_csrf
from backend.web.drive import writer_for
from backend.web.errors import ApiError, ErrorCode, documented

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

LOGO_MAX_BYTES = 5 * 1024 * 1024  # shown small, but exported logos are often large
BRAND_FOLDER = "_marca"
_EXTENSIONS = {
    LogoType.PNG: "png",
    LogoType.JPEG: "jpg",
    LogoType.WEBP: "webp",
    LogoType.SVG: "svg",
}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
# Served as an image only: nothing in it may run, load or be framed.
LOGO_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "public, max-age=300",
}


class OfficeOut(BaseModel):
    name: str
    contact_email: str | None
    logo_url: str | None  # changes when the logo does, so browsers fetch the new one
    can_manage: bool


class OfficeIn(BaseModel):
    name: str | None = None
    contact_email: str | None = None


def _out(tenant: CurrentTenant, found: OfficeProfile | None, staff: CurrentStaff) -> OfficeOut:
    has_logo = found is not None and found.logo_file_id is not None
    return OfficeOut(
        name=found.display_name if found else tenant.name,
        contact_email=found.contact_email if found else None,
        # Microseconds: two changes within a second still get different addresses.
        logo_url=f"/api/office/logo?v={found.updated_at.timestamp():.6f}" if has_logo else None,
        can_manage=staff.role is Role.OWNER,
    )


async def _profile_for_change(db: AsyncSession, tenant: CurrentTenant) -> OfficeProfile:
    found = await load_profile(db)
    if found is None:
        found = OfficeProfile(display_name=tenant.name)
        db.add(found)
    return found


def _owner(staff: CurrentStaff) -> None:
    if staff.role is not Role.OWNER:
        raise ApiError(403, ErrorCode.OWNER_ONLY)


@router.get("/office", responses=documented(401))
async def office(
    staff: CurrentStaff = Depends(current_staff),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> OfficeOut:
    return _out(tenant, await load_profile(db), staff)


@router.patch("/office", responses=documented(401, 403, 422))
async def change_office(
    body: OfficeIn,
    staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> OfficeOut:
    _owner(staff)
    found = await _profile_for_change(db, tenant)
    if body.name is not None:
        name = body.name.strip()
        if not name or len(name) > NAME_MAX:
            raise ApiError(422, ErrorCode.INVALID_OFFICE_NAME)
        found.display_name = name
    if body.contact_email is not None:
        email = body.contact_email.strip().lower()
        if email and not _EMAIL.match(email):
            raise ApiError(422, ErrorCode.INVALID_EMAIL)
        found.contact_email = email or None
    await db.commit()
    await db.refresh(found)
    return _out(tenant, found, staff)


def _logo_type(content: bytes) -> LogoType | None:
    """From the bytes, never from the file name or the browser's word."""
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return LogoType.PNG
    if content.startswith(b"\xff\xd8\xff"):
        return LogoType.JPEG
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return LogoType.WEBP
    head = content[:2048].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if (head.startswith(b"<?xml") or head.startswith(b"<svg")) and b"<svg" in head:
        return LogoType.SVG
    return None


@router.put("/office/logo", responses=documented(401, 403, 409, 413, 415, 503))
async def upload_logo(
    request: Request,
    file: UploadFile,
    staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> OfficeOut:
    _owner(staff)
    content = await file.read(LOGO_MAX_BYTES + 1)
    if len(content) > LOGO_MAX_BYTES:
        raise ApiError(413, ErrorCode.LOGO_TOO_LARGE)
    logo_type = _logo_type(content)
    if logo_type is None:
        raise ApiError(415, ErrorCode.LOGO_WRONG_TYPE)
    name = f"logo.{_EXTENSIONS[logo_type]}"
    connection = await db.scalar(select(StorageConnection))

    if connection is not None and connection.kind is StorageKind.FOLDER:
        if request.app.state.settings.deployed:
            raise ApiError(409, ErrorCode.DRIVE_NOT_CONNECTED)
        # Local development: the fictional dataset's folder on this machine.
        folder = Path(request.app.state.settings.local_storage_root) / connection.root_id
        (folder / BRAND_FOLDER).mkdir(parents=True, exist_ok=True)
        (folder / BRAND_FOLDER / name).write_bytes(content)
        found = await _profile_for_change(db, tenant)
        found.logo_file_id, found.logo_type = f"{BRAND_FOLDER}/{name}", logo_type
    else:
        if connection is not None and connection.reader_status is not ReaderStatus.OK:
            # Uploaded through the office's grant but shown through the reader: if
            # the reader cannot read the folder, the logo would never display.
            raise ApiError(409, ErrorCode.DRIVE_UNREADABLE)
        connection, writer = await writer_for(request, db)
        found = await _profile_for_change(db, tenant)
        try:
            if not (found.brand_folder_id and await writer.can_open(found.brand_folder_id)):
                found.brand_folder_id = await writer.create_folder(BRAND_FOLDER, connection.root_id)
            previous = found.logo_file_id
            found.logo_file_id = await writer.upload(
                name, found.brand_folder_id, content, logo_type
            )
        except ConnectError as error:
            log.error("logo upload to Drive failed for %s: %s", tenant.slug, error.detail)
            raise ApiError(503, ErrorCode.DRIVE_CONNECT_FAILED) from None
        found.logo_type = logo_type
        if previous:
            await writer.trash(previous)
    await db.commit()
    await db.refresh(found)
    return _out(tenant, found, staff)


@router.get("/office/logo", include_in_schema=False)
async def logo(request: Request, db: AsyncSession = Depends(get_tenant_session)) -> Response:
    found = await load_profile(db)
    connection = await db.scalar(select(StorageConnection))
    if found is None or found.logo_file_id is None or connection is None:
        return Response(status_code=404)
    try:
        google = getattr(request.app.state, "google", None)  # set up at app start
        storage = storage_for(connection, request.app.state.settings, google)
        item = await storage.get(found.logo_file_id)
        download = await storage.download(item)
    except StorageError as error:
        log.warning("logo unavailable: %s %s", error.problem, error.detail)
        return Response(status_code=404)

    async def body():
        try:
            async for chunk in download.chunks:
                yield chunk
        finally:
            await download.aclose()

    return StreamingResponse(body(), media_type=found.logo_type.value, headers=LOGO_HEADERS)
