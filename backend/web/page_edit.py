"""Editing a project's content from its page (edit mode, part 1; A24).

    GET    /api/detail-types                        the built-in details to add
    PATCH  /api/projects/{id}/content               description, details, project type
    PUT    /api/projects/{id}/meeting               set the next meeting
    DELETE /api/projects/{id}/meeting?row_version=  clear it
    PUT    /api/projects/{id}/stages/{n}/notes      a stage's note to the client

Anyone signed in may edit. Every change carries the `row_version` the page
loaded and bumps it, so a change saved meanwhile by someone else is refused
with `project_changed` instead of overwritten (plan section 7). "Atualizado"
(`last_activity_at`) moves for the meeting and stage notes only (Fabio, 16 Oct
2026: what the client notices; until the updates feed of A28 exists).
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.notifications.events import record
from backend.notifications.models import EventKind
from backend.projects.enums import DetailType, ProjectStatus
from backend.projects.models import (
    MEETING_LOCATION_MAX,
    MEETING_TITLE_MAX,
    DetailTypeDef,
    Meeting,
    Project,
    ProjectDetail,
    ProjectStage,
    ProjectTypeDef,
)
from backend.tenancy.models import Locale
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web.auth import CurrentStaff, current_staff, require_csrf
from backend.web.errors import ApiError, ErrorCode, documented

router = APIRouter(prefix="/api")

DESCRIPTION_MAX = 5000
NOTES_MAX = 2000
_WEB_LINK = re.compile(r"^https?://\S+$")


class DetailTypeOut(BaseModel):
    key: str
    label: str
    type: DetailType


@router.get("/detail-types", responses=documented(401))
async def detail_types(
    _staff: CurrentStaff = Depends(current_staff),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> list[DetailTypeOut]:
    rows = await db.scalars(select(DetailTypeDef).order_by(DetailTypeDef.position))
    return [
        DetailTypeOut(
            key=row.key,
            label=row.labels.get(tenant.locale.value) or row.labels[Locale.PT_BR.value],
            type=row.value_type,
        )
        for row in rows
    ]


async def _change(
    db: AsyncSession, project_id: uuid.UUID, row_version: int, values: dict | None = None
) -> Project:
    """Bump the project's row version (with `values`), only if nobody saved it
    since the page loaded it."""
    project = await db.scalar(
        select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
    )
    if project is None:
        raise ApiError(404, ErrorCode.PROJECT_NOT_FOUND)
    if project.status is ProjectStatus.ARCHIVED:
        raise ApiError(409, ErrorCode.PROJECT_ARCHIVED)  # viewable, not editable (section 22)
    changed = await db.execute(
        update(Project)
        .where(Project.id == project_id, Project.row_version == row_version)
        .values(**(values or {}), row_version=Project.row_version + 1)
    )
    if changed.rowcount != 1:
        raise ApiError(409, ErrorCode.PROJECT_CHANGED)
    return project


class DetailIn(BaseModel):
    key: str = Field(max_length=100)
    value: str = Field(max_length=500)  # as typed: text, a number of m², or a date


class ContentIn(BaseModel):
    row_version: int
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX)
    # The whole list, in order; a detail left out is removed.
    details: list[DetailIn] | None = Field(default=None, max_length=50)
    # Changing the type later leaves the stages as they are (section 10).
    project_type: str | None = Field(default=None, max_length=100)


def _detail_value(value_type: DetailType, value: str) -> dict:
    text = value.strip()
    if value_type is DetailType.TEXT:
        if not text:
            raise ApiError(422, ErrorCode.INVALID_DETAIL)
        return {"value_text": text}
    if value_type is DetailType.AREA:
        try:
            number = Decimal(text.replace(",", "."))
        except InvalidOperation:
            raise ApiError(422, ErrorCode.INVALID_DETAIL) from None
        if not number.is_finite() or number < 0 or number >= Decimal("1e10"):
            raise ApiError(422, ErrorCode.INVALID_DETAIL)
        return {"value_number": number.quantize(Decimal("0.01"))}
    try:
        return {"value_date": date.fromisoformat(text)}
    except ValueError:
        raise ApiError(422, ErrorCode.INVALID_DETAIL) from None


@router.patch(
    "/projects/{project_id}/content", status_code=204, responses=documented(401, 404, 409, 422)
)
async def change_content(
    project_id: uuid.UUID,
    body: ContentIn,
    _staff: CurrentStaff = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    values = {}
    if body.description is not None:
        values["description"] = body.description.strip()
    if body.project_type is not None:
        if await db.get(ProjectTypeDef, body.project_type) is None:
            raise ApiError(422, ErrorCode.UNKNOWN_PROJECT_TYPE)
        values["project_type"] = body.project_type
    rows = []
    if body.details is not None:
        known = dict((await db.execute(select(DetailTypeDef.key, DetailTypeDef.value_type))).all())
        if len({d.key for d in body.details}) != len(body.details):
            raise ApiError(422, ErrorCode.INVALID_DETAIL)  # one of each
        for position, detail in enumerate(body.details, start=1):
            if detail.key not in known:
                raise ApiError(422, ErrorCode.INVALID_DETAIL)
            rows.append(
                {
                    "key": detail.key,
                    "value_type": known[detail.key],
                    "position": position,
                    **_detail_value(known[detail.key], detail.value),
                }
            )
    await _change(db, project_id, body.row_version, values)
    if body.details is not None:
        await db.execute(delete(ProjectDetail).where(ProjectDetail.project_id == project_id))
        for row in rows:
            db.add(ProjectDetail(project_id=project_id, **row))
    await db.commit()
    return Response(status_code=204)


class MeetingIn(BaseModel):
    row_version: int
    title: str = Field(max_length=200)
    # In the office's time zone, as staff read them on its clock.
    day: date
    start: time
    end: time | None = None  # an hour after the start if left empty
    location: str | None = Field(default=None, max_length=200)
    link: str | None = Field(default=None, max_length=1000)


async def _next_meeting(db: AsyncSession, project_id: uuid.UUID) -> Meeting | None:
    return await db.scalar(
        select(Meeting)
        .where(Meeting.project_id == project_id, Meeting.ends_at > datetime.now(UTC))
        .order_by(Meeting.starts_at)
        .limit(1)
    )


@router.put(
    "/projects/{project_id}/meeting", status_code=204, responses=documented(401, 404, 409, 422)
)
async def set_meeting(
    project_id: uuid.UUID,
    body: MeetingIn,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """The page shows one meeting, the next: this sets it (a new one, or the
    upcoming one changed)."""
    title = body.title.strip()
    location = (body.location or "").strip() or None
    link = (body.link or "").strip() or None
    zone = ZoneInfo(tenant.timezone)
    starts_at = datetime.combine(body.day, body.start, zone)
    ends_at = (
        datetime.combine(body.day, body.end, zone) if body.end else starts_at + timedelta(hours=1)
    )
    if (
        not 1 <= len(title) <= MEETING_TITLE_MAX
        or ends_at <= starts_at
        or (location and len(location) > MEETING_LOCATION_MAX)
        or (link and not _WEB_LINK.match(link))  # never a javascript: link
        or ends_at <= datetime.now(UTC)  # already over: the page would hide it at once
    ):
        raise ApiError(422, ErrorCode.INVALID_MEETING)
    now = datetime.now(UTC)
    project = await _change(db, project_id, body.row_version, {"last_activity_at": now})
    values = {
        "title": title,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "location": location,
        "link": link,
    }
    upcoming = await _next_meeting(db, project_id)
    if upcoming is None:
        db.add(Meeting(project_id=project_id, **values))
    else:
        await db.execute(update(Meeting).where(Meeting.id == upcoming.id).values(**values))
    kind = EventKind.MEETING_SCHEDULED if upcoming is None else EventKind.MEETING_CHANGED
    record(db, project, kind, title=title)
    await db.commit()
    return Response(status_code=204)


@router.delete(
    "/projects/{project_id}/meeting", status_code=204, responses=documented(401, 404, 409)
)
async def clear_meeting(
    project_id: uuid.UUID,
    row_version: int,
    _staff: CurrentStaff = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    project = await _change(db, project_id, row_version, {"last_activity_at": datetime.now(UTC)})
    upcoming = await _next_meeting(db, project_id)
    if upcoming is not None:
        await db.execute(delete(Meeting).where(Meeting.id == upcoming.id))
        record(db, project, EventKind.MEETING_CLEARED, title=upcoming.title)
    await db.commit()
    return Response(status_code=204)


class NotesIn(BaseModel):
    row_version: int
    notes: str = Field(max_length=NOTES_MAX)


@router.put(
    "/projects/{project_id}/stages/{position}/notes",
    status_code=204,
    responses=documented(401, 404, 409),
)
async def set_notes(
    project_id: uuid.UUID,
    position: int,
    body: NotesIn,
    _staff: CurrentStaff = Depends(require_csrf),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """A stage's note to the client ("Recado"); empty removes it."""
    stage = await db.scalar(
        select(ProjectStage.id).where(
            ProjectStage.project_id == project_id, ProjectStage.position == position
        )
    )
    if stage is None:
        raise ApiError(404, ErrorCode.PROJECT_NOT_FOUND)
    now = datetime.now(UTC)
    project = await _change(db, project_id, body.row_version, {"last_activity_at": now})
    notes = body.notes.strip()
    await db.execute(
        update(ProjectStage)
        .where(ProjectStage.id == stage)
        .values(notes=notes, notes_updated_at=now if notes else None)
    )
    if notes:  # for the updates panel; a note never emails (A32)
        record(db, project, EventKind.NOTE_CHANGED, stage_position=position)
    await db.commit()
    return Response(status_code=204)
