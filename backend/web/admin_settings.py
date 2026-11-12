"""The operator dashboard's "Configurações" (A44): the site's built-in project
types and stages, the same for every office, and how clients are notified (A48).

    GET  /api/admin/settings/types-and-stages      both lists, with how many projects use each
    POST /api/admin/settings/types                 a new type
    PUT  /api/admin/settings/types/{key}           a type's name, hidden, and the stages it lists
    POST /api/admin/settings/stages                a new stage
    PUT  /api/admin/settings/stages/{key}          a stage's name, description, hidden
    PUT  /api/admin/settings/order                 the types' or the stages' order
    GET  /api/admin/settings/notices               "Avisos": batching, reminders, WhatsApp
    PUT  /api/admin/settings/notices               "Avisos" changed

Signed-in operators only, on Unio's own address (as the rest of /api/admin).
Changes use the operator's login and are audited in the same transaction; each
answers with both lists as they now are.
"""

from __future__ import annotations

from datetime import time, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError

from backend.notifications import notices
from backend.notifications.models import (
    ASK_AGAIN_DAYS,
    BEFORE_MINUTES,
    HOLD_MINUTES_MAX,
    QUIET_MINUTES,
    NoticeSettings,
    WhatsAppNews,
)
from backend.operators import actions, catalog
from backend.projects.enums import ProjectType
from backend.projects.models import ProjectTypeDef, StageDef
from backend.tenancy.models import Locale
from backend.web.admin import (
    _action_failure,
    _action_sessionmaker,
    current_operator,
    operator_with_csrf,
)
from backend.web.errors import ApiError, ErrorCode, documented
from backend.web.request_id import current_request_id

router = APIRouter()

PREFIX = "/api/admin/settings"
TEXT_MAX = 2000  # what the request may carry; the lists' own limits are checked after


class SiteTexts(BaseModel):
    pt: str = Field(max_length=TEXT_MAX)
    en: str = Field(default="", max_length=TEXT_MAX)  # blank: the Portuguese


def _texts(stored: dict[str, str]) -> SiteTexts:
    return SiteTexts(pt=stored.get(Locale.PT_BR.value, ""), en=stored.get(Locale.EN.value, ""))


class SiteTypeStageOut(BaseModel):
    key: str
    usual: bool  # ticked for a new project
    about: SiteTexts | None  # the type's own words; None: the stage's general text
    projects: int  # projects of this type that have this stage


class SiteTypeOut(BaseModel):
    key: str
    labels: SiteTexts
    hidden: bool
    # "Outro": lists every stage that isn't hidden; `stages` holds its ticked ones.
    lists_every_stage: bool
    stages: list[SiteTypeStageOut]  # in the stages' order
    projects: int
    # Projects of this type that have each stage, listed or not (one may have been
    # added from "Mostrar todas as etapas"): what its own words for it would reach.
    stage_projects: dict[str, int]


class SiteStageOut(BaseModel):
    key: str
    titles: SiteTexts
    about: SiteTexts
    hidden: bool
    projects: int


class SiteCatalogOut(BaseModel):
    types: list[SiteTypeOut]  # in their order
    stages: list[SiteStageOut]  # in their order
    can_change: bool  # the operator's login is set up for this deployment
    limits: dict[str, int]


async def _catalog(request: Request) -> SiteCatalogOut:
    async with request.app.state.sessionmaker() as db:
        types, stages, listed = await catalog.lists(db)
    used = await catalog.usage(request.app.state.sessionmaker)
    position = {stage.key: n for n, stage in enumerate(stages)}
    by_type: dict[str, list] = {}
    for row in sorted(listed, key=lambda row: position.get(row.stage_key, 0)):
        by_type.setdefault(row.project_type, []).append(row)
    return SiteCatalogOut(
        types=[
            SiteTypeOut(
                key=kind.key,
                labels=_texts(kind.labels),
                hidden=kind.hidden,
                lists_every_stage=kind.key == ProjectType.OTHER,
                stages=[
                    SiteTypeStageOut(
                        key=row.stage_key,
                        usual=row.usual,
                        about=_texts(row.about) if row.about else None,
                        projects=used.type_stages[(kind.key, row.stage_key)],
                    )
                    for row in by_type.get(kind.key, [])
                ],
                projects=used.types[kind.key],
                stage_projects={
                    stage: count
                    for (of_type, stage), count in used.type_stages.items()
                    if of_type == kind.key
                },
            )
            for kind in types
        ],
        stages=[
            SiteStageOut(
                key=stage.key,
                titles=_texts(stage.titles),
                about=_texts(stage.about),
                hidden=stage.hidden,
                projects=used.stages[stage.key],
            )
            for stage in stages
        ],
        can_change=getattr(request.app.state, "operator_sessionmaker", None) is not None,
        limits={
            "typeLabel": catalog.TYPE_LABEL_MAX,
            "stageTitle": catalog.STAGE_TITLE_MAX,
            "stageAbout": catalog.STAGE_ABOUT_MAX,
        },
    )


async def _change(request: Request, operator: dict, change) -> SiteCatalogOut:
    """`change(db)` with the operator's login, audited (as the action it returns)
    in the same transaction."""
    try:
        async with _action_sessionmaker(request)() as db:
            action = await change(db)
            actions.audit_site(db, operator["email"], action, current_request_id())
            await db.commit()
    except catalog.CatalogProblem as problem:
        status = 409 if problem.code == ErrorCode.SETTING_NAME_TAKEN else 422
        raise ApiError(status, ErrorCode(problem.code)) from None
    except SQLAlchemyError as error:  # e.g. two operators adding the same key at once
        raise _action_failure(request, "settings", error) from None
    return await _catalog(request)


@router.get(f"{PREFIX}/types-and-stages", responses=documented(401, 404))
async def types_and_stages(
    request: Request, response: Response, _session: dict = Depends(current_operator)
) -> SiteCatalogOut:
    response.headers["Cache-Control"] = "private, no-store"
    return await _catalog(request)


class NewSiteTypeIn(BaseModel):
    labels: SiteTexts


@router.post(f"{PREFIX}/types", responses=documented(401, 403, 404, 409, 422, 503))
async def new_type(
    body: NewSiteTypeIn, request: Request, operator: dict = Depends(operator_with_csrf)
) -> SiteCatalogOut:
    labels = _checked(body.labels, catalog.TYPE_LABEL_MAX)

    async def change(db):
        return f"settings:type-add:{await catalog.add_type(db, labels)}"

    return await _change(request, operator, change)


class SiteTypeStageIn(BaseModel):
    key: str = Field(max_length=100)
    usual: bool
    about: SiteTexts | None = None  # None: the stage's general text


class SiteTypeIn(BaseModel):
    labels: SiteTexts
    hidden: bool
    stages: list[SiteTypeStageIn] = Field(max_length=200)


@router.put(f"{PREFIX}/types/{{key}}", responses=documented(401, 403, 404, 409, 422, 503))
async def change_type(
    key: str, body: SiteTypeIn, request: Request, operator: dict = Depends(operator_with_csrf)
) -> SiteCatalogOut:
    labels = _checked(body.labels, catalog.TYPE_LABEL_MAX)
    listed = [
        catalog.Listed(
            row.key,
            row.usual,
            _checked(row.about, catalog.STAGE_ABOUT_MAX)
            if row.about and row.about.pt.strip()
            else None,
        )
        for row in body.stages
    ]

    async def change(db):
        await catalog.change_type(db, key, labels, body.hidden, listed)
        return f"settings:type:{key}"

    return await _change(request, operator, change)


class NewSiteStageIn(BaseModel):
    titles: SiteTexts
    about: SiteTexts


@router.post(f"{PREFIX}/stages", responses=documented(401, 403, 404, 409, 422, 503))
async def new_stage(
    body: NewSiteStageIn, request: Request, operator: dict = Depends(operator_with_csrf)
) -> SiteCatalogOut:
    titles = _checked(body.titles, catalog.STAGE_TITLE_MAX)
    about = _checked(body.about, catalog.STAGE_ABOUT_MAX)

    async def change(db):
        return f"settings:stage-add:{await catalog.add_stage(db, titles, about)}"

    return await _change(request, operator, change)


class SiteStageIn(BaseModel):
    titles: SiteTexts
    about: SiteTexts
    hidden: bool


@router.put(f"{PREFIX}/stages/{{key}}", responses=documented(401, 403, 404, 409, 422, 503))
async def change_stage(
    key: str, body: SiteStageIn, request: Request, operator: dict = Depends(operator_with_csrf)
) -> SiteCatalogOut:
    titles = _checked(body.titles, catalog.STAGE_TITLE_MAX)
    about = _checked(body.about, catalog.STAGE_ABOUT_MAX)

    async def change(db):
        await catalog.change_stage(db, key, titles, about, body.hidden)
        return f"settings:stage:{key}"

    return await _change(request, operator, change)


class SiteOrderIn(BaseModel):
    kind: Literal["types", "stages"]
    keys: list[str] = Field(max_length=500)


@router.put(f"{PREFIX}/order", responses=documented(401, 403, 404, 422, 503))
async def change_order(
    body: SiteOrderIn, request: Request, operator: dict = Depends(operator_with_csrf)
) -> SiteCatalogOut:
    model = ProjectTypeDef if body.kind == "types" else StageDef

    async def change(db):
        await catalog.reorder(db, model, body.keys)
        return f"settings:order:{body.kind}"

    return await _change(request, operator, change)


def _checked(given: SiteTexts, limit: int) -> dict[str, str]:
    try:
        return catalog.texts(given.pt, given.en, limit)
    except catalog.CatalogProblem as problem:
        raise ApiError(422, ErrorCode(problem.code)) from None


# -- "Avisos" (A48) ---------------------------------------------------------------------

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"
_MINUTE = timedelta(minutes=1)


class NoticeSettingsIn(BaseModel):
    quiet_minutes: int
    hold_minutes: int
    reminder_morning: str = Field(pattern=HHMM)  # "08:30", the office's time zone
    reminder_evening: str = Field(pattern=HHMM)
    reminder_before_minutes: int
    ask_again_days: int
    whatsapp_news: list[WhatsAppNews] = Field(max_length=len(WhatsAppNews))


class NoticeSettingsOut(NoticeSettingsIn):
    can_change: bool  # the operator's login is set up for this deployment
    limits: dict[str, list[int]]  # each number's [least, most]


def _hhmm(value: time) -> str:
    return value.strftime("%H:%M")


async def _notices(request: Request) -> NoticeSettingsOut:
    async with request.app.state.sessionmaker() as db:
        found = await notices.current(db)
    return NoticeSettingsOut(
        quiet_minutes=found.quiet // _MINUTE,
        hold_minutes=found.hold // _MINUTE,
        reminder_morning=_hhmm(found.morning),
        reminder_evening=_hhmm(found.evening),
        reminder_before_minutes=found.before // _MINUTE,
        ask_again_days=found.ask_again.days,
        whatsapp_news=[news for news in WhatsAppNews if news in found.whatsapp],
        can_change=getattr(request.app.state, "operator_sessionmaker", None) is not None,
        limits={
            "quietMinutes": list(QUIET_MINUTES),
            "holdMinutes": [QUIET_MINUTES[0], HOLD_MINUTES_MAX],
            "reminderBeforeMinutes": list(BEFORE_MINUTES),
            "askAgainDays": list(ASK_AGAIN_DAYS),
        },
    )


@router.get(f"{PREFIX}/notices", responses=documented(401, 404))
async def notice_settings(
    request: Request, response: Response, _session: dict = Depends(current_operator)
) -> NoticeSettingsOut:
    response.headers["Cache-Control"] = "private, no-store"
    return await _notices(request)


def _within(value: int, bounds: tuple[int, int]) -> bool:
    return bounds[0] <= value <= bounds[1]


@router.put(f"{PREFIX}/notices", responses=documented(401, 403, 404, 422, 503))
async def change_notice_settings(
    body: NoticeSettingsIn, request: Request, operator: dict = Depends(operator_with_csrf)
) -> NoticeSettingsOut:
    morning = time.fromisoformat(body.reminder_morning)
    evening = time.fromisoformat(body.reminder_evening)
    if not (
        _within(body.quiet_minutes, QUIET_MINUTES)
        and _within(body.hold_minutes, (body.quiet_minutes, HOLD_MINUTES_MAX))
        and _within(body.reminder_before_minutes, BEFORE_MINUTES)
        and _within(body.ask_again_days, ASK_AGAIN_DAYS)
        and evening > morning
    ):
        raise ApiError(422, ErrorCode.INVALID_NOTICE_SETTINGS)
    try:
        async with _action_sessionmaker(request)() as db:
            await db.execute(
                update(NoticeSettings)
                .where(NoticeSettings.id == 1)
                .values(
                    quiet_minutes=body.quiet_minutes,
                    hold_minutes=body.hold_minutes,
                    reminder_morning=morning,
                    reminder_evening=evening,
                    reminder_before_minutes=body.reminder_before_minutes,
                    ask_again_days=body.ask_again_days,
                    whatsapp_news=[
                        news.value for news in WhatsAppNews if news in body.whatsapp_news
                    ],
                )
            )
            actions.audit_site(db, operator["email"], "settings:notices", current_request_id())
            await db.commit()
    except SQLAlchemyError as error:
        raise _action_failure(request, "settings", error) from None
    return await _notices(request)
