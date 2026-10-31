"""The office's portfolio, edited in the painel (Portfólio), behind the
`portfolio` feature (A40). Once published, the office's own address shows it at
`/` (backend/web/portfolio_page.py) instead of Unio's home.

    GET    /api/portfolio                       the whole portfolio, for staff
    PATCH  /api/portfolio                       published, opening text
    POST   /api/portfolio/entries               add a work (from a project, or not)
    PATCH  /api/portfolio/entries/{id}          its texts, or its photos' order
    DELETE /api/portfolio/entries/{id}          remove it, photos to the Drive trash
    PUT    /api/portfolio/order                 the works' order
    POST   /api/portfolio/entries/{id}/photos   add a photo (resized in the browser)
    DELETE /api/portfolio/photos/{id}           remove a photo
    GET    /api/portfolio/photos/{id}           the photo: public once published

Every change answers with the whole portfolio, which is small. Any staff member
edits it, as they edit project pages, which clients see too.

Photos are copies in the office's storage, in a `_portfolio` folder inside its
root: chosen from a project's files, the browser downloads, resizes and uploads
them, so the portfolio never depends on a project's files staying as they are.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics import capture
from backend.db.engine import get_tenant_session
from backend.portfolio.models import (
    DESCRIPTION_MAX,
    ENTRIES_MAX,
    INTRO_MAX,
    PHOTOS_MAX,
    PLACE_MAX,
    TITLE_MAX,
    YEAR_MAX,
    YEAR_MIN,
    Portfolio,
    PortfolioEntry,
    PortfolioPhoto,
)
from backend.projects.enums import CoverType
from backend.projects.models import Project
from backend.storage.google_connect import ConnectError
from backend.storage.models import StorageKind
from backend.tenancy.models import Feature
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web.auth import CurrentStaff, current_staff, optional_staff, require_csrf
from backend.web.drive import writer_for
from backend.web.errors import ApiError, ErrorCode, documented
from backend.web.office import image_type
from backend.web.project_settings import (
    COVER_MAX_BYTES,
    local_root,
    serve_stored_image,
    storage_connection,
)

log = logging.getLogger(__name__)

FOLDER = "_portfolio"
_EXTENSIONS = {CoverType.PNG: "png", CoverType.JPEG: "jpg", CoverType.WEBP: "webp"}
# Pixels on the long side, from Drive's thumbnails: a card, and a photo on its own.
SIZES = {"card": 960, "full": 2000}
PHOTO_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "X-Content-Type-Options": "nosniff",
}
# A photo never changes under its address (a new photo is a new row).
PUBLIC_PHOTO = {**PHOTO_HEADERS, "Cache-Control": "public, max-age=86400"}
PRIVATE_PHOTO = {**PHOTO_HEADERS, "Cache-Control": "private, max-age=86400"}


def _switched_on(tenant: CurrentTenant = Depends(current_tenant)) -> None:
    if not tenant.has(Feature.PORTFOLIO):
        raise ApiError(409, ErrorCode.FEATURE_OFF)


router = APIRouter(prefix="/api", dependencies=[Depends(_switched_on)])


class PhotoOut(BaseModel):
    id: uuid.UUID
    url: str


class EntryOut(BaseModel):
    id: uuid.UUID
    title: str
    place: str
    year: int | None
    description: str
    # The project it was drawn from, if any (staff only: never on the public page).
    project_id: uuid.UUID | None
    project_name: str | None
    photos: list[PhotoOut]


class PortfolioOut(BaseModel):
    published: bool
    intro: str
    entries: list[EntryOut]


class PortfolioIn(BaseModel):
    published: bool | None = None
    intro: str | None = Field(default=None, max_length=INTRO_MAX)


class EntryIn(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    place: str = Field(default="", max_length=PLACE_MAX)
    year: int | None = Field(default=None, ge=YEAR_MIN, le=YEAR_MAX)
    description: str = Field(default="", max_length=DESCRIPTION_MAX)
    project_id: uuid.UUID | None = None


class EntryChange(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    place: str | None = Field(default=None, max_length=PLACE_MAX)
    year: int | None = Field(default=None, ge=YEAR_MIN, le=YEAR_MAX)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX)
    # Every one of its photos, in their new order.
    photos: list[uuid.UUID] | None = Field(default=None, max_length=PHOTOS_MAX)


class OrderIn(BaseModel):
    # Every work, in its new order.
    entries: list[uuid.UUID] = Field(max_length=ENTRIES_MAX)


def photo_url(photo: PortfolioPhoto) -> str:
    return f"/api/portfolio/photos/{photo.id}"


async def entries_with_photos(
    db: AsyncSession,
) -> list[tuple[PortfolioEntry, list[PortfolioPhoto]]]:
    """Every work in order, each with its photos in order."""
    entries = (await db.scalars(select(PortfolioEntry).order_by(PortfolioEntry.position))).all()
    photos = (await db.scalars(select(PortfolioPhoto).order_by(PortfolioPhoto.position))).all()
    by_entry: dict[uuid.UUID, list[PortfolioPhoto]] = {}
    for photo in photos:
        by_entry.setdefault(photo.entry_id, []).append(photo)
    return [(entry, by_entry.get(entry.id, [])) for entry in entries]


async def _out(db: AsyncSession) -> PortfolioOut:
    found = await db.scalar(select(Portfolio))
    works = await entries_with_photos(db)
    linked = {entry.project_id for entry, _ in works if entry.project_id}
    names = (
        dict(
            (await db.execute(select(Project.id, Project.name).where(Project.id.in_(linked)))).all()
        )
        if linked
        else {}
    )
    return PortfolioOut(
        published=found.published if found else False,
        intro=found.intro if found else "",
        entries=[
            EntryOut(
                id=entry.id,
                title=entry.title,
                place=entry.place,
                year=entry.year,
                description=entry.description,
                project_id=entry.project_id,
                project_name=names.get(entry.project_id),
                photos=[PhotoOut(id=photo.id, url=photo_url(photo)) for photo in photos],
            )
            for entry, photos in works
        ],
    )


async def _portfolio(db: AsyncSession) -> Portfolio:
    """This office's portfolio row, made on its first change."""
    found = await db.scalar(select(Portfolio).with_for_update())
    if found is None:
        found = Portfolio(published=False, intro="")
        db.add(found)
        await db.flush()
    return found


async def _entry(db: AsyncSession, entry_id: uuid.UUID) -> PortfolioEntry:
    entry = await db.scalar(select(PortfolioEntry).where(PortfolioEntry.id == entry_id))
    if entry is None:
        raise ApiError(404, ErrorCode.PORTFOLIO_ENTRY_NOT_FOUND)
    return entry


async def _trash(request: Request, db: AsyncSession, file_ids: list[str]) -> None:
    """Photos no longer shown: to the office's Drive trash, where they can be
    recovered (locally, deleted). Best effort: the portfolio has already let go."""
    if not file_ids:
        return
    connection = await storage_connection(request, db)
    if connection is None:
        return
    if connection.kind is StorageKind.FOLDER:
        for file_id in file_ids:
            (local_root(request, connection) / file_id).unlink(missing_ok=True)
        return
    try:
        _connection, writer = await writer_for(request, db)
        for file_id in file_ids:
            await writer.trash(file_id)
    except (ApiError, ConnectError) as error:
        log.warning("portfolio photos left in Drive: %s", getattr(error, "detail", error))


@router.get("/portfolio", responses=documented(401))
async def portfolio(
    _staff: CurrentStaff = Depends(current_staff),
    db: AsyncSession = Depends(get_tenant_session),
) -> PortfolioOut:
    return await _out(db)


@router.patch("/portfolio", responses=documented(401, 422))
async def change_portfolio(
    request: Request,
    body: PortfolioIn,
    _staff: CurrentStaff = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_session),
) -> PortfolioOut:
    found = await _portfolio(db)
    if body.intro is not None:
        found.intro = body.intro.strip()
    if body.published is not None and body.published != found.published:
        found.published = body.published
        capture(request, "portfolio_published" if body.published else "portfolio_unpublished")
    await db.commit()
    return await _out(db)


@router.post("/portfolio/entries", responses=documented(401, 404, 409, 422))
async def add_entry(
    request: Request,
    body: EntryIn,
    _staff: CurrentStaff = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_session),
) -> PortfolioOut:
    if not body.title.strip():
        raise ApiError(422, ErrorCode.INVALID_REQUEST)  # the painel never sends one
    await _portfolio(db)  # locks the office's portfolio: one addition at a time
    if body.project_id is not None and not await db.scalar(
        select(Project.id).where(Project.id == body.project_id, Project.deleted_at.is_(None))
    ):
        raise ApiError(404, ErrorCode.PROJECT_NOT_FOUND)
    count, last = (await db.execute(select(func.count(), func.max(PortfolioEntry.position)))).one()
    if count >= ENTRIES_MAX:
        raise ApiError(409, ErrorCode.PORTFOLIO_FULL)
    db.add(
        PortfolioEntry(
            position=(last or 0) + 1,
            title=body.title.strip(),
            place=body.place.strip(),
            year=body.year,
            description=body.description.strip(),
            project_id=body.project_id,
        )
    )
    await db.commit()
    capture(request, "portfolio_entry_added", {"from_project": body.project_id is not None})
    return await _out(db)


@router.patch("/portfolio/entries/{entry_id}", responses=documented(401, 404, 409, 422))
async def change_entry(
    entry_id: uuid.UUID,
    body: EntryChange,
    _staff: CurrentStaff = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_session),
) -> PortfolioOut:
    entry = await _entry(db, entry_id)
    if body.title is not None:
        if not body.title.strip():
            raise ApiError(422, ErrorCode.INVALID_REQUEST)  # the painel never sends one
        entry.title = body.title.strip()
    if body.place is not None:
        entry.place = body.place.strip()
    if "year" in body.model_fields_set:
        entry.year = body.year  # None clears it
    if body.description is not None:
        entry.description = body.description.strip()
    if body.photos is not None:
        photos = (
            await db.scalars(select(PortfolioPhoto).where(PortfolioPhoto.entry_id == entry.id))
        ).all()
        by_id = {photo.id: photo for photo in photos}
        if len(body.photos) != len(by_id) or set(body.photos) != set(by_id):
            # A photo added or removed meanwhile, elsewhere: reload and try again.
            raise ApiError(409, ErrorCode.PORTFOLIO_ENTRY_NOT_FOUND)
        for position, photo_id in enumerate(body.photos, start=1):
            by_id[photo_id].position = position
    await db.commit()
    return await _out(db)


@router.delete("/portfolio/entries/{entry_id}", responses=documented(401, 404))
async def remove_entry(
    request: Request,
    entry_id: uuid.UUID,
    _staff: CurrentStaff = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_session),
) -> PortfolioOut:
    entry = await _entry(db, entry_id)
    files = list(
        (
            await db.scalars(
                select(PortfolioPhoto.file_id).where(PortfolioPhoto.entry_id == entry.id)
            )
        ).all()
    )
    await db.delete(entry)  # its photos go with it
    await db.commit()
    await _trash(request, db, files)
    capture(request, "portfolio_entry_removed")
    return await _out(db)


@router.put("/portfolio/order", responses=documented(401, 409, 422))
async def order_entries(
    body: OrderIn,
    _staff: CurrentStaff = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_session),
) -> PortfolioOut:
    await _portfolio(db)
    entries = {entry.id: entry for entry in (await db.scalars(select(PortfolioEntry))).all()}
    if len(body.entries) != len(entries) or set(body.entries) != set(entries):
        raise ApiError(409, ErrorCode.PORTFOLIO_ENTRY_NOT_FOUND)  # changed elsewhere: reload
    for position, entry_id in enumerate(body.entries, start=1):
        entries[entry_id].position = position
    await db.commit()
    return await _out(db)


async def _store(
    request: Request,
    db: AsyncSession,
    tenant: CurrentTenant,
    found: Portfolio,
    name: str,
    content: bytes,
    kind: CoverType,
) -> str:
    """Save a photo in `_portfolio`; its id in the office's storage."""
    connection = await storage_connection(request, db)
    if connection is None:
        raise ApiError(409, ErrorCode.DRIVE_NOT_CONNECTED)
    if connection.kind is StorageKind.FOLDER:
        # Local development: the fictional dataset's folder on this machine.
        folder = local_root(request, connection) / FOLDER
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(content)
        return (Path(FOLDER) / name).as_posix()
    connection, writer = await writer_for(request, db)
    try:
        if not (found.folder_id and await writer.can_open(found.folder_id)):
            found.folder_id = await writer.create_folder(FOLDER, connection.root_id)
        return await writer.upload(name, found.folder_id, content, kind)
    except ConnectError as error:
        log.error("portfolio photo upload to Drive failed for %s: %s", tenant.slug, error.detail)
        raise ApiError(503, ErrorCode.DRIVE_CONNECT_FAILED) from None


@router.post(
    "/portfolio/entries/{entry_id}/photos", responses=documented(401, 404, 409, 413, 415, 503)
)
async def add_photo(
    request: Request,
    entry_id: uuid.UUID,
    file: UploadFile,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> PortfolioOut:
    """A photo, at the end of the work's photos (the first is its cover)."""
    content = await file.read(COVER_MAX_BYTES + 1)
    if len(content) > COVER_MAX_BYTES:
        raise ApiError(413, ErrorCode.COVER_TOO_LARGE)
    try:
        kind = CoverType(image_type(content))
    except ValueError:  # not an image, or an SVG
        raise ApiError(415, ErrorCode.COVER_WRONG_TYPE) from None
    found = await _portfolio(db)  # locked: positions are counted one upload at a time
    entry = await _entry(db, entry_id)
    count, last = (
        await db.execute(
            select(func.count(), func.max(PortfolioPhoto.position)).where(
                PortfolioPhoto.entry_id == entry.id
            )
        )
    ).one()
    if count >= PHOTOS_MAX:
        raise ApiError(409, ErrorCode.PORTFOLIO_FULL)
    photo = PortfolioPhoto(entry_id=entry.id, position=(last or 0) + 1, image_type=kind)
    photo.id = uuid.uuid4()
    photo.file_id = await _store(
        request, db, tenant, found, f"foto-{photo.id.hex[:12]}.{_EXTENSIONS[kind]}", content, kind
    )
    db.add(photo)
    await db.commit()
    capture(request, "portfolio_photo_added")
    return await _out(db)


@router.delete("/portfolio/photos/{photo_id}", responses=documented(401, 404))
async def remove_photo(
    request: Request,
    photo_id: uuid.UUID,
    _staff: CurrentStaff = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_session),
) -> PortfolioOut:
    photo = await db.scalar(select(PortfolioPhoto).where(PortfolioPhoto.id == photo_id))
    if photo is None:
        raise ApiError(404, ErrorCode.PORTFOLIO_ENTRY_NOT_FOUND)
    file_id = photo.file_id
    await db.execute(delete(PortfolioPhoto).where(PortfolioPhoto.id == photo_id))
    await db.commit()
    await _trash(request, db, [file_id])
    return await _out(db)


@router.get("/portfolio/photos/{photo_id}", include_in_schema=False)
async def photo(
    request: Request,
    photo_id: uuid.UUID,
    size: str = "full",
    staff: CurrentStaff | None = Depends(optional_staff),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """Anyone's once the portfolio is published; until then, staff's only."""
    found = await db.scalar(select(PortfolioPhoto).where(PortfolioPhoto.id == photo_id))
    published = await db.scalar(select(Portfolio.published))
    if found is None or size not in SIZES or not (published or staff):
        return Response(status_code=404)
    headers = PUBLIC_PHOTO if published else PRIVATE_PHOTO
    return await serve_stored_image(
        request, db, found.file_id, found.image_type, SIZES[size], headers
    )
