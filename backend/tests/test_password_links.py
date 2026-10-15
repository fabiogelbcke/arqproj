"""Choosing a password with an invite or reset link, through the API, as the app's
restricted login (so the narrow grants are exercised too)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text, update

from backend.commands.seed import seed
from backend.identity import accounts, links
from backend.identity.models import LinkKind, PasswordLink
from backend.tenancy.models import Tenant
from backend.web import auth

pytestmark = pytest.mark.anyio

ALINEA = {"host": "alinea.localhost"}
NEW_PASSWORD = "chosen by me"


async def scope(db, slug):
    tenant_id = await db.scalar(select(Tenant.id).where(Tenant.slug == slug))
    await db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})


async def invite(db, slug="alinea", email="ana@example.com", kind=LinkKind.INVITE, password=None):
    """An account (as the staff command makes it) and a link for it."""
    await scope(db, slug)
    user = await accounts.find_user(db, email) or await accounts.create_user(
        db, email=email, name="Ana", password=password
    )
    return await links.create(db, user, kind)


@pytest.fixture
async def tenants(db_session):
    await seed(db_session)


async def choose(client, token, password=NEW_PASSWORD, headers=ALINEA):
    return await client.post(
        "/api/password", json={"token": token, "password": password}, headers=headers
    )


async def sign_in(client, password=NEW_PASSWORD):
    return await client.post(
        "/api/session",
        json={"email": "ana@example.com", "password": password},
        headers=ALINEA,
    )


async def test_an_invite_lets_the_person_choose_a_password_and_signs_them_in(
    client, db_session, tenants
):
    token = await invite(db_session)
    checked = await client.post("/api/password-link", json={"token": token}, headers=ALINEA)
    assert checked.json() == {"email": "ana@example.com", "name": "Ana", "kind": "invite"}

    chosen = await choose(client, token)
    assert chosen.status_code == 200
    assert chosen.json()["email"] == "ana@example.com"
    assert (await client.get("/api/me", headers=ALINEA)).status_code == 200
    client.cookies.clear()
    assert (await sign_in(client)).status_code == 200  # the chosen password works


async def test_an_invited_account_cannot_sign_in_before_choosing(
    client, db_session, tenants, monkeypatch
):
    await invite(db_session)

    async def no_wait(_seconds):
        pass

    monkeypatch.setattr(auth.anyio, "sleep", no_wait)
    response = await sign_in(client, password="")
    assert response.json() == {"error": "invalid_credentials"}


async def test_a_link_works_once(client, db_session, tenants):
    token = await invite(db_session)
    assert (await choose(client, token)).status_code == 200
    again = await choose(client, token, password="somebody else's")
    assert (again.status_code, again.json()) == (404, {"error": "link_invalid"})
    client.cookies.clear()
    assert (await sign_in(client)).status_code == 200  # the first choice stands


async def test_a_too_short_password_keeps_the_link_usable(client, db_session, tenants):
    token = await invite(db_session)
    short = await choose(client, token, password="1234567")
    assert (short.status_code, short.json()) == (422, {"error": "password_too_short"})
    assert "set-cookie" not in short.headers
    assert (await choose(client, token, password="12345678")).status_code == 200


async def test_an_expired_link_is_refused(client, db_session, tenants):
    token = await invite(db_session)
    await db_session.execute(
        update(PasswordLink).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    checked = await client.post("/api/password-link", json={"token": token}, headers=ALINEA)
    assert checked.status_code == 404
    assert (await choose(client, token)).status_code == 404


async def test_a_link_only_works_on_its_own_offices_address(client, db_session, tenants):
    token = await invite(db_session, slug="norte")
    assert (await choose(client, token, headers=ALINEA)).status_code == 404
    assert (await choose(client, token, headers={"host": "norte.localhost"})).status_code == 200


async def test_a_reset_ends_every_other_sign_in(client, db_session, tenants):
    await invite(db_session, password="the old password")
    old = await sign_in(client, password="the old password")
    old_cookie = old.cookies[auth.COOKIE]

    token = await invite(db_session, kind=LinkKind.RESET)
    assert (await choose(client, token)).status_code == 200
    client.cookies.set(auth.COOKIE, old_cookie)  # e.g. a stolen copy
    assert (await client.get("/api/me", headers=ALINEA)).status_code == 401
    client.cookies.clear()
    assert (await sign_in(client, password="the old password")).status_code == 401
    assert (await sign_in(client)).status_code == 200


async def test_hashing_the_new_password_holds_no_database_connection(
    app, client, db_session, tenants, monkeypatch
):
    """Hashing is slow on purpose; the pool is small (see sign-in)."""
    token = await invite(db_session)
    opened, holding = [], []
    make_session = app.state.sessionmaker

    def recording_sessionmaker():
        context = make_session()
        opened.append(context.session)
        return context

    real_hash = accounts.new_password_hash

    async def watched_hash(password):
        holding.extend(session.in_transaction() for session in opened)
        return await real_hash(password)

    app.state.sessionmaker = recording_sessionmaker
    monkeypatch.setattr(accounts, "new_password_hash", watched_hash)
    assert (await choose(client, token)).status_code == 200
    assert opened and not any(holding)
