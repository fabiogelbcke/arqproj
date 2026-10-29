"""Proposals in the painel (A42): the generator, its versions and presets.

    GET   /api/projects/{id}/proposal          what the generator starts from
    POST  /api/projects/{id}/proposal/preview  the PDF of what is on screen, unsaved
    POST  /api/projects/{id}/proposals         save it as the next version
    GET   /api/projects/{id}/proposals/{v}/pdf a saved version's PDF (staff)
    POST  /api/projects/{id}/accept-proposal   "Proposta aceita": the project goes live
    PUT   /api/proposal-presets                the office's services, the whole list
    PATCH /api/proposal-defaults               the office's opening and observations

Anyone signed in may use them (A42: every staff member for now). Saving a proposal
also fills in the office's address, city, phone, WhatsApp, email and signing
architect where the office has none yet, so they are asked for once. An owner may
also replace the ones already set, when asked on saving (`update_office`).
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.identity.emails import is_email, tidy_email
from backend.identity.models import Role, User
from backend.office.models import LogoType, OfficeProfile
from backend.office.profile import profile as load_profile
from backend.projects.enums import ProjectStatus
from backend.projects.models import Project, ProjectSlug
from backend.proposals.content import (
    AMOUNT_MAX,
    INTRO_MAX,
    NOTES_MAX,
    SERVICES_MAX,
    ProposalContent,
    Service,
    in_words,
    money,
)
from backend.proposals.models import Proposal, ProposalServicePreset
from backend.proposals.pdf import date_line, fill, render, texts
from backend.storage.base import StorageError
from backend.storage.connections import storage_for
from backend.storage.models import StorageConnection
from backend.tenancy.models import Locale
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web.auth import CurrentStaff, current_staff, require_csrf
from backend.web.errors import ApiError, ErrorCode, documented
from backend.web.projects import ProjectSummary, summaries

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

PDF_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "private, no-store",
}


# -- shared with the client page -------------------------------------------------


def in_proposal(project: Project) -> bool:
    """The client page shows only the proposal: a proposal still open, or one
    archived without being accepted."""
    return project.status is ProjectStatus.PROPOSAL or (
        project.status is ProjectStatus.ARCHIVED and project.archived_from is ProjectStatus.PROPOSAL
    )


async def latest(db: AsyncSession, project_id: uuid.UUID) -> Proposal | None:
    return await db.scalar(
        select(Proposal)
        .where(Proposal.project_id == project_id)
        .order_by(Proposal.version.desc())
        .limit(1)
    )


async def logo_bytes(
    request: Request, db: AsyncSession, found: OfficeProfile | None
) -> bytes | None:
    """The office's logo for a PDF: an SVG logo's PNG (PDF readers draw no SVG).
    None without one, or when storage can't give it: the PDF shows the name."""
    if found is None or found.logo_file_id is None:
        return None
    file_id = found.logo_png_file_id if found.logo_type is LogoType.SVG else found.logo_file_id
    connection = await db.scalar(select(StorageConnection))
    if file_id is None or connection is None:
        return None
    try:
        google = getattr(request.app.state, "google", None)  # set up at app start
        storage = storage_for(connection, request.app.state.settings, google)
        download = await storage.download(await storage.get(file_id))
        try:
            return b"".join([chunk async for chunk in download.chunks])
        finally:
            await download.aclose()
    except StorageError as error:
        log.warning("proposal logo unavailable: %s %s", error.problem, error.detail)
        return None


async def pdf_response(
    request: Request,
    db: AsyncSession,
    tenant: CurrentTenant,
    project: Project,
    content: ProposalContent,
    download: bool,
    headers: dict[str, str] | None = None,
) -> Response:
    found = await load_profile(db)
    pdf = render(
        content,
        office_name=found.display_name if found else tenant.name,
        project_name=project.name,
        logo=await logo_bytes(request, db, found),
        locale=tenant.locale,
    )
    name = fill(texts(tenant.locale)["pdf"]["fileName"], name=project.name)
    # The name as typed (UTF-8), and a plain one for older browsers.
    plain = name.encode("ascii", "ignore").decode().replace('"', "")
    disposition = f'{"attachment" if download else "inline"}; filename="{plain}"; '
    disposition += f"filename*=UTF-8''{quote(name)}"
    return Response(
        pdf,
        media_type="application/pdf",
        headers={**PDF_HEADERS, **(headers or {}), "Content-Disposition": disposition},
    )


class ServiceOut(BaseModel):
    title: str
    description: str


class PaymentOut(BaseModel):
    amount: str  # "R$ 5.800,00", in the office's language
    when: str


class ProposalOut(BaseModel):
    """The latest proposal, ready to show on the page (A42)."""

    version: int
    date_line: str  # "Joinville, 7 de outubro de 2026"
    client_name: str
    intro: str
    services: list[ServiceOut]
    fee: str  # "" while the generator has no fee yet
    fee_in_words: str
    payments: list[PaymentOut]
    not_included: list[str]
    notes: str
    signatory: str
    address: str
    phone: str
    whatsapp: str
    email: str
    pdf_url: str  # changes with each version, so browsers fetch the new one


def proposal_out(content: ProposalContent, version: int, locale: Locale, url: str) -> ProposalOut:
    """The proposal, ready to show on a page."""
    return ProposalOut(
        version=version,
        date_line=date_line(content, locale),
        client_name=content.client_name,
        intro=content.intro,
        services=[ServiceOut(title=s.title, description=s.description) for s in content.services],
        fee=money(content.fee, locale) if content.fee else "",
        fee_in_words=in_words(content.fee, locale) if content.fee else "",
        payments=[
            PaymentOut(amount=money(p.amount, locale), when=p.when) for p in content.payments
        ],
        not_included=content.not_included,
        notes=content.notes,
        signatory=content.signatory,
        address=content.address,
        phone=content.phone,
        whatsapp=content.whatsapp,
        email=content.email,
        pdf_url=url,
    )


# -- the generator ----------------------------------------------------------------


class PresetOut(BaseModel):
    title: str
    description: str


class VersionOut(BaseModel):
    version: int
    created_at: datetime
    created_by: str | None  # the staff member's name


class ProposalStart(ProposalContent):
    """What the generator opens with: the latest version, or a new proposal from
    the office's details and defaults. Without a version, no fee yet."""

    fee: int | None = Field(default=None, gt=0, le=AMOUNT_MAX)  # type: ignore[assignment]
    services: list[Service] = Field(default=[], max_length=SERVICES_MAX)


class OfficeDetailsOut(BaseModel):
    address: str
    city: str
    phone: str
    whatsapp: str
    email: str
    signatory: str


class GeneratorOut(BaseModel):
    project_id: uuid.UUID
    project_name: str
    slug: str
    status: ProjectStatus
    row_version: int
    start: ProposalStart
    versions: list[VersionOut]  # newest first
    presets: list[PresetOut]  # the office's services, or the built-in list
    # The office's details as set: a blank one is filled in from the next saved proposal.
    office: OfficeDetailsOut
    # The office's own opening and observations, else the built-in ones.
    default_intro: str
    default_notes: str


def _defaults(found: OfficeProfile | None, locale: Locale) -> tuple[str, str]:
    built_in = texts(locale)["defaults"]
    intro = found.proposal_intro if found and found.proposal_intro is not None else None
    notes = found.proposal_notes if found and found.proposal_notes is not None else None
    return (
        intro if intro is not None else built_in["intro"],
        notes if notes is not None else built_in["notes"],
    )


async def presets(db: AsyncSession, locale: Locale) -> list[PresetOut]:
    own = list(
        await db.scalars(select(ProposalServicePreset).order_by(ProposalServicePreset.position))
    )
    if own:
        return [PresetOut(title=p.title, description=p.description) for p in own]
    return [PresetOut(**service) for service in texts(locale)["defaults"]["services"]]


def _office(found: OfficeProfile | None) -> OfficeDetailsOut:
    return OfficeDetailsOut(
        address=(found and found.address) or "",
        city=(found and found.city) or "",
        phone=(found and found.phone) or "",
        whatsapp=(found and found.whatsapp) or "",
        email=(found and found.contact_email) or "",
        signatory=(found and found.signatory) or "",
    )


async def _project(db: AsyncSession, project_id: uuid.UUID, lock: bool = False) -> Project:
    query = select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
    project = await db.scalar(query.with_for_update() if lock else query)
    if project is None:
        raise ApiError(404, ErrorCode.PROJECT_NOT_FOUND)
    return project


def _today(tenant: CurrentTenant) -> date:
    try:
        return datetime.now(ZoneInfo(tenant.timezone)).date()
    except (KeyError, ValueError):
        return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


@router.get("/projects/{project_id}/proposal", responses=documented(401, 404))
async def generator(
    project_id: uuid.UUID,
    _staff: CurrentStaff = Depends(current_staff),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> GeneratorOut:
    project = await _project(db, project_id)
    found = await load_profile(db)
    office = _office(found)
    intro, notes = _defaults(found, tenant.locale)
    offered = await presets(db, tenant.locale)
    newest = await latest(db, project.id)
    if newest is not None:
        start = ProposalStart.model_validate(newest.content)
    else:
        start = ProposalStart(
            client_name=project.client_name,
            city=office.city,
            date=_today(tenant),
            intro=intro,
            services=[Service(title=p.title, description=p.description) for p in offered],
            notes=notes,
            signatory=office.signatory,
            address=office.address,
            phone=office.phone,
            whatsapp=office.whatsapp,
            email=office.email,
        )
    slug = await db.scalar(
        select(ProjectSlug.slug).where(ProjectSlug.project_id == project.id, ProjectSlug.is_current)
    )
    versions = [
        VersionOut(version=version, created_at=created_at, created_by=name)
        for version, created_at, name in await db.execute(
            select(Proposal.version, Proposal.created_at, User.name)
            .outerjoin(User, User.id == Proposal.created_by)
            .where(Proposal.project_id == project.id)
            .order_by(Proposal.version.desc())
        )
    ]
    return GeneratorOut(
        project_id=project.id,
        project_name=project.name,
        slug=slug or "",
        status=project.status,
        row_version=project.row_version,
        start=start,
        versions=versions,
        presets=offered,
        office=office,
        default_intro=intro,
        default_notes=notes,
    )


@router.post(
    "/projects/{project_id}/proposal/preview",
    responses={**documented(401, 404, 422), 200: {"content": {"application/pdf": {}}}},
    response_class=Response,
)
async def preview(
    request: Request,
    project_id: uuid.UUID,
    body: ProposalContent,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    """What is on screen, as the PDF will be: nothing is saved."""
    project = await _project(db, project_id)
    return await pdf_response(request, db, tenant, project, body, download=False)


@router.post("/projects/{project_id}/proposal/preview-page", responses=documented(401, 404, 422))
async def preview_page(
    project_id: uuid.UUID,
    body: ProposalStart,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> ProposalOut:
    """What is on screen, as the client page will show it (amounts written out in
    the office's language): the generator's live preview. Nothing is saved."""
    await _project(db, project_id)
    return proposal_out(body, 0, tenant.locale, "")


async def _fill_office_details(
    db: AsyncSession, tenant: CurrentTenant, content: ProposalContent, replace: bool
) -> None:
    """The office's details from the proposal: those it has no value for yet, or,
    with `replace`, every one the proposal gives. A blank never clears one."""
    found = await load_profile(db)
    if found is None:
        found = OfficeProfile(display_name=tenant.name)
        db.add(found)
    for column, value in (
        ("address", content.address),
        ("city", content.city),
        ("phone", content.phone),
        ("whatsapp", content.whatsapp),
        ("signatory", content.signatory),
    ):
        if value and (replace or not getattr(found, column)):
            setattr(found, column, value)
    email = tidy_email(content.email)
    if email and is_email(email) and (replace or not found.contact_email):
        found.contact_email = email


@router.post(
    "/projects/{project_id}/proposals",
    status_code=201,
    responses=documented(401, 403, 404, 409, 422),
)
async def save(
    project_id: uuid.UUID,
    body: ProposalContent,
    update_office: bool = False,
    staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> VersionOut:
    """The next version. The client page shows it at once (A42: no email)."""
    if update_office and staff.role is not Role.OWNER:
        raise ApiError(403, ErrorCode.OWNER_ONLY)
    # Locked until saved: two saves at once get consecutive versions.
    project = await _project(db, project_id, lock=True)
    if project.status is ProjectStatus.ARCHIVED:
        raise ApiError(409, ErrorCode.PROJECT_ARCHIVED)
    number = (
        await db.scalar(
            select(func.coalesce(func.max(Proposal.version), 0)).where(
                Proposal.project_id == project.id
            )
        )
    ) + 1
    saved = Proposal(
        project_id=project.id,
        version=number,
        content=body.model_dump(mode="json"),
        created_by=staff.user_id,
    )
    db.add(saved)
    await _fill_office_details(db, tenant, body, replace=update_office)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ApiError(409, ErrorCode.PROJECT_CHANGED) from None
    await db.refresh(saved)
    log.info("proposal v%s saved for project %s in %s", number, project.id, tenant.slug)
    return VersionOut(version=number, created_at=saved.created_at, created_by=staff.name)


@router.get(
    "/projects/{project_id}/proposals/{version}/pdf",
    responses={**documented(401, 404), 200: {"content": {"application/pdf": {}}}},
    response_class=Response,
)
async def version_pdf(
    request: Request,
    project_id: uuid.UUID,
    version: int,
    download: bool = False,
    _staff: CurrentStaff = Depends(current_staff),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    project = await _project(db, project_id)
    found = await db.scalar(
        select(Proposal).where(Proposal.project_id == project.id, Proposal.version == version)
    )
    if found is None:
        raise ApiError(404, ErrorCode.PROPOSAL_NOT_FOUND)
    content = ProposalContent.model_validate(found.content)
    return await pdf_response(request, db, tenant, project, content, download)


class AcceptIn(BaseModel):
    row_version: int


@router.post("/projects/{project_id}/accept-proposal", responses=documented(401, 404, 409, 422))
async def accept(
    project_id: uuid.UUID,
    body: AcceptIn,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> ProjectSummary:
    """ "Proposta aceita": the page shows the project, with a link to the proposal.
    Accepting twice changes nothing."""
    project = await _project(db, project_id)
    if project.status is ProjectStatus.PROPOSAL:
        accepted = await db.execute(
            update(Project)
            .where(
                Project.id == project.id,
                Project.status == ProjectStatus.PROPOSAL,
                Project.row_version == body.row_version,
            )
            .values(status=ProjectStatus.ACTIVE, row_version=Project.row_version + 1)
        )
        if accepted.rowcount != 1:  # archived or changed meanwhile
            raise ApiError(409, ErrorCode.PROJECT_CHANGED)
        await db.commit()
    elif project.status is not ProjectStatus.ACTIVE:
        raise ApiError(422, ErrorCode.INVALID_STATUS_CHANGE)  # completed, archived or draft
    db.expire_all()
    return (await summaries(db, tenant.locale, only=project_id))[0]


# -- the office's presets and defaults --------------------------------------------


class PresetsIn(BaseModel):
    services: list[Service] = Field(max_length=SERVICES_MAX)


@router.put("/proposal-presets", responses=documented(401, 422))
async def change_presets(
    body: PresetsIn,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> list[PresetOut]:
    """The office's services, in order ("Salvar como padrão"). An empty list goes
    back to the built-in one."""
    await db.execute(delete(ProposalServicePreset))
    for position, service in enumerate(body.services, start=1):
        db.add(
            ProposalServicePreset(
                position=position, title=service.title, description=service.description
            )
        )
    await db.commit()
    return await presets(db, tenant.locale)


class DefaultsIn(BaseModel):
    # None leaves it as it is; "" saves an empty one.
    intro: str | None = Field(default=None, max_length=INTRO_MAX)
    notes: str | None = Field(default=None, max_length=NOTES_MAX)


class DefaultsOut(BaseModel):
    intro: str
    notes: str


@router.patch("/proposal-defaults", responses=documented(401, 422))
async def change_defaults(
    body: DefaultsIn,
    _staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> DefaultsOut:
    """The opening and observations new proposals start with."""
    found = await load_profile(db)
    if found is None:
        found = OfficeProfile(display_name=tenant.name)
        db.add(found)
    if body.intro is not None:
        found.proposal_intro = body.intro.strip()
    if body.notes is not None:
        found.proposal_notes = body.notes.strip()
    await db.commit()
    intro, notes = _defaults(found, tenant.locale)
    return DefaultsOut(intro=intro, notes=notes)
