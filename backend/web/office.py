"""The office's details in the painel (Configurações → Escritório).

    GET   /api/office        name, contact email, logo; anyone signed in
    PATCH /api/office        change name and contact email (owners)
    PUT   /api/office/logo      upload the logo (owners; needs the office's storage)
    PUT   /api/office/logo/png  a PNG of the SVG logo, for one uploaded before PNGs
    PUT   /api/office/logo/dark  the logo for dark mode (owners)
    DELETE /api/office/logo/dark dark mode shows the usual logo again
    GET   /api/office/logo      the logo itself, public (client pages show it);
                                ?png=true: an SVG logo's PNG (emails);
                                ?dark=true: the dark mode logo

The logo is stored in the office's own storage, in a `_marca` folder inside its
root: Google Drive (through the office's grant), or the local folder in
development. An SVG may contain scripts, so the logo is only ever served with a
policy that forbids running anything, and the painel shows it as an image.

Email programs don't show SVG images, so with an SVG logo the painel also sends a
PNG it drew in the browser (its fonts render the logo's lettering as on the
site), stored beside it as `logo.png`. The server only checks that it is a PNG.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.identity.models import Role
from backend.office.models import LogoType, OfficeProfile
from backend.office.profile import logo_urls
from backend.office.profile import profile as load_profile
from backend.storage.base import StorageError
from backend.storage.connections import storage_for
from backend.storage.google_connect import ConnectError
from backend.storage.models import ReaderStatus, StorageConnection, StorageKind
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web.auth import CurrentStaff, current_staff, require_csrf
from backend.web.drive import writer_for
from backend.web.errors import ApiError, ErrorCode, documented

# The office's name as shown at the top of its pages: 28 characters for now (Fabio,
# 18 Oct 2026). The database allows NAME_MAX (80), so this can grow without a migration.
NAME_LIMIT = 28

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
    # For dark mode; None: the logo above shows there too.
    logo_dark_url: str | None
    # An SVG logo without its PNG (uploaded before PNGs): the painel draws one.
    logo_needs_png: bool
    can_manage: bool


class OfficeIn(BaseModel):
    name: str | None = None
    contact_email: str | None = None


def _out(tenant: CurrentTenant, found: OfficeProfile | None, staff: CurrentStaff) -> OfficeOut:
    has_logo = found is not None and found.logo_file_id is not None
    logo_url, logo_dark_url = logo_urls(found)
    return OfficeOut(
        name=found.display_name if found else tenant.name,
        contact_email=found.contact_email if found else None,
        logo_url=logo_url,
        logo_dark_url=logo_dark_url,
        logo_needs_png=has_logo
        and found.logo_type is LogoType.SVG
        and found.logo_png_file_id is None,
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
        # The limit is for names entered from now on: one saved before it stays as is.
        if not name or (name != found.display_name and len(name) > NAME_LIMIT):
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


def image_type(content: bytes) -> LogoType | None:
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


async def _read(file: UploadFile) -> bytes:
    content = await file.read(LOGO_MAX_BYTES + 1)
    if len(content) > LOGO_MAX_BYTES:
        raise ApiError(413, ErrorCode.LOGO_TOO_LARGE)
    return content


def _png(content: bytes) -> bytes:
    if image_type(content) is not LogoType.PNG:
        raise ApiError(415, ErrorCode.LOGO_WRONG_TYPE)
    return content


async def _store(
    request: Request,
    db: AsyncSession,
    tenant: CurrentTenant,
    found: OfficeProfile,
    files: dict[str, tuple[bytes, LogoType]],
) -> dict[str, str]:
    """Save brand files (name: content, type) in `_marca`; their ids by name. What
    the profile pointed to before is the caller's to trash."""
    connection = await db.scalar(select(StorageConnection))
    if connection is not None and connection.kind is StorageKind.FOLDER:
        if request.app.state.settings.deployed:
            raise ApiError(409, ErrorCode.DRIVE_NOT_CONNECTED)
        # Local development: the fictional dataset's folder on this machine.
        folder = Path(request.app.state.settings.local_storage_root) / connection.root_id
        (folder / BRAND_FOLDER).mkdir(parents=True, exist_ok=True)
        for name, (content, _type) in files.items():
            (folder / BRAND_FOLDER / name).write_bytes(content)
        return {name: f"{BRAND_FOLDER}/{name}" for name in files}
    if connection is not None and connection.reader_status is not ReaderStatus.OK:
        # Uploaded through the office's grant but shown through the reader: if
        # the reader cannot read the folder, the logo would never display.
        raise ApiError(409, ErrorCode.DRIVE_UNREADABLE)
    connection, writer = await writer_for(request, db)
    ids = {}
    try:
        if not (found.brand_folder_id and await writer.can_open(found.brand_folder_id)):
            found.brand_folder_id = await writer.create_folder(BRAND_FOLDER, connection.root_id)
        for name, (content, kind) in files.items():
            ids[name] = await writer.upload(name, found.brand_folder_id, content, kind)
    except ConnectError as error:
        log.error("logo upload to Drive failed for %s: %s", tenant.slug, error.detail)
        for done in ids.values():
            await writer.trash(done)  # all or nothing
        raise ApiError(503, ErrorCode.DRIVE_CONNECT_FAILED) from None
    return ids


async def _trash(request: Request, db: AsyncSession, *ids: str | None) -> None:
    """The files a change replaced. On Drive only: locally they were overwritten."""
    connection = await db.scalar(select(StorageConnection))
    if connection is None or connection.kind is StorageKind.FOLDER or not any(ids):
        return
    _connection, writer = await writer_for(request, db)
    for item_id in ids:
        if item_id:
            await writer.trash(item_id)


@router.put("/office/logo", responses=documented(401, 403, 409, 413, 415, 503))
async def upload_logo(
    request: Request,
    file: UploadFile,
    png: UploadFile | None = None,
    staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> OfficeOut:
    """The logo; with an SVG, also `png`, the painel's drawing of it (for email)."""
    _owner(staff)
    content = await _read(file)
    logo_type = image_type(content)
    if logo_type is None:
        raise ApiError(415, ErrorCode.LOGO_WRONG_TYPE)
    files = {f"logo.{_EXTENSIONS[logo_type]}": (content, logo_type)}
    if logo_type is LogoType.SVG and png is not None:
        files["logo.png"] = (_png(await _read(png)), LogoType.PNG)
    found = await _profile_for_change(db, tenant)
    previous = (found.logo_file_id, found.logo_png_file_id)
    ids = await _store(request, db, tenant, found, files)
    found.logo_file_id, found.logo_type = ids[next(iter(files))], logo_type
    found.logo_png_file_id = ids.get("logo.png") if logo_type is LogoType.SVG else None
    # A new logo, a new address, even when its id stays the same (a local folder
    # overwrites `_marca/logo.png`): otherwise browsers keep showing the old one.
    found.updated_at = func.now()
    await db.commit()
    await _trash(request, db, *(p for p in previous if p not in ids.values()))
    await db.refresh(found)
    return _out(tenant, found, staff)


@router.put("/office/logo/dark", responses=documented(401, 403, 409, 413, 415, 503))
async def upload_dark_logo(
    request: Request,
    file: UploadFile,
    staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> OfficeOut:
    """The logo for dark mode (pages show it only with the usual one)."""
    _owner(staff)
    content = await _read(file)
    logo_type = image_type(content)
    if logo_type is None:
        raise ApiError(415, ErrorCode.LOGO_WRONG_TYPE)
    found = await _profile_for_change(db, tenant)
    previous = found.logo_dark_file_id
    name = f"logo-escuro.{_EXTENSIONS[logo_type]}"
    ids = await _store(request, db, tenant, found, {name: (content, logo_type)})
    found.logo_dark_file_id, found.logo_dark_type = ids[name], logo_type
    found.updated_at = func.now()  # a new address, as for the usual logo
    await db.commit()
    if previous and previous != found.logo_dark_file_id:
        await _trash(request, db, previous)
    await db.refresh(found)
    return _out(tenant, found, staff)


@router.delete("/office/logo/dark", responses=documented(401, 403, 503))
async def remove_dark_logo(
    request: Request,
    staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> OfficeOut:
    """Dark mode shows the usual logo again."""
    _owner(staff)
    found = await _profile_for_change(db, tenant)
    previous = found.logo_dark_file_id
    found.logo_dark_file_id = found.logo_dark_type = None
    await db.commit()
    await _trash(request, db, previous)
    await db.refresh(found)
    return _out(tenant, found, staff)


@router.put("/office/logo/png", responses=documented(401, 403, 409, 413, 415, 503))
async def add_logo_png(
    request: Request,
    file: UploadFile,
    staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> OfficeOut:
    """The PNG of an SVG logo uploaded before PNGs were drawn (the painel sends it
    when it sees `logo_needs_png`)."""
    _owner(staff)
    content = _png(await _read(file))
    found = await load_profile(db)
    if found is None or found.logo_type is not LogoType.SVG:
        raise ApiError(409, ErrorCode.LOGO_WRONG_TYPE)  # only an SVG logo has one
    previous = found.logo_png_file_id
    ids = await _store(request, db, tenant, found, {"logo.png": (content, LogoType.PNG)})
    found.logo_png_file_id = ids["logo.png"]
    await db.commit()
    if previous and previous != found.logo_png_file_id:
        await _trash(request, db, previous)
    await db.refresh(found)
    return _out(tenant, found, staff)


@router.get("/office/logo", include_in_schema=False)
async def logo(
    request: Request,
    png: bool = False,
    dark: bool = False,
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    found = await load_profile(db)
    connection = await db.scalar(select(StorageConnection))
    file_id = found and (
        found.logo_png_file_id if png else found.logo_dark_file_id if dark else found.logo_file_id
    )
    if found is None or file_id is None or connection is None:
        return Response(status_code=404)
    try:
        google = getattr(request.app.state, "google", None)  # set up at app start
        storage = storage_for(connection, request.app.state.settings, google)
        item = await storage.get(file_id)
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

    media_type = (LogoType.PNG if png else found.logo_dark_type if dark else found.logo_type).value
    return StreamingResponse(body(), media_type=media_type, headers=LOGO_HEADERS)
