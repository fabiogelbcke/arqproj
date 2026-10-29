"""Creating an office from a link an operator sent (A38, A36): the start of a
signup page.

    GET  /criar-escritorio               the page (the dashboard's bundle)
    POST /api/office-signup/check        is the link still good; is this address free
    POST /api/office-signup/create       create the office; returns its owner link
    POST /api/admin/signup-links         (operators) make a link, shown once

Only on Unio's own address (OPERATOR_HOST), like the dashboard. The holder of a
link names the office and picks its address, `{address}.{OPERATOR_HOST}`; the
office is created through the operator's database login, as the dashboard does,
and the link is used up in the same transaction. The browser then goes on to the
new address's owner signup (name, email, password, the emailed code), so this
page never creates an account itself. The token travels in the address's
fragment and the request body, never the path, so it stays out of logs. An
open signup page later is this page without the link, plus abuse controls.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.db.isolation import scope_to_tenant
from backend.operators import actions
from backend.tenancy.middleware import SIGNUP_PAGE
from backend.tenancy.resolve import current_tenant
from backend.web import admin, pages
from backend.web.auth import optional_staff
from backend.web.errors import ApiError, ErrorCode, documented
from backend.web.office import NAME_LIMIT
from backend.web.request_id import current_request_id

log = logging.getLogger(__name__)
router = APIRouter()

ADDRESS_MIN, ADDRESS_MAX = 3, 40
# Addresses Unio may want for itself, or that would read as Unio's.
RESERVED = frozenset(
    {
        "admin", "api", "app", "assets", "blog", "contato", "docs", "help", "mail",
        "painel", "staging", "static", "status", "suporte", "support", "unio", "www",
    }
)  # fmt: skip


def _address(value: str) -> str:
    """The address as typed, if it is a usable first part of a hostname."""
    address = value.strip().lower()
    usable = (
        ADDRESS_MIN <= len(address) <= ADDRESS_MAX
        and all(ch.isascii() and (ch.isalnum() or ch == "-") for ch in address)
        and not address.startswith("-")
        and not address.endswith("-")
        and "--" not in address  # never punycode's "xn--"
        and address not in RESERVED
    )
    if not usable:
        raise ApiError(422, ErrorCode.INVALID_OFFICE_ADDRESS)
    return address


def _name(value: str) -> str:
    name = " ".join(value.split())
    if not name or len(name) > NAME_LIMIT:
        raise ApiError(422, ErrorCode.INVALID_OFFICE_NAME)
    return name


def _hostname(request: Request, address: str) -> str:
    return f"{address}.{request.app.state.settings.operator_host}"


class CheckIn(BaseModel):
    token: str = Field(max_length=200)
    address: str | None = Field(default=None, max_length=100)


class CheckOut(BaseModel):
    domain: str  # what follows the address: "myunio.app"
    address_free: bool | None = None  # when an address was asked about


class CreateIn(BaseModel):
    token: str = Field(max_length=200)
    name: str = Field(max_length=200)
    address: str = Field(max_length=100)


class CreateOut(BaseModel):
    owner_url: str  # the new address's owner signup, where the browser goes next


def _failure(request: Request, error: Exception) -> ApiError:
    log.error("office signup: route=%s operation=create detail=%s", request.url.path, error)
    if isinstance(error, IntegrityError):  # the address taken a moment ago
        return ApiError(409, ErrorCode.OFFICE_ADDRESS_TAKEN)
    return ApiError(503, ErrorCode.OPERATOR_ACTION_FAILED)


@router.post(
    "/api/office-signup/check",
    responses=documented(404, 422, 503),
    dependencies=[Depends(admin._on_operator_host)],
)
async def check(body: CheckIn, request: Request, response: Response) -> CheckOut:
    response.headers["Cache-Control"] = "private, no-store"
    domain = request.app.state.settings.operator_host
    address = _address(body.address) if body.address is not None else None
    try:
        async with admin._action_sessionmaker(request)() as db:
            await actions.usable_signup_link(db, body.token)
            if address is None:
                return CheckOut(domain=domain)
            free = await actions.address_free(db, address, _hostname(request, address))
            return CheckOut(domain=domain, address_free=free)
    except SQLAlchemyError as error:
        raise _failure(request, error) from None


@router.post(
    "/api/office-signup/create",
    responses=documented(404, 409, 422, 503),
    dependencies=[Depends(admin._on_operator_host)],
)
async def create(body: CreateIn, request: Request, response: Response) -> CreateOut:
    response.headers["Cache-Control"] = "private, no-store"
    name, address = _name(body.name), _address(body.address)
    settings = request.app.state.settings
    try:
        async with admin._action_sessionmaker(request)() as db:
            url = await actions.create_from_signup(
                db,
                body.token,
                name,
                address,
                _hostname(request, address),
                current_request_id(),
                settings.local_site_port,
            )
            await db.commit()
    except SQLAlchemyError as error:
        raise _failure(request, error) from None
    log.info("office signup: created %s", address)
    return CreateOut(owner_url=url)


class SignupLinkOut(BaseModel):
    url: str


@router.post("/api/admin/signup-links", responses=documented(401, 403, 404, 503))
async def make_link(
    request: Request, response: Response, operator: dict = Depends(admin.operator_with_csrf)
) -> SignupLinkOut:
    """ "Link para criar escritório": one-time, for 7 days, shown only now."""
    response.headers["Cache-Control"] = "private, no-store"
    settings = request.app.state.settings
    try:
        async with admin._action_sessionmaker(request)() as db:
            url = actions.signup_link(
                db, operator["email"], settings.operator_host, settings.local_site_port
            )
            await db.commit()
    except SQLAlchemyError as error:
        raise _failure(request, error) from None
    return SignupLinkOut(url=url)


@router.get(SIGNUP_PAGE, include_in_schema=False)
async def page(request: Request) -> Response:
    try:
        admin._on_operator_host(request)
    except ApiError:
        # On an office's address it's no signup page: a project may have that address.
        if getattr(request.state, "tenant", None) is None:
            return PlainTextResponse("Not found", status_code=404)
        tenant = current_tenant(request)
        async with request.app.state.sessionmaker() as db:
            scope_to_tenant(db.sync_session, tenant.id)
            staff = await optional_staff(request, Response(), db)
            return await pages.shell(request, SIGNUP_PAGE.lstrip("/"), staff, tenant, db)
    shell = Path(admin._settings(request).frontend_dist) / "admin.html"
    if not shell.is_file():
        return PlainTextResponse(
            "The dashboard is not built. Run `make build` (or `make dev`).", status_code=503
        )
    return FileResponse(
        shell, headers={"Cache-Control": "no-cache", "Content-Security-Policy": admin.POLICY}
    )
