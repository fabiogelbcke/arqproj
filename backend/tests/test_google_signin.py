"""Office staff sign in with Google (plan section 5): through Unio's one return
address, completed only on the office's own address, in the browser that
started, for an existing account of that office."""

from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import text

from backend.commands.seed import seed
from backend.identity import accounts
from backend.identity.models import Role
from backend.operators.google_signin import GoogleSignIn, Identity, SignInError, challenge
from backend.security import keys
from backend.tests.test_office import ALINEA, NORTE, sign_in_as, tenant_id
from backend.tests.test_team import Sent
from backend.web import attempts, auth, email_confirmation, google_signin

pytestmark = pytest.mark.anyio

UNIO = {"host": "localhost"}  # where Google returns (OPERATOR_HOST, locally)
ANA = "dona@alinea.example"


@pytest.fixture
async def google(app, client, db_session, monkeypatch):
    await seed(db_session)
    await sign_in_as(client, db_session, ANA, Role.OWNER)
    client.cookies.clear()  # signed out again: the test signs in with Google
    app.state.settings = app.state.settings.model_copy(
        update={"google_oauth_client_id": "client-1", "google_oauth_client_secret": "secret-1"}
    )
    answers = {"identity": Identity(ANA, "Ana"), "calls": 0}
    attempts.reset()

    async def identify(self, http, code, verifier, nonce):
        answers["got"] = (code, verifier, nonce)
        answers["calls"] += 1
        if isinstance(answers["identity"], Exception):
            raise answers["identity"]
        return answers["identity"]

    monkeypatch.setattr(GoogleSignIn, "identify", identify)
    return answers


async def start(client, host=ALINEA) -> dict:
    response = await client.post("/api/auth/google/start", headers=host)
    assert response.status_code == 200
    return {k: v[0] for k, v in parse_qs(urlsplit(response.json()["url"]).query).items()}


async def returned(client, query: dict, **change):
    """Google's return to Unio's address, then on to the office's."""
    params = {"state": query["state"], "code": "c-1"} | change
    back = await client.get("/api/auth/google/callback", params=params, headers=UNIO)
    assert back.status_code == 302
    on = urlsplit(back.headers["location"])
    return await client.get(f"{on.path}?{on.query}", headers={"host": on.netloc})


async def test_google_asked_only_who_with_pkce_returning_to_unios_address(client, google):
    query = await start(client)
    assert query["scope"] == "openid email profile"
    assert query["redirect_uri"] == "http://localhost:5173/api/auth/google/callback"
    assert query["code_challenge_method"] == "S256" and query["nonce"]


async def test_the_return_goes_on_to_the_office_and_signs_in_there(client, google):
    query = await start(client)
    back = await client.get(
        "/api/auth/google/callback", params={"state": query["state"], "code": "c-1"}, headers=UNIO
    )
    assert back.headers["location"].startswith("http://alinea.localhost/api/auth/google/finish?")
    done = await returned(client, query)
    assert (done.status_code, done.headers["location"]) == (302, "/painel/")
    code, verifier, nonce = google["got"]
    assert code == "c-1" and challenge(verifier) == query["code_challenge"]
    assert nonce == query["nonce"]
    me = await client.get("/api/me", headers=ALINEA)
    assert (me.status_code, me.json()["email"]) == (200, ANA)


async def test_a_return_in_another_browser_signs_nobody_in(client, google):
    query = await start(client)
    client.cookies.clear()
    done = await returned(client, query)
    assert done.headers["location"].startswith("/painel/entrar?google=expirado&ref=")
    assert (await client.get("/api/me", headers=ALINEA)).status_code == 401


async def test_started_at_one_office_it_never_finishes_at_another(client, google):
    query = await start(client, NORTE)
    forged = await client.get(
        "/api/auth/google/finish",
        params={"state": query["state"], "code": "c-1"},
        headers=ALINEA,
    )
    assert forged.headers["location"].startswith("/painel/entrar?google=expirado&ref=")
    assert (await client.get("/api/me", headers=ALINEA)).status_code == 401


async def test_unios_address_forwards_only_to_an_address_of_that_office(app, client, google):
    state = keys.sign(
        app.state.settings.app_secret,
        google_signin.STATE_PURPOSE,
        {"origin": "http://norte.localhost", "tenant": "00000000-0000-0000-0000-000000000000"},
        60,
    )
    back = await client.get(
        "/api/auth/google/callback", params={"state": state, "code": "c-1"}, headers=UNIO
    )
    assert back.status_code == 404


async def test_cancelled_at_google_says_so(client, google):
    query = await start(client)
    done = await returned(client, query, error="access_denied", code="")
    assert done.headers["location"].startswith("/painel/entrar?google=cancelado&ref=")


async def test_an_email_without_an_account_here_gets_none_made(client, google, db_session):
    google["identity"] = Identity("alguem@gmail.com", None)
    query = await start(client)
    done = await returned(client, query)
    assert done.headers["location"].startswith("/painel/entrar?google=sem-conta&ref=")
    made = await db_session.scalar(
        text("SELECT count(*) FROM users WHERE email = 'alguem@gmail.com'")
    )
    assert made == 0


async def test_googles_failure_is_logged_and_said_only_to_have_failed(client, google, caplog):
    google["identity"] = SignInError("token endpoint 500: detail")
    query = await start(client)
    done = await returned(client, query)
    assert done.headers["location"].startswith("/painel/entrar?google=falhou&ref=")
    assert "token endpoint 500: detail" in caplog.text


async def _joined_as(client, db_session, email="caio@gmail.com", password="a good password"):
    """Someone joined through the office's shared link with this address (A36):
    signed in, unconfirmed. The browser's session cookie, then signed out here."""
    t = await tenant_id(db_session, "alinea")
    await db_session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(t)})
    await accounts.create_user(
        db_session, email=email, name="Caio", password=password, email_confirmed=False
    )
    joined = await client.post(
        "/api/session", json={"email": email, "password": password}, headers=ALINEA
    )
    assert (joined.status_code, joined.json()["email_confirmed"]) == (200, False)
    cookie = client.cookies.get(auth.COOKIE)
    client.cookies.clear()
    return cookie


async def test_google_confirms_a_pending_sign_ups_email(client, google, db_session):
    await _joined_as(client, db_session)
    google["identity"] = Identity("caio@gmail.com", "Caio")
    query = await start(client)
    await returned(client, query)
    me = (await client.get("/api/me", headers=ALINEA)).json()
    assert (me["email"], me["email_confirmed"]) == ("caio@gmail.com", True)


async def test_google_confirming_a_sign_up_keeps_nothing_its_maker_chose(
    client, google, db_session
):
    """Anyone holding the shared link can sign up with a colleague's address. When
    the colleague then proves it with Google, the one who signed up must not end up
    with a working account: their session ends and their password stops working."""
    joiners_cookie = await _joined_as(client, db_session)
    google["identity"] = Identity("caio@gmail.com", "Caio")
    await returned(client, await start(client))
    real_caio = client.cookies.get(auth.COOKIE)
    assert (await client.get("/api/team", headers=ALINEA)).status_code == 200

    client.cookies.clear()
    client.cookies.set(auth.COOKIE, joiners_cookie)
    assert (await client.get("/api/me", headers=ALINEA)).status_code == 401
    client.cookies.clear()
    password = await client.post(
        "/api/session",
        json={"email": "caio@gmail.com", "password": "a good password"},
        headers=ALINEA,
    )
    assert (password.status_code, password.json()) == (401, {"error": "invalid_credentials"})

    marked = await db_session.scalar(
        text("SELECT unconfirmed_signup FROM users WHERE email = 'caio@gmail.com'")
    )
    assert marked is False  # a member like any other from now on
    # The address's owner carries on, and is a member like any other: not shown as
    # an invite (which could be cancelled) and let in by Google again.
    client.cookies.set(auth.COOKIE, real_caio)
    team = (await client.get("/api/team", headers=ALINEA)).json()["members"]
    assert {m["email"]: m["status"] for m in team}["caio@gmail.com"] == "active"
    client.cookies.clear()
    again = await returned(client, await start(client))
    assert again.headers["location"] == "/painel/"


async def test_google_confirming_a_changed_email_keeps_the_account_as_it_is(
    client, google, db_session, monkeypatch
):
    """A changed email ("Minha conta") is unconfirmed too, but the account was the
    person's before: Google confirming the new address ends nothing."""
    box = Sent()
    monkeypatch.setattr(email_confirmation, "sender_for", lambda settings, http: box)
    signed = await client.post(
        "/api/session", json={"email": ANA, "password": "a good password"}, headers=ALINEA
    )
    headers = {**ALINEA, auth.CSRF_HEADER: signed.json()["csrf_token"]}
    changed = await client.post(
        "/api/me/email/change",
        json={"current": "a good password", "email": "ana.nova@gmail.com"},
        headers=headers,
    )
    assert (changed.status_code, changed.json()["email_confirmed"]) == (200, False)
    this_device = client.cookies.get(auth.COOKIE)
    client.cookies.clear()
    google["identity"] = Identity("ana.nova@gmail.com", "Ana")
    assert (await returned(client, await start(client))).headers["location"] == "/painel/"
    me = (await client.get("/api/me", headers=ALINEA)).json()
    assert (me["email"], me["email_confirmed"]) == ("ana.nova@gmail.com", True)
    client.cookies.clear()
    client.cookies.set(auth.COOKIE, this_device)
    assert (await client.get("/api/projects", headers=ALINEA)).status_code == 200
    client.cookies.clear()
    password = await client.post(
        "/api/session",
        json={"email": "ana.nova@gmail.com", "password": "a good password"},
        headers=ALINEA,
    )
    assert password.status_code == 200


async def test_google_ends_no_sign_in_of_a_confirmed_account(client, google, db_session):
    """Signing in with Google on one device leaves the account's password and its
    other devices alone."""
    elsewhere = await client.post(
        "/api/session", json={"email": ANA, "password": "a good password"}, headers=ALINEA
    )
    assert elsewhere.status_code == 200
    other_device = client.cookies.get(auth.COOKIE)
    client.cookies.clear()
    await returned(client, await start(client))
    assert (await client.get("/api/me", headers=ALINEA)).status_code == 200
    client.cookies.clear()
    client.cookies.set(auth.COOKIE, other_device)
    assert (await client.get("/api/me", headers=ALINEA)).status_code == 200
    client.cookies.clear()
    again = await client.post(
        "/api/session", json={"email": ANA, "password": "a good password"}, headers=ALINEA
    )
    assert again.status_code == 200


async def test_an_unexpected_failure_at_google_still_counts_as_a_try(client, google, monkeypatch):
    """The try reserved before asking Google ends however the exchange ends: an
    error is no free try, and doesn't keep the device waiting for good."""
    clock = [1000.0]
    monkeypatch.setattr(attempts.time, "monotonic", lambda: clock[0])
    google["identity"] = RuntimeError("unexpected")
    for _ in range(attempts.LIMIT):
        assert (await returned(client, await start(client))).status_code == 500
    google["identity"] = Identity(ANA, "Ana")
    blocked = await returned(client, await start(client))
    assert blocked.headers["location"].startswith("/painel/entrar?google=tentativas&ref=")
    clock[0] += attempts.WINDOW_SECONDS + 1
    assert (await returned(client, await start(client))).headers["location"] == "/painel/"


async def test_not_configured_says_so_without_detail(app, client, google):
    app.state.settings = app.state.settings.model_copy(update={"google_oauth_client_id": None})
    response = await client.post("/api/auth/google/start", headers=ALINEA)
    assert (response.status_code, response.json()) == (503, {"error": "signin_not_configured"})


async def test_the_page_gets_the_failures_support_code(client, google):
    google["identity"] = SignInError("token endpoint 500: detail")
    query = await start(client)
    done = await returned(client, query)
    ref = parse_qs(urlsplit(done.headers["location"]).query)["ref"][0]
    assert ref and ref == done.headers["x-request-id"]  # the log line's ID


async def test_it_waits_for_a_confirmation_under_way_on_the_account(client, google, db_session):
    """As codes and links do (accounts.lock_confirmation): an address corrected
    meanwhile must not be confirmed by Google's answer for the old one."""
    from backend.tests.test_team import _waits_for

    query = await start(client)
    user_id = await db_session.scalar(text("SELECT id FROM users WHERE email = :e"), {"e": ANA})
    lock = "SELECT pg_advisory_xact_lock(hashtext('email-code'), hashtext(:k))"
    params = {"state": query["state"], "code": "c-1"}
    back = await client.get("/api/auth/google/callback", params=params, headers=UNIO)
    on = urlsplit(back.headers["location"])
    call = lambda: client.get(f"{on.path}?{on.query}", headers={"host": on.netloc})  # noqa: E731
    assert await _waits_for(lock, str(user_id), call) == 302


async def test_an_address_corrected_meanwhile_is_not_signed_in(
    client, google, db_session, monkeypatch
):
    """The account's address changed while the lock was awaited: Google vouched
    for the old one, so nobody is signed in and nothing is confirmed."""

    async def corrected_meanwhile(session, user_id):
        await session.execute(
            text("UPDATE users SET email = 'outro@gmail.com' WHERE id = :u"), {"u": str(user_id)}
        )

    monkeypatch.setattr(accounts, "lock_confirmation", corrected_meanwhile)
    query = await start(client)
    done = await returned(client, query)
    assert done.headers["location"].startswith("/painel/entrar?google=sem-conta&ref=")
    assert (await client.get("/api/me", headers=ALINEA)).status_code == 401


async def test_a_pending_invite_is_accepted_only_through_its_link(client, google, db_session):
    """Signed in with Google, an invited account would still read as a pending
    invite (no password), and cancelling that would delete an account in use."""
    t = await tenant_id(db_session, "alinea")
    await db_session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(t)})
    await accounts.create_user(db_session, email="bia@alinea.example", name="Bia")  # invited
    google["identity"] = Identity("bia@alinea.example", "Bia")
    query = await start(client)
    done = await returned(client, query)
    assert done.headers["location"].startswith("/painel/entrar?google=convite&ref=")
    assert (await client.get("/api/me", headers=ALINEA)).status_code == 401


async def test_a_device_failing_again_and_again_must_wait(client, google):
    """Section 5: hand-offs are rate-limited, so a replayed return can't make the
    server call Google at will (5 failures in 15 minutes, as passwords)."""
    google["identity"] = SignInError("invalid_grant")
    for _ in range(attempts.LIMIT):
        query = await start(client)
        done = await returned(client, query)
        assert done.headers["location"].startswith("/painel/entrar?google=falhou")
    calls = google["calls"]
    query = await start(client)
    done = await returned(client, query)
    assert done.headers["location"].startswith("/painel/entrar?google=tentativas&ref=")
    assert google["calls"] == calls  # Google not asked again
