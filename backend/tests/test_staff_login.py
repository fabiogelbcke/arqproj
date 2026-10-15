"""Staff sign-in, sessions and CSRF, through the API, as the app's restricted login."""

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text, update

from backend.commands.seed import seed
from backend.identity import accounts
from backend.identity.models import LoginSession
from backend.tenancy.models import Tenant
from backend.web import auth

pytestmark = pytest.mark.anyio

PASSWORD = "correct horse battery"


async def add_staff(db, slug, email, password=PASSWORD, role="owner"):
    """Create an account in a tenant, the way the staff command does."""
    tenant_id = await db.scalar(select(Tenant.id).where(Tenant.slug == slug))
    await db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})
    return await accounts.create_user(db, email=email, name="Ana", password=password, role=role)


@pytest.fixture
async def staff(db_session):
    await seed(db_session)
    await add_staff(db_session, "alinea", "ana@alinea.example")
    # Same email in another tenant: a separate account with its own password.
    await add_staff(db_session, "norte", "ana@alinea.example", password="another password 123")


@pytest.fixture
def failed_delays(monkeypatch):
    """Records the delay after failed sign-ins instead of waiting for it."""
    waited = []

    async def no_wait(seconds):
        waited.append(seconds)

    monkeypatch.setattr(auth.anyio, "sleep", no_wait)
    return waited


async def sign_in(client, host="alinea.localhost", email="ana@alinea.example", password=PASSWORD):
    return await client.post(
        "/api/session", json={"email": email, "password": password}, headers={"host": host}
    )


async def test_sign_in_sets_a_session_cookie_and_returns_the_csrf_token(client, staff):
    response = await sign_in(client)
    assert response.status_code == 200
    body = response.json()
    assert (body["email"], body["role"], body["tenant_slug"]) == (
        "ana@alinea.example",
        "owner",
        "alinea",
    )
    assert body["csrf_token"]
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
    assert "domain=" not in cookie  # bound to this exact address


async def test_the_cookie_is_https_only_when_deployed(app, client, staff):
    app.state.settings = app.state.settings.model_copy(update={"environment": "production"})
    response = await sign_in(client)
    assert "secure" in response.headers["set-cookie"].lower()


async def test_me_answers_for_the_signed_in_staff_member(client, staff):
    await sign_in(client)
    me = await client.get("/api/me", headers={"host": "alinea.localhost"})
    assert me.status_code == 200
    assert me.json()["email"] == "ana@alinea.example"


async def test_email_is_not_case_sensitive(client, staff):
    assert (await sign_in(client, email="  ANA@Alinea.Example ")).status_code == 200


async def test_wrong_password_and_unknown_email_look_the_same(client, staff, failed_delays):
    wrong_password = await sign_in(client, password="not the password")
    unknown_email = await sign_in(client, email="nobody@alinea.example")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert failed_delays == [auth.FAILED_LOGIN_DELAY] * 2
    assert "set-cookie" not in wrong_password.headers


async def test_another_tenants_password_does_not_work_here(client, staff, failed_delays):
    response = await sign_in(client, password="another password 123")  # norte's password
    assert response.status_code == 401


async def test_a_session_only_works_on_its_own_tenant(client, staff):
    await sign_in(client, host="alinea.localhost")
    # The same cookie, sent to another tenant's address.
    elsewhere = await client.get("/api/me", headers={"host": "norte.localhost"})
    assert elsewhere.status_code == 401


async def test_no_cookie_means_not_signed_in(client, staff):
    response = await client.get("/api/me", headers={"host": "alinea.localhost"})
    assert response.status_code == 401


async def test_sign_out_needs_the_csrf_token(client, staff):
    csrf = (await sign_in(client)).json()["csrf_token"]
    host = {"host": "alinea.localhost"}

    refused = await client.delete("/api/session", headers=host)
    assert refused.status_code == 403
    wrong = await client.delete("/api/session", headers={**host, auth.CSRF_HEADER: "nope"})
    assert wrong.status_code == 403
    assert (await client.get("/api/me", headers=host)).status_code == 200  # still signed in

    signed_out = await client.delete("/api/session", headers={**host, auth.CSRF_HEADER: csrf})
    assert signed_out.status_code == 204
    assert (await client.get("/api/me", headers=host)).status_code == 401


async def test_a_signed_out_token_stays_dead(client, staff):
    """Signing out revokes the session itself, not only the browser's cookie."""
    response = await sign_in(client)
    token = response.cookies[auth.COOKIE]
    host = {"host": "alinea.localhost"}
    await client.delete(
        "/api/session", headers={**host, auth.CSRF_HEADER: response.json()["csrf_token"]}
    )
    client.cookies.set(auth.COOKIE, token)  # e.g. a copy taken earlier
    assert (await client.get("/api/me", headers=host)).status_code == 401


async def test_an_expired_session_is_refused(client, db_session, staff):
    await sign_in(client)
    await db_session.execute(
        update(LoginSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    assert (await client.get("/api/me", headers={"host": "alinea.localhost"})).status_code == 401


async def test_using_a_session_keeps_it_alive(client, db_session, staff):
    await sign_in(client)
    a_while_ago = datetime.now(UTC) - timedelta(hours=2)
    await db_session.execute(
        update(LoginSession).values(
            last_seen_at=a_while_ago, expires_at=a_while_ago + timedelta(days=1)
        )
    )
    me = await client.get("/api/me", headers={"host": "alinea.localhost"})
    assert me.status_code == 200
    row = await db_session.scalar(select(LoginSession))
    await db_session.refresh(row)
    assert row.expires_at > datetime.now(UTC) + timedelta(days=29)
    # The browser's cookie is extended too, or it would expire first.
    max_age = int(me.headers["set-cookie"].lower().split("max-age=")[1].split(";")[0])
    assert max_age > timedelta(days=29).total_seconds()


async def test_signing_out_removes_the_cookie(client, staff):
    csrf = (await sign_in(client)).json()["csrf_token"]
    await client.delete(
        "/api/session", headers={"host": "alinea.localhost", auth.CSRF_HEADER: csrf}
    )
    assert auth.COOKIE not in client.cookies


async def test_only_a_hash_of_the_token_is_stored(client, db_session, staff):
    token = (await sign_in(client)).cookies[auth.COOKIE]
    stored = await db_session.scalar(select(LoginSession.token_hash))
    assert token not in stored
    assert stored == hashlib.sha256(token.encode()).hexdigest()
