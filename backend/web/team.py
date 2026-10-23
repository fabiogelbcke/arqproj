"""Configurações → Equipe: owners invite staff (A36, 20 Oct 2026).

    GET    /api/team                  the office's staff, pending invites, the shared link's state
    POST   /api/team/invites          owner: invite a person (an account without a password, and
                                      an emailed link to choose one; the link comes back to copy)
    POST   /api/team/invites/{id}/link  owner: a new link for a pending invite, emailed again
    DELETE /api/team/invites/{id}       owner: cancel a pending invite
    POST   /api/team/join-link        owner: turn the shared link on (a new one; any old one stops)
    DELETE /api/team/join-link        owner: turn it off
    POST   /api/join/check            anyone with the shared link: is it on, and whose
    POST   /api/join                  anyone with it: a name and an email, to be emailed a link

An invite is the existing one-time link (`backend.identity.links`), so the person
always chooses their own password. The shared link never makes an account usable
by itself: it emails that link to the address given, so the address is proven
theirs (plan section 5), and it always makes a member.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

import anyio
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.identity import accounts, links
from backend.identity.emails import is_email, tidy_email
from backend.identity.models import JoinLink, LinkKind, Role, User
from backend.notifications.email import Email, EmailError, sender_for
from backend.notifications.office import office_of
from backend.notifications.password_reset import invite_email
from backend.office.profile import display_name
from backend.tenancy.resolve import CurrentTenant, current_tenant
from backend.web import attempts
from backend.web.auth import CurrentStaff, current_staff, require_csrf
from backend.web.errors import ApiError, ErrorCode, documented

NAME_MAX = 80
JOIN_PATH = "/painel/entrar-na-equipe"
# Requests from the shared link: a few per device in 15 minutes (as "Esqueceu a
# senha?"), and every answer as late as the slowest, so none tells who has an account.
JOIN_TRIES = "join"
JOIN_ANSWER_AT = 0.5
JOIN_LINK_LIFETIME = timedelta(hours=24)  # Fabio, 20 Oct 2026: a link passed around goes stale
RESEND_AFTER = timedelta(minutes=2)  # at most one emailed link per address in this time
# One request per address at a time, until its transaction ends: two at once must not
# both find no account and both make one (the second would fail, and say it exists).
_LOCK_EMAIL = text("SELECT pg_advisory_xact_lock(hashtext('staff-email'), hashtext(:email))")
# One change to an office's shared link at a time (a double click on "Criar novo
# link" must not try to turn on two).
_LOCK_JOIN_LINK = text("SELECT pg_advisory_xact_lock(hashtext('join-link'), hashtext(:tenant))")

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class MemberOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: Role
    # "invited": hasn't chosen a password through the invite yet.
    status: Literal["active", "invited"]
    me: bool


class JoinLinkOut(BaseModel):
    on: bool
    expires_at: str | None  # when the one that's on stops working (ISO)


class TeamOut(BaseModel):
    members: list[MemberOut]
    join_link: JoinLinkOut
    can_manage: bool  # an owner: invites and the shared link


class InviteIn(BaseModel):
    name: str = Field(max_length=500)
    email: str = Field(max_length=500)
    role: Role = Role.MEMBER


class InviteOut(BaseModel):
    member: MemberOut
    link: str  # to copy and send another way
    emailed: bool  # False: the email couldn't go; the link still works


class LinkOnOut(BaseModel):
    link: str  # shown now only: only its hash is kept
    expires_at: str


class JoinCheckIn(BaseModel):
    token: str = Field(max_length=200)


class JoinCheckOut(BaseModel):
    office: str


class JoinIn(BaseModel):
    token: str = Field(max_length=200)
    name: str = Field(max_length=500)
    email: str = Field(max_length=500)


def _owner(staff: CurrentStaff) -> None:
    if staff.role is not Role.OWNER:
        raise ApiError(403, ErrorCode.OWNER_ONLY)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _member(user: User, staff: CurrentStaff) -> MemberOut:
    return MemberOut(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        status="active" if user.password_hash else "invited",
        me=user.id == staff.user_id,
    )


def _name(raw: str) -> str:
    name = " ".join(raw.split())
    if not name or len(name) > NAME_MAX:
        raise ApiError(422, ErrorCode.INVALID_STAFF_NAME)
    return name


def _address(raw: str) -> str:
    email = tidy_email(raw)
    if not is_email(email):
        raise ApiError(422, ErrorCode.INVALID_EMAIL)
    return email


async def _send(request: Request, tenant: CurrentTenant, email: Email, route: str) -> bool:
    """Whether it went; a failure is logged with its detail, and the person is told
    only that the email couldn't go (AGENTS.md)."""
    try:
        http = getattr(request.app.state, "http", None)  # set up at app start
        await sender_for(request.app.state.settings, http).send(email)
        return True
    except EmailError as error:
        log.error("invite email failed: route=%s tenant=%s %s", route, tenant.slug, error.detail)
        return False


async def _invite(
    db: AsyncSession, request: Request, tenant: CurrentTenant, user: User, inviter: str | None
) -> tuple[str, Email]:
    """A new invite link for `user` (any earlier one stops working), and its email.
    On the office's stored address, never one taken from the request (section 4)."""
    token = await links.create(db, user, LinkKind.INVITE)
    office = await office_of(db, request.app.state.settings, tenant.id)
    link = f"{office.base}{links.PATH}#token={token}"
    return link, invite_email(office, user.name, user.email, token, inviter)


@router.get("/team", responses=documented(401))
async def team(
    staff: CurrentStaff = Depends(current_staff),
    db: AsyncSession = Depends(get_tenant_session),
) -> TeamOut:
    users = list(await db.scalars(select(User)))
    # People who can sign in first, by name; then pending invites.
    users.sort(key=lambda user: (user.password_hash is None, user.name.lower()))
    on = await db.scalar(select(JoinLink).where(*_working()))
    return TeamOut(
        members=[_member(user, staff) for user in users],
        join_link=JoinLinkOut(
            on=on is not None,
            expires_at=(on.created_at + JOIN_LINK_LIFETIME).isoformat() if on else None,
        ),
        can_manage=staff.role is Role.OWNER,
    )


@router.post("/team/invites", status_code=201, responses=documented(401, 403, 409, 422))
async def invite(
    body: InviteIn,
    request: Request,
    staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> InviteOut:
    _owner(staff)
    name, email = _name(body.name), _address(body.email)
    await db.execute(_LOCK_EMAIL, {"email": email})
    found = await accounts.find_user(db, email)
    if found is not None and found.password_hash is not None:
        raise ApiError(409, ErrorCode.ALREADY_STAFF, found.name)
    # Invited before and not in yet: a new invite, with what's given now (its old
    # link goes with the old account; the app never edits an account's role).
    if found is not None and not await _delete_pending(db, found):
        raise ApiError(409, ErrorCode.ALREADY_STAFF, found.name)  # in, just now
    user = await accounts.create_user(db, email=email, name=name, role=body.role)
    link, message = await _invite(db, request, tenant, user, staff.name)
    await db.commit()
    posthog = getattr(request.app.state, "posthog", None)
    if posthog is not None:
        posthog.capture("staff_invited", properties={"role": str(body.role)})
    emailed = await _send(request, tenant, message, "/api/team/invites")
    log.info("staff %s invited to %s by %s", user.id, tenant.slug, staff.user_id)
    return InviteOut(member=_member(user, staff), link=link, emailed=emailed)


async def _delete_pending(db: AsyncSession, user: User) -> bool:
    """Deletes the account only if it's still pending, in one statement: if its
    invite is used meanwhile (a password chosen), the row is in and stays."""
    gone = await db.scalar(
        delete(User).where(User.id == user.id, User.password_hash.is_(None)).returning(User.id)
    )
    db.expunge(user)
    return gone is not None


async def _pending(db: AsyncSession, user_id: uuid.UUID) -> User:
    # Read from the database every time (never this session's copy): called again
    # once a lock is held, it must see an invite used or cancelled meanwhile.
    user = await db.get(User, user_id, populate_existing=True)
    if user is None:
        raise ApiError(404, ErrorCode.NOT_AN_INVITE)
    if user.password_hash is not None:
        raise ApiError(409, ErrorCode.NOT_AN_INVITE)  # already in
    return user


@router.post("/team/invites/{user_id}/link", responses=documented(401, 403, 404, 409))
async def invite_again(
    user_id: uuid.UUID,
    request: Request,
    staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> InviteOut:
    _owner(staff)
    user = await _pending(db, user_id)
    # As an invite: two at once must not leave two links working.
    await db.execute(_LOCK_EMAIL, {"email": user.email})
    user = await _pending(db, user_id)  # still pending once it's this request's turn
    link, message = await _invite(db, request, tenant, user, staff.name)
    await db.commit()
    emailed = await _send(request, tenant, message, "/api/team/invites/{user_id}/link")
    return InviteOut(member=_member(user, staff), link=link, emailed=emailed)


@router.delete("/team/invites/{user_id}", status_code=204, responses=documented(401, 403, 404, 409))
async def cancel_invite(
    user_id: uuid.UUID,
    staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> None:
    """Only a pending invite: its account and links go (removing staff who are in
    comes later, A36)."""
    _owner(staff)
    user = await _pending(db, user_id)
    if not await _delete_pending(db, user):
        raise ApiError(409, ErrorCode.NOT_AN_INVITE)  # in, just now
    await db.commit()
    log.info("invite %s cancelled in %s by %s", user_id, tenant.slug, staff.user_id)


@router.post("/team/join-link", status_code=201, responses=documented(401, 403))
async def join_link_on(
    request: Request,
    staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> LinkOnOut:
    _owner(staff)
    await db.execute(_LOCK_JOIN_LINK, {"tenant": str(tenant.id)})
    await db.execute(
        update(JoinLink).where(JoinLink.revoked_at.is_(None)).values(revoked_at=func.now())
    )
    token = secrets.token_urlsafe(24)
    made = JoinLink(created_by=staff.user_id, token_hash=_hash(token))
    db.add(made)
    office = await office_of(db, request.app.state.settings, tenant.id)
    await db.commit()
    await db.refresh(made)
    return LinkOnOut(
        link=f"{office.base}{JOIN_PATH}#token={token}",
        expires_at=(made.created_at + JOIN_LINK_LIFETIME).isoformat(),
    )


@router.delete("/team/join-link", status_code=204, responses=documented(401, 403))
async def join_link_off(
    staff: CurrentStaff = Depends(require_csrf),
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> None:
    _owner(staff)
    await db.execute(_LOCK_JOIN_LINK, {"tenant": str(tenant.id)})
    await db.execute(
        update(JoinLink).where(JoinLink.revoked_at.is_(None)).values(revoked_at=func.now())
    )
    await db.commit()


def _working():
    """A shared link that's on: not turned off or replaced, and under 24 hours old."""
    return (JoinLink.revoked_at.is_(None), JoinLink.created_at > func.now() - JOIN_LINK_LIFETIME)


async def _join_link(db: AsyncSession, token: str) -> JoinLink:
    found = await db.scalar(
        select(JoinLink).where(JoinLink.token_hash == _hash(token), *_working())
    )
    if found is None:
        raise ApiError(404, ErrorCode.JOIN_LINK_INVALID)
    return found


@router.post("/join/check", responses=documented(404))
async def check_join_link(
    body: JoinCheckIn,
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> JoinCheckOut:
    await _join_link(db, body.token)
    return JoinCheckOut(office=await display_name(db, tenant))


@router.post("/join", status_code=202, responses=documented(404, 422, 429))
async def join(
    body: JoinIn,
    request: Request,
    background: BackgroundTasks,
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> None:
    """Emails an invite link to the address given, as a new member. The same answer
    whatever the address, and no sooner than JOIN_ANSWER_AT: someone with an account
    already gets nothing (they can sign in, or use "Esqueceu a senha?")."""
    who = attempts.device(request)
    if not attempts.admit(JOIN_TRIES, who):
        raise ApiError(429, ErrorCode.TOO_MANY_ATTEMPTS)
    attempts.failed(JOIN_TRIES, who)  # every request counts toward the limit
    started = anyio.current_time()
    await _join_link(db, body.token)
    name, email = _name(body.name), _address(body.email)
    await db.execute(_LOCK_EMAIL, {"email": email})
    found = await accounts.find_user(db, email)
    message: Email | None = None
    if found is None:
        user = await accounts.create_user(db, email=email, name=name, role=Role.MEMBER)
        message = (await _invite(db, request, tenant, user, None))[1]
    # A pending invite gets a new link only if it's a member's: the shared link
    # never lets anyone in as an owner (A36), even through an owner's invite.
    elif (
        found.password_hash is None
        and found.role is Role.MEMBER
        and not await _recent_invite(db, found)
    ):
        message = (await _invite(db, request, tenant, found, None))[1]
    await db.commit()  # the connection goes back before the wait
    await anyio.sleep(max(0.0, JOIN_ANSWER_AT - (anyio.current_time() - started)))
    if message is not None:
        background.add_task(_send, request, tenant, message, "/api/join")


async def _recent_invite(db: AsyncSession, user: User) -> bool:
    """An invite link went to them in the last few minutes: don't send another
    (someone else may be typing their address in again and again)."""
    return await links.made_since(db, user, LinkKind.INVITE, datetime.now(UTC) - RESEND_AFTER)
