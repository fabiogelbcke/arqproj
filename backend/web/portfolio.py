"""The office's portfolio, edited in the painel (Portfólio), behind the
`portfolio` feature (A40). Once published, the office's own address shows it at
`/` (backend/web/portfolio_page.py) instead of Unio's home.

    GET    /api/portfolio                       the whole portfolio, for staff
    PATCH  /api/portfolio                       published, opening text, social links
    POST   /api/portfolio/entries               add a work (from a project, or not)
    PATCH  /api/portfolio/entries/{id}          its texts, or its photos' order
    DELETE /api/portfolio/entries/{id}          remove it, photos to the Drive trash
    PUT    /api/portfolio/order                 the works' order
    POST   /api/portfolio/entries/{id}/photos   add a photo (resized in the browser)
    DELETE /api/portfolio/photos/{id}           remove a photo
    GET    /api/portfolio/photos/{id}           the photo: public once published
    POST   /api/portfolio/entries/{id}/videos/uploads   open a video's upload
    POST   /api/portfolio/entries/{id}/videos   the video, once sent, with its poster
    DELETE /api/portfolio/videos/{id}           remove a video
    GET    /api/portfolio/videos/{id}           the video (in parts): public once published
    GET    /api/portfolio/videos/{id}/poster    the frame shown before it plays

Every change answers with the whole portfolio, which is small. Any staff member
edits it, as they edit project pages, which clients see too.

Photos are copies in the office's storage, in a `_portfolio` folder inside its
root: chosen from a project's files, the browser downloads, resizes and uploads
them, so the portfolio never depends on a project's files staying as they are.
Videos are too large to pass through the app: the browser sends each straight to
the office's storage, as clients' uploads go (A31), then registers it here with a
frame it took from it, the poster.
"""

from __future__ import annotations

import logging
import re
import uuid
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics import capture
from backend.db.engine import get_tenant_session
from backend.documents.comparisons import LABEL_MAX as COMPARISON_LABEL_MAX
from backend.documents.comparisons import clean_label
from backend.identity.models import User
from backend.portfolio.links import profile
from backend.portfolio.models import (
    CREDITS_MAX,
    DESCRIPTION_MAX,
    DETAIL_VALUE_MAX,
    DETAILS_MAX,
    ENTRIES_MAX,
    INTRO_MAX,
    LABEL_MAX,
    LINK_MAX,
    PHOTOS_MAX,
    PLACE_MAX,
    TITLE_MAX,
    VIDEO_MAX_BYTES,
    VIDEOS_MAX,
    YEAR_MAX,
    YEAR_MIN,
    Portfolio,
    PortfolioDetail,
    PortfolioEntry,
    PortfolioFormat,
    PortfolioPhoto,
    PortfolioVideo,
    SocialNetwork,
    VideoType,
    WorkStatus,
)
from backend.projects.enums import CoverType, DetailKey, DetailType, ProjectStatus
from backend.projects.models import (
    DetailTypeDef,
    Project,
    ProjectDetail,
    ProjectMember,
    ProjectStage,
    ProjectTypeDef,
)
from backend.storage.base import StorageError, StorageProblem
from backend.storage.connections import storage_for
from backend.storage.google_connect import ConnectError
from backend.storage.models import StorageConnection, StorageKind
from backend.tenancy.models import Feature, Locale
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web.auth import CurrentStaff, current_staff, optional_staff, require_csrf
from backend.web.covers import COVER_MAX_BYTES, local_root, storage_connection
from backend.web.drive import writer_for
from backend.web.errors import ApiError, ErrorCode, documented
from backend.web.office import image_type
from backend.web.page_edit import DetailTypeOut, detail_value
from backend.web.page_files import RangeNotSatisfiable, byte_range, etag
from backend.web.page_uploads import UploadFailedIn, local_upload_url, upload_origin
from backend.web.project_settings import serve_stored_image

log = logging.getLogger(__name__)

FOLDER = "_portfolio"
_EXTENSIONS = {CoverType.PNG: "png", CoverType.JPEG: "jpg", CoverType.WEBP: "webp"}
# Pixels on the long side, from Drive's thumbnails: a card, and a photo on its own.
SIZES = {"card": 960, "full": 2000}
PHOTO_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "X-Content-Type-Options": "nosniff",
}
# A photo never changes under its address (a new photo is a new row), but it can
# be removed or the portfolio unpublished: kept for minutes, not a day.
PUBLIC_PHOTO = {**PHOTO_HEADERS, "Cache-Control": "public, max-age=300"}
PRIVATE_PHOTO = {**PHOTO_HEADERS, "Cache-Control": "private, max-age=86400"}


def _switched_on(tenant: CurrentTenant = Depends(current_tenant)) -> None:
    if not tenant.has(Feature.PORTFOLIO):
        raise ApiError(409, ErrorCode.FEATURE_OFF)


router = APIRouter(prefix="/api", dependencies=[Depends(_switched_on)])


class PhotoComparisonOut(BaseModel):
    """A "before" photo's comparison (A46): its "after" photo, and the slider's
    words for each side (None: the page's own, "Antes" and "Depois")."""

    after: uuid.UUID
    before_label: str | None
    after_label: str | None


class PhotoOut(BaseModel):
    id: uuid.UUID
    url: str
    comparison: PhotoComparisonOut | None = None


class VideoOut(BaseModel):
    id: uuid.UUID
    url: str
    poster_url: str


class VideoUploadIn(BaseModel):
    size: int = Field(gt=0)
    mime_type: str = Field(max_length=100)


class VideoUploadOut(BaseModel):
    upload_url: str  # where the browser sends the file, as for clients' uploads
    name: str  # the file's name in storage: sent back once it's there


class SheetLineOut(BaseModel):
    """A line of the work's sheet: one of the built-in details (its `key`, with
    its label in the office's language) or one with the office's own label."""

    key: str | None
    label: str
    type: DetailType
    value: str  # as typed: text, a number of m² ("212.5"), or an ISO date


class EntryOut(BaseModel):
    id: uuid.UUID
    title: str
    place: str
    year: int | None
    description: str
    project_type: str | None
    status: WorkStatus | None
    details: list[SheetLineOut]
    credits: str
    videos: list[VideoOut]
    # The project it was drawn from, if any (staff only: never on the public page).
    project_id: uuid.UUID | None
    project_name: str | None
    photos: list[PhotoOut]


class PortfolioOut(BaseModel):
    published: bool
    format: PortfolioFormat
    intro: str
    links: dict[SocialNetwork, str]
    entries: list[EntryOut]


class PortfolioIn(BaseModel):
    published: bool | None = None
    format: PortfolioFormat | None = None
    intro: str | None = Field(default=None, max_length=INTRO_MAX)
    # Every profile, replacing those kept: "@name" or an address on the network.
    links: dict[SocialNetwork, str] | None = None


class EntryIn(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    place: str = Field(default="", max_length=PLACE_MAX)
    year: int | None = Field(default=None, ge=YEAR_MIN, le=YEAR_MAX)
    description: str = Field(default="", max_length=DESCRIPTION_MAX)
    # None: the project's own type, for a work drawn from one.
    project_type: str | None = Field(default=None, max_length=100)
    project_id: uuid.UUID | None = None


class SheetLineIn(BaseModel):
    key: str | None = Field(default=None, max_length=100)  # a built-in detail's
    label: str | None = Field(default=None, max_length=LABEL_MAX)  # or the office's own
    value: str = Field(max_length=500)  # as typed: text (≤ 200), a number of m², or a date


class EntryChange(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    place: str | None = Field(default=None, max_length=PLACE_MAX)
    year: int | None = Field(default=None, ge=YEAR_MIN, le=YEAR_MAX)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX)
    project_type: str | None = Field(default=None, max_length=100)
    status: WorkStatus | None = None
    # The whole sheet, in order; a line left out is removed.
    details: list[SheetLineIn] | None = Field(default=None, max_length=DETAILS_MAX)
    credits: str | None = Field(default=None, max_length=CREDITS_MAX)
    # Every one of its videos, in their new order.
    videos: list[uuid.UUID] | None = Field(default=None, max_length=VIDEOS_MAX)
    # Every one of its photos, in their new order.
    photos: list[uuid.UUID] | None = Field(default=None, max_length=PHOTOS_MAX)


class OrderIn(BaseModel):
    # Every work, in its new order.
    entries: list[uuid.UUID] = Field(max_length=ENTRIES_MAX)


def links(found: Portfolio | None) -> dict[str, str]:
    """The office's profiles in the footer's order (the database keeps none)."""
    kept = found.links if found else {}
    return {network.value: kept[network] for network in SocialNetwork if network in kept}


def photo_url(photo: PortfolioPhoto) -> str:
    return f"/api/portfolio/photos/{photo.id}"


def video_url(video: PortfolioVideo) -> str:
    return f"/api/portfolio/videos/{video.id}"


async def videos_by_entry(db: AsyncSession) -> dict[uuid.UUID, list[PortfolioVideo]]:
    """Every work's videos, in order."""
    found: dict[uuid.UUID, list[PortfolioVideo]] = {}
    for video in (await db.scalars(select(PortfolioVideo).order_by(PortfolioVideo.position))).all():
        found.setdefault(video.entry_id, []).append(video)
    return found


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


def _typed(detail: PortfolioDetail) -> str:
    """The value as the editor shows it: text, "212.5", or "2026-03-02"."""
    if detail.value_type is DetailType.AREA and detail.value_number is not None:
        return format(detail.value_number.normalize(), "f")
    if detail.value_type is DetailType.DATE and detail.value_date is not None:
        return detail.value_date.isoformat()
    return detail.value_text or ""


async def details_by_entry(db: AsyncSession, locale: Locale) -> dict[uuid.UUID, list[SheetLineOut]]:
    """Every work's sheet, its lines in order, labelled in the office's language."""
    rows = await db.execute(
        select(PortfolioDetail, DetailTypeDef.labels)
        .outerjoin(DetailTypeDef, DetailTypeDef.key == PortfolioDetail.key)
        .order_by(PortfolioDetail.position)
    )
    found: dict[uuid.UUID, list[SheetLineOut]] = {}
    for detail, labels in rows.all():
        label = detail.label if labels is None else _label(labels, locale)
        found.setdefault(detail.entry_id, []).append(
            SheetLineOut(
                key=detail.key, label=label or "", type=detail.value_type, value=_typed(detail)
            )
        )
    return found


def _label(labels: dict[str, str], locale: Locale) -> str:
    return labels.get(locale.value) or labels[Locale.PT_BR.value]


async def _out(db: AsyncSession, locale: Locale) -> PortfolioOut:
    found = await db.scalar(select(Portfolio))
    works = await entries_with_photos(db)
    videos = await videos_by_entry(db)
    details = await details_by_entry(db, locale)
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
        format=found.format if found else PortfolioFormat.GALLERY,
        intro=found.intro if found else "",
        links=links(found),
        entries=[
            EntryOut(
                id=entry.id,
                title=entry.title,
                place=entry.place,
                year=entry.year,
                description=entry.description,
                project_type=entry.project_type,
                status=entry.status,
                details=details.get(entry.id, []),
                credits=entry.credits,
                videos=[
                    VideoOut(
                        id=video.id,
                        url=video_url(video),
                        poster_url=f"{video_url(video)}/poster",
                    )
                    for video in videos.get(entry.id, [])
                ],
                project_id=entry.project_id,
                project_name=names.get(entry.project_id),
                photos=[_photo_out(photo) for photo in photos],
            )
            for entry, photos in works
        ],
    )


def _photo_out(photo: PortfolioPhoto) -> PhotoOut:
    comparison = (
        PhotoComparisonOut(
            after=photo.compare_photo_id,
            before_label=photo.before_label,
            after_label=photo.after_label,
        )
        if photo.compare_photo_id
        else None
    )
    return PhotoOut(id=photo.id, url=photo_url(photo), comparison=comparison)


def compared(photos: list[PortfolioPhoto]) -> tuple[list[PortfolioPhoto], dict]:
    """A work's photos as its page shows them (A46): each "after" photo left out,
    shown with its "before" one; with each "before" photo's id, its "after"."""
    by_id = {photo.id: photo for photo in photos}
    pairs = {
        photo.id: by_id[photo.compare_photo_id]
        for photo in photos
        if photo.compare_photo_id in by_id
    }
    afters = {after.id for after in pairs.values()}
    return [photo for photo in photos if photo.id not in afters], pairs


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


async def _known_type(db: AsyncSession, key: str | None) -> str | None:
    if key is not None and not await db.scalar(
        select(ProjectTypeDef.key).where(ProjectTypeDef.key == key)
    ):
        raise ApiError(422, ErrorCode.INVALID_REQUEST)  # the painel offers only known ones
    return key


def _profiles(given: dict[SocialNetwork, str]) -> dict[str, str]:
    kept = {}
    for network in SocialNetwork:  # in the footer's order
        value = given.get(network, "").strip()
        if not value:
            continue
        address = profile(network, value) if len(value) <= LINK_MAX else None
        if address is None:
            raise ApiError(422, ErrorCode.PORTFOLIO_LINK_INVALID)
        kept[network.value] = address
    return kept


async def _project_facts(
    db: AsyncSession, project: Project, members: bool
) -> tuple[dict, list[PortfolioDetail]]:
    """What a work drawn from `project` starts with, besides its name and type:
    its status and year, and its sheet: the project's details in their order,
    never its client nor its address, which the office may not want public
    (staff add the place themselves). "Responsável" is the
    project's members where the office has them (A41), as the client page shows
    it; a "Responsável" typed before the office had members is stale and left out."""
    rows = (
        await db.scalars(
            select(ProjectDetail)
            .where(ProjectDetail.project_id == project.id)
            .order_by(ProjectDetail.position)
        )
    ).all()
    details = {detail.key: detail for detail in rows}
    status = {
        ProjectStatus.COMPLETED: WorkStatus.COMPLETED,
        ProjectStatus.ACTIVE: WorkStatus.IN_PROGRESS,
    }.get(project.archived_from or project.status)
    if status is WorkStatus.COMPLETED:
        finished = await db.scalar(
            select(func.max(ProjectStage.completed_at)).where(ProjectStage.project_id == project.id)
        )
        year = finished.year if finished else None
    else:
        delivery = details.get(DetailKey.EXPECTED_DELIVERY)
        year = delivery.value_date.year if delivery and delivery.value_date else None
    sheet = [
        PortfolioDetail(
            key=detail.key,
            value_type=detail.value_type,
            value_text=detail.value_text,
            value_number=detail.value_number,
            value_date=detail.value_date,
        )
        for detail in rows
        if detail.key not in (DetailKey.CLIENT, DetailKey.LOCATION)
        and (detail.key != DetailKey.RESPONSIBLE or not members)
    ]
    if members:
        names = await db.scalars(
            select(User.name)
            .join(ProjectMember, ProjectMember.user_id == User.id)
            .where(ProjectMember.project_id == project.id)
            .order_by(func.lower(User.name), User.id)
        )
        team = ", ".join(names)
        if team:
            sheet.append(
                PortfolioDetail(
                    key=DetailKey.RESPONSIBLE,
                    value_type=DetailType.TEXT,
                    value_text=team[:DETAIL_VALUE_MAX],
                )
            )
    for position, detail in enumerate(sheet, start=1):
        detail.position = position
    facts = {"status": status, "year": year if year and YEAR_MIN <= year <= YEAR_MAX else None}
    return facts, sheet


@router.get("/portfolio/detail-types", responses=documented(401, 409))
async def detail_types(
    _staff: CurrentStaff = Depends(current_staff),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> list[DetailTypeOut]:
    """The built-in details a line of a work's sheet may be: every one but the
    client. "Responsável" too, whether or not the office names a project's members
    (A41): a work's sheet is written by hand, with no members to name instead."""
    rows = await db.scalars(
        select(DetailTypeDef)
        .where(DetailTypeDef.key != DetailKey.CLIENT)
        .order_by(DetailTypeDef.position)
    )
    return [
        DetailTypeOut(key=row.key, label=_label(row.labels, tenant.locale), type=row.value_type)
        for row in rows
    ]


async def _sheet(db: AsyncSession, wanted: list[SheetLineIn]) -> list[PortfolioDetail]:
    """The work's sheet as sent: each line a built-in detail (one of each, never
    the client) with a value of its type, or the office's own label with a text."""
    known = dict(
        (
            await db.execute(
                select(DetailTypeDef.key, DetailTypeDef.value_type).where(
                    DetailTypeDef.key != DetailKey.CLIENT
                )
            )
        ).all()
    )
    keys = [line.key for line in wanted if line.key]
    if len(set(keys)) != len(keys):
        raise ApiError(422, ErrorCode.INVALID_DETAIL)
    sheet = []
    for position, line in enumerate(wanted, start=1):
        if line.key:
            if line.key not in known or line.label:
                raise ApiError(422, ErrorCode.INVALID_DETAIL)
            kind, label = known[line.key], None
        else:
            label = (line.label or "").strip()
            if not label:
                raise ApiError(422, ErrorCode.INVALID_DETAIL)
            kind = DetailType.TEXT
        sheet.append(
            PortfolioDetail(
                position=position,
                key=line.key,
                label=label,
                value_type=kind,
                **detail_value(kind, line.value, text_max=DETAIL_VALUE_MAX),
            )
        )
    return sheet


async def _trash(request: Request, db: AsyncSession, file_ids: list[str]) -> None:
    """Photos no longer shown: to the office's Drive trash, where they can be
    recovered (locally, deleted). Best effort: the portfolio has already let go."""
    if not file_ids:
        return
    try:
        connection = await storage_connection(request, db)
        if connection is None:
            return
        if connection.kind is StorageKind.FOLDER:
            for file_id in file_ids:
                (local_root(request, connection) / file_id).unlink(missing_ok=True)
            return
        _connection, writer = await writer_for(request, db)
        for file_id in file_ids:
            await writer.trash(file_id)
    except (ApiError, ConnectError) as error:
        log.warning("portfolio photos left in Drive: %s", getattr(error, "detail", error))


@router.get("/portfolio", responses=documented(401))
async def portfolio(
    _staff: CurrentStaff = Depends(current_staff),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> PortfolioOut:
    return await _out(db, tenant.locale)


@router.patch("/portfolio", responses=documented(401, 422))
async def change_portfolio(
    request: Request,
    body: PortfolioIn,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> PortfolioOut:
    found = await _portfolio(db)
    if body.intro is not None:
        found.intro = body.intro.strip()
    if body.links is not None:
        found.links = _profiles(body.links)
    if body.format is not None and body.format is not found.format:
        found.format = body.format
        capture(request, "portfolio_format_changed", {"format": body.format.value})
    if body.published is not None and body.published != found.published:
        found.published = body.published
        capture(request, "portfolio_published" if body.published else "portfolio_unpublished")
    await db.commit()
    return await _out(db, tenant.locale)


@router.post("/portfolio/entries", responses=documented(401, 404, 409, 422))
async def add_entry(
    request: Request,
    body: EntryIn,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> PortfolioOut:
    if not body.title.strip():
        raise ApiError(422, ErrorCode.INVALID_REQUEST)  # the painel never sends one
    await _portfolio(db)  # locks the office's portfolio: one addition at a time
    kind = await _known_type(db, body.project_type)
    facts: dict = {"year": body.year}
    sheet: list[PortfolioDetail] = []
    if body.project_id is not None:
        project = await db.scalar(
            select(Project).where(Project.id == body.project_id, Project.deleted_at.is_(None))
        )
        if project is None:
            raise ApiError(404, ErrorCode.PROJECT_NOT_FOUND)
        kind = kind or project.project_type
        facts, sheet = await _project_facts(db, project, tenant.has(Feature.PROJECT_MEMBERS))
        facts["year"] = body.year or facts["year"]
    count, last = (await db.execute(select(func.count(), func.max(PortfolioEntry.position)))).one()
    if count >= ENTRIES_MAX:
        raise ApiError(409, ErrorCode.PORTFOLIO_FULL)
    entry = PortfolioEntry(
        position=(last or 0) + 1,
        title=body.title.strip(),
        place=body.place.strip(),
        description=body.description.strip(),
        project_type=kind,
        project_id=body.project_id,
        credits="",
        **facts,
    )
    db.add(entry)
    await db.flush()
    for detail in sheet:
        detail.entry_id = entry.id
        db.add(detail)
    await db.commit()
    capture(request, "portfolio_entry_added", {"from_project": body.project_id is not None})
    return await _out(db, tenant.locale)


@router.patch("/portfolio/entries/{entry_id}", responses=documented(401, 404, 409, 422))
async def change_entry(
    entry_id: uuid.UUID,
    body: EntryChange,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
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
    if "project_type" in body.model_fields_set:
        entry.project_type = await _known_type(db, body.project_type)  # None clears it
    if "status" in body.model_fields_set:
        entry.status = body.status  # None clears it
    if body.details is not None:
        sheet = await _sheet(db, body.details)
        await db.execute(delete(PortfolioDetail).where(PortfolioDetail.entry_id == entry.id))
        for detail in sheet:
            detail.entry_id = entry.id
            db.add(detail)
    if body.credits is not None:
        entry.credits = body.credits.strip()
    for wanted, model in ((body.photos, PortfolioPhoto), (body.videos, PortfolioVideo)):
        if wanted is None:
            continue
        items = (await db.scalars(select(model).where(model.entry_id == entry.id))).all()
        by_id = {item.id: item for item in items}
        if len(wanted) != len(by_id) or set(wanted) != set(by_id):
            # One added or removed meanwhile, elsewhere: reload and try again.
            raise ApiError(409, ErrorCode.PORTFOLIO_ENTRY_NOT_FOUND)
        for position, item_id in enumerate(wanted, start=1):
            by_id[item_id].position = position
    await db.commit()
    return await _out(db, tenant.locale)


@router.delete("/portfolio/entries/{entry_id}", responses=documented(401, 404))
async def remove_entry(
    request: Request,
    entry_id: uuid.UUID,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
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
    for video in (
        await db.scalars(select(PortfolioVideo).where(PortfolioVideo.entry_id == entry.id))
    ).all():
        files += [video.file_id, video.poster_file_id]
    await db.delete(entry)  # its photos and videos go with it
    await db.commit()
    await _trash(request, db, files)
    capture(request, "portfolio_entry_removed")
    return await _out(db, tenant.locale)


@router.put("/portfolio/order", responses=documented(401, 409, 422))
async def order_entries(
    body: OrderIn,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> PortfolioOut:
    await _portfolio(db)
    entries = {entry.id: entry for entry in (await db.scalars(select(PortfolioEntry))).all()}
    if len(body.entries) != len(entries) or set(body.entries) != set(entries):
        raise ApiError(409, ErrorCode.PORTFOLIO_ENTRY_NOT_FOUND)  # changed elsewhere: reload
    for position, entry_id in enumerate(body.entries, start=1):
        entries[entry_id].position = position
    await db.commit()
    return await _out(db, tenant.locale)


def _image_size(content: bytes) -> tuple[int, int] | tuple[None, None]:
    """The image's pixels, from its header, so the page lays it out at its shape
    before it loads; (None, None) for a file PIL can't read, which is stored
    anyway (the browser may still show it)."""
    try:
        with Image.open(BytesIO(content)) as image:
            return image.size
    except (OSError, ValueError, Image.DecompressionBombError):
        return None, None


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
    photo.width, photo.height = _image_size(content)
    photo.id = uuid.uuid4()
    photo.file_id = await _store(
        request, db, tenant, found, f"foto-{photo.id.hex[:12]}.{_EXTENSIONS[kind]}", content, kind
    )
    db.add(photo)
    await db.commit()
    capture(request, "portfolio_photo_added")
    return await _out(db, tenant.locale)


@router.delete("/portfolio/photos/{photo_id}", responses=documented(401, 404))
async def remove_photo(
    request: Request,
    photo_id: uuid.UUID,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> PortfolioOut:
    photo = await db.scalar(select(PortfolioPhoto).where(PortfolioPhoto.id == photo_id))
    if photo is None:
        raise ApiError(404, ErrorCode.PORTFOLIO_ENTRY_NOT_FOUND)
    file_id = photo.file_id
    await db.execute(delete(PortfolioPhoto).where(PortfolioPhoto.id == photo_id))
    await db.commit()
    await _trash(request, db, [file_id])
    return await _out(db, tenant.locale)


class PhotoComparisonIn(BaseModel):
    # The work's photo to compare this one with, as its "after"; None: no comparison.
    after: uuid.UUID | None
    before_label: str | None = Field(default=None, max_length=COMPARISON_LABEL_MAX)
    after_label: str | None = Field(default=None, max_length=COMPARISON_LABEL_MAX)


@router.put("/portfolio/photos/{photo_id}/comparison", responses=documented(401, 404, 409))
async def compare_photo(
    request: Request,
    photo_id: uuid.UUID,
    body: PhotoComparisonIn,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> PortfolioOut:
    """ "Antes e depois": this photo, the "before", with another of the work's
    photos, the "after", on one slider (A46). Each photo is in one comparison at
    most, as one side; asking again with another photo or labels changes it."""
    await _portfolio(db)  # locked: two staff pairing the same photos wait in turn
    photo = await db.scalar(select(PortfolioPhoto).where(PortfolioPhoto.id == photo_id))
    if photo is None:
        raise ApiError(404, ErrorCode.PORTFOLIO_ENTRY_NOT_FOUND)
    if body.after is not None:
        same_work = select(PortfolioPhoto).where(PortfolioPhoto.entry_id == photo.entry_id)
        photos = (await db.scalars(same_work)).all()
        after = next((other for other in photos if other.id == body.after), None)
        if after is None or after.id == photo.id:
            raise ApiError(404, ErrorCode.PORTFOLIO_ENTRY_NOT_FOUND)  # another work's, or gone
        busy = {other.compare_photo_id for other in photos if other.id != photo.id}
        if (
            photo.id in busy  # this one is already another photo's "after"
            or after.id in busy  # that one is already another photo's "after"
            or after.compare_photo_id is not None  # that one is a "before" already
        ):
            raise ApiError(409, ErrorCode.PORTFOLIO_PHOTO_COMPARED)
    photo.compare_photo_id = body.after
    photo.before_label = clean_label(body.before_label) if body.after else None
    photo.after_label = clean_label(body.after_label) if body.after else None
    await db.commit()
    capture(request, "portfolio_comparison_set" if body.after else "portfolio_comparison_removed")
    return await _out(db, tenant.locale)


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


_VIDEO_NAME = re.compile(r"video-[0-9a-f]{32}\.(mp4|webm)")
_VIDEO_EXTENSIONS = {VideoType.MP4: "mp4", VideoType.WEBM: "webm"}


async def _room_for_video(db: AsyncSession, entry: PortfolioEntry) -> int:
    count, last = (
        await db.execute(
            select(func.count(), func.max(PortfolioVideo.position)).where(
                PortfolioVideo.entry_id == entry.id
            )
        )
    ).one()
    if count >= VIDEOS_MAX:
        raise ApiError(409, ErrorCode.PORTFOLIO_FULL)
    return (last or 0) + 1


@router.post(
    "/portfolio/entries/{entry_id}/videos/uploads/failed",
    status_code=502,
    responses=documented(401, 502),
)
async def video_upload_failed(
    request: Request,
    entry_id: uuid.UUID,
    body: UploadFailedIn,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
) -> Response:
    """The video's bytes go from the browser to the storage, past the app; when
    sending fails for good, the browser reports it here (as a stage's upload does),
    so it is logged with the office and the work, and staff get the support code."""
    log.error(
        "portfolio videos: sending failed for %s, work %s: %r (%s bytes), status %s: %s",
        tenant.id,
        entry_id,
        body.name,
        body.size,
        body.status,
        body.detail,
    )
    capture(request, "portfolio_video_upload_failed", {"bytes": body.size})
    raise ApiError(502, ErrorCode.UPLOAD_FAILED)


@router.post(
    "/portfolio/entries/{entry_id}/videos/uploads",
    responses=documented(401, 404, 409, 413, 415, 503),
)
async def start_video_upload(
    request: Request,
    entry_id: uuid.UUID,
    body: VideoUploadIn,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> VideoUploadOut:
    """Where the browser sends a video: an upload session in the office's Drive
    (locally, the app's stand-in), under a name of our choosing."""
    try:
        kind = VideoType(body.mime_type)
    except ValueError:
        raise ApiError(415, ErrorCode.PORTFOLIO_VIDEO_REFUSED) from None
    if body.size > VIDEO_MAX_BYTES:
        raise ApiError(413, ErrorCode.PORTFOLIO_VIDEO_REFUSED)
    found = await _portfolio(db)
    await _room_for_video(db, await _entry(db, entry_id))
    name = f"video-{uuid.uuid4().hex}.{_VIDEO_EXTENSIONS[kind]}"
    connection = await storage_connection(request, db)
    if connection is None:
        raise ApiError(409, ErrorCode.DRIVE_NOT_CONNECTED)
    if connection.kind is StorageKind.FOLDER:
        (local_root(request, connection) / FOLDER).mkdir(parents=True, exist_ok=True)
        url = local_upload_url(request, tenant, FOLDER, name, body.size)
    else:
        connection, writer = await writer_for(request, db)
        try:
            if not (found.folder_id and await writer.can_open(found.folder_id)):
                found.folder_id = await writer.create_folder(FOLDER, connection.root_id)
            url = await writer.start_upload(
                name, found.folder_id, body.size, kind.value, upload_origin(request, tenant)
            )
        except ConnectError as error:
            log.error(
                "portfolio video upload to Drive failed for %s: %s", tenant.slug, error.detail
            )
            raise ApiError(503, ErrorCode.DRIVE_CONNECT_FAILED) from None
    await db.commit()  # the folder, if it was just made
    return VideoUploadOut(upload_url=url, name=name)


@router.post(
    "/portfolio/entries/{entry_id}/videos", responses=documented(401, 404, 409, 413, 415, 503)
)
async def add_video(
    request: Request,
    entry_id: uuid.UUID,
    poster: UploadFile,
    name: str = Form(max_length=60),
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> PortfolioOut:
    """A video the browser has sent to the office's storage, by the name it was
    given, with a frame of it. Only a file of that name in the portfolio's folder
    is taken: never another of the office's files, which this would make public."""
    content = await poster.read(COVER_MAX_BYTES + 1)
    if len(content) > COVER_MAX_BYTES:
        raise ApiError(413, ErrorCode.COVER_TOO_LARGE)
    try:
        poster_type = CoverType(image_type(content))
    except ValueError:
        raise ApiError(415, ErrorCode.COVER_WRONG_TYPE) from None
    if not _VIDEO_NAME.fullmatch(name):
        raise ApiError(422, ErrorCode.INVALID_REQUEST)  # the painel sends back what it was given
    found = await _portfolio(db)  # locked: positions are counted one at a time
    entry = await _entry(db, entry_id)
    position = await _room_for_video(db, entry)
    connection = await db.scalar(select(StorageConnection))
    folder = FOLDER if connection and connection.kind is StorageKind.FOLDER else found.folder_id
    if connection is None or folder is None:
        raise ApiError(409, ErrorCode.UPLOAD_FAILED)
    try:
        storage = storage_for(
            connection, request.app.state.settings, getattr(request.app.state, "google", None)
        )
        sent = next((item for item in await storage.list_folder(folder) if item.name == name), None)
    except StorageError as error:
        if error.problem is not StorageProblem.NOT_FOUND:  # no folder: nothing ever arrived
            log.error(
                "portfolio video unlisted for %s: %s %s", tenant.slug, error.problem, error.detail
            )
            raise ApiError(503, ErrorCode.FILES_UNAVAILABLE) from None
        sent = None
    if sent is None:
        log.error("portfolio video %s never arrived for %s", name, tenant.slug)
        raise ApiError(409, ErrorCode.UPLOAD_FAILED)
    try:
        kind = VideoType(sent.mime_type)
    except ValueError:
        kind = None
    if kind is None or not sent.size or sent.size > VIDEO_MAX_BYTES:
        raise ApiError(415, ErrorCode.PORTFOLIO_VIDEO_REFUSED)
    video = PortfolioVideo(
        entry_id=entry.id,
        position=position,
        file_id=sent.id,
        video_type=kind,
    )
    video.id = uuid.uuid4()
    video.poster_type = poster_type
    video.width, video.height = _image_size(content)  # the poster's: the video's shape
    video.poster_file_id = await _store(
        request,
        db,
        tenant,
        found,
        f"{name.rsplit('.', 1)[0]}-capa.{_EXTENSIONS[poster_type]}",
        content,
        poster_type,
    )
    db.add(video)
    await db.commit()
    capture(request, "portfolio_video_added", {"bytes": sent.size})
    return await _out(db, tenant.locale)


@router.delete("/portfolio/videos/{video_id}", responses=documented(401, 404))
async def remove_video(
    request: Request,
    video_id: uuid.UUID,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> PortfolioOut:
    video = await db.scalar(select(PortfolioVideo).where(PortfolioVideo.id == video_id))
    if video is None:
        raise ApiError(404, ErrorCode.PORTFOLIO_ENTRY_NOT_FOUND)
    files = [video.file_id, video.poster_file_id]
    await db.execute(delete(PortfolioVideo).where(PortfolioVideo.id == video_id))
    await db.commit()
    await _trash(request, db, files)
    return await _out(db, tenant.locale)


async def _shown_video(
    db: AsyncSession, video_id: uuid.UUID, staff: CurrentStaff | None
) -> tuple[PortfolioVideo | None, dict[str, str]]:
    """The video, if this viewer may see it (anyone once published, else staff),
    with the headers its answer carries."""
    found = await db.scalar(select(PortfolioVideo).where(PortfolioVideo.id == video_id))
    published = await db.scalar(select(Portfolio.published))
    if found is None or not (published or staff):
        return None, {}
    return found, PUBLIC_PHOTO if published else PRIVATE_PHOTO


@router.get("/portfolio/videos/{video_id}/poster", include_in_schema=False)
async def video_poster(
    request: Request,
    video_id: uuid.UUID,
    size: str = "full",
    staff: CurrentStaff | None = Depends(optional_staff),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    found, headers = await _shown_video(db, video_id, staff)
    if found is None or size not in SIZES:
        return Response(status_code=404)
    return await serve_stored_image(
        request, db, found.poster_file_id, found.poster_type, SIZES[size], headers
    )


@router.get("/portfolio/videos/{video_id}", include_in_schema=False)
async def video(
    request: Request,
    video_id: uuid.UUID,
    staff: CurrentStaff | None = Depends(optional_staff),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """The video's bytes as they come from storage, in the parts the browser asks
    for (Range): it plays from any point without loading the whole file."""
    found, headers = await _shown_video(db, video_id, staff)
    connection = await db.scalar(select(StorageConnection))
    if found is None or connection is None:
        return Response(status_code=404)
    try:
        storage = storage_for(
            connection, request.app.state.settings, getattr(request.app.state, "google", None)
        )
        item = await storage.get(found.file_id)
        try:
            part = byte_range(request, item)
        except RangeNotSatisfiable:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{item.size}"})
        download = await storage.download(item, part)
    except StorageError as error:
        log.warning("portfolio video unavailable: %s %s", error.problem, error.detail)
        return Response(status_code=404)
    headers = {**headers, "Accept-Ranges": "bytes", "ETag": etag(item)}
    if download.size is not None:
        headers["Content-Length"] = str(download.size)
    if part is not None:
        headers["Content-Range"] = f"bytes {part[0]}-{part[1]}/{item.size}"

    async def body():
        try:
            async for chunk in download.chunks:
                yield chunk
        except StorageError as error:  # storage gave up partway: the player sees a cut
            log.warning("portfolio video broke off: %s %s", error.problem, error.detail)
        finally:
            await download.aclose()

    await db.close()  # before streaming: never hold a database connection meanwhile
    return StreamingResponse(
        body(),
        status_code=206 if part is not None else 200,
        media_type=found.video_type.value,
        headers=headers,
    )
