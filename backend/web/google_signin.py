"""Office staff sign in with Google (A38, plan section 5): "Entrar com Google".

    POST /api/auth/google/start    on the office's address: Google's sign-in address
    GET  /api/auth/google/finish   on the office's address: the return, completed

Google sends everyone back to one registered address on Unio's own host
(`backend/web/admin.py`, CALLBACK), which forwards the return, unchanged, to the
office that started: its address is in the signed `state`, and must be one
registered to that office. The sign-in is completed only there:

- The browser that started holds, in a cookie for that office's address alone,
  the flow's state, nonce and PKCE verifier. Another browser, or a return opened
  on another office's address, finds nothing to match.
- Google's code is the hand-off: it works once, for minutes, and only with that
  verifier, so a copied or replayed return can't be redeemed (section 5 asks for
  a single-use code bound to the office and the browser; Google's, with PKCE,
  is one, so the app mints and stores none of its own).

Google signs in an existing account of this office by its verified email, and
never makes one: invites and sign-up links do. Proving the email this way also
confirms it (an unconfirmed sign-up). A pending invite is accepted only through
its link first. Passwords keep working.
"""

from __future__ import annotations

import logging
import secrets
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.identity import accounts
from backend.operators.google_signin import GoogleSignIn, SignInError, new_verifier
from backend.security import keys
from backend.tenancy.resolve import CurrentTenant, current_tenant, resolve
from backend.web import attempts
from backend.web.auth import signed_in
from backend.web.errors import ApiError, ErrorCode, documented
from backend.web.request_id import current_request_id

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth/google")

FINISH = "/api/auth/google/finish"
STATE_PURPOSE = "office-signin-state"
FLOW_PURPOSE = "office-signin-flow"
FLOW_COOKIE = "google_signin"
TTL = 600  # long enough to sign in at Google
TRIES = "google-signin"
SIGN_IN_PAGE = "/painel/entrar"
AFTER = "/painel/"


class StartOut(BaseModel):
    url: str


def google(request: Request) -> GoogleSignIn:
    settings = request.app.state.settings
    if not (settings.google_oauth_client_id and settings.google_oauth_client_secret):
        raise ApiError(503, ErrorCode.SIGNIN_NOT_CONFIGURED)
    return GoogleSignIn(
        settings.google_oauth_client_id,
        settings.google_oauth_client_secret,
        settings.google_signin_redirect_uri,
    )


@router.post("/start", responses=documented(503))
async def start(
    request: Request, response: Response, tenant: CurrentTenant = Depends(current_tenant)
) -> StartOut:
    client = google(request)
    settings = request.app.state.settings
    flow = {
        "state": secrets.token_urlsafe(24),
        "nonce": secrets.token_urlsafe(24),
        "verifier": new_verifier(),
    }
    origin = f"{request.url.scheme}://{request.headers['host']}"
    state = keys.sign(
        settings.app_secret,
        STATE_PURPOSE,
        {"origin": origin, "tenant": str(tenant.id), "flow": flow["state"]},
        TTL,
    )
    response.set_cookie(
        FLOW_COOKIE,
        keys.sign(settings.app_secret, FLOW_PURPOSE, flow, TTL),
        max_age=TTL,
        path=FINISH,
        httponly=True,
        samesite="lax",  # sent on the top-level redirect back from Unio's address
        secure=settings.deployed,
    )
    return StartOut(url=client.authorization_url(state, flow["nonce"], flow["verifier"]))


def office_state(request: Request) -> dict | None:
    """The return's `state`, if it is an office's sign-in (and not an operator's)."""
    try:
        return keys.verify(
            request.app.state.settings.app_secret,
            STATE_PURPOSE,
            request.query_params.get("state", ""),
        )
    except keys.BadToken:
        return None


async def forward(request: Request, state: dict) -> Response:
    """At Unio's return address: on to the office that started, only to an address
    registered to that office."""
    origin = state["origin"]
    async with request.app.state.sessionmaker() as session:
        resolution = await resolve(session, urlsplit(origin).netloc)
    if resolution is None or str(resolution.tenant.id) != state["tenant"]:
        log.warning("google sign-in return for an address not registered to its office")
        return Response("Not found", status_code=404, media_type="text/plain")
    return RedirectResponse(f"{origin}{FINISH}?{request.url.query}", status_code=302)


def _back(problem: str | None = None) -> RedirectResponse:
    # With the request ID its log line carries, so the page shows the support code.
    target = f"{SIGN_IN_PAGE}?google={problem}&ref={current_request_id()}" if problem else AFTER
    response = RedirectResponse(target, status_code=302)
    response.delete_cookie(FLOW_COOKIE, path=FINISH)
    return response


@router.get("/finish", include_in_schema=False)
async def finish(
    request: Request,
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> Response:
    settings = request.app.state.settings
    state = office_state(request)
    try:
        flow = keys.verify(settings.app_secret, FLOW_PURPOSE, request.cookies.get(FLOW_COOKIE, ""))
    except keys.BadToken:
        return _back("expirado")  # another browser, or too late
    if (
        state is None
        or state["tenant"] != str(tenant.id)  # started at another office
        or not secrets.compare_digest(state["flow"], flow["state"])
    ):
        return _back("expirado")
    if request.query_params.get("error") or not request.query_params.get("code"):
        return _back("cancelado")
    # A few failed exchanges per device, as passwords are (section 5: hand-offs
    # are rate-limited): a replayed return can't make the server call Google at will.
    who = attempts.device(request)
    if not attempts.admit(TRIES, who):
        return _back("tentativas")
    try:
        identity = await google(request).identify(
            getattr(request.app.state, "http", None),  # set up at app start
            request.query_params["code"],
            flow["verifier"],
            flow["nonce"],
        )
    except (SignInError, ApiError) as error:
        attempts.failed(TRIES, who)
        detail = error.detail if isinstance(error, SignInError) else error.code
        log.error("google sign-in failed: route=%s tenant=%s %s", FINISH, tenant.slug, detail)
        return _back("falhou")
    attempts.succeeded(TRIES, who)
    user = await accounts.find_user(db, identity.email)
    if user is not None:
        # As codes and links do: one confirmation at a time per account, its address
        # read again under the lock (a correction meanwhile must not be confirmed).
        await accounts.lock_confirmation(db, user.id)
        await db.refresh(user)
    if user is None or user.email != identity.email:
        log.info("google sign-in: no account for that email in %s", tenant.slug)
        return _back("sem-conta")
    if user.password_hash is None:
        # A pending invite (A36): accepted only through its link, which sets the
        # password; until then the team page offers to cancel or resend it, which
        # must never touch an account in use.
        return _back("convite")
    # Google has shown the address is theirs: a pending sign-up or invite counts.
    await accounts.confirm_email(db, user)
    response = _back()
    await signed_in(request, response, tenant, db, user, method="google")  # commits
    log.info("staff %s signed in with google in %s", user.id, tenant.slug)
    return response
