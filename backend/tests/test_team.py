"""Configurações → Equipe (A36): owners invite staff, personally or with a shared
link whose joiners choose a password at once and still prove their email."""

import logging
import re
import secrets
from datetime import UTC, datetime, timedelta

import anyio
import httpx2
import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app import create_app
from backend.commands.seed import seed
from backend.db.isolation import scope_to_tenant
from backend.identity import accounts
from backend.identity.models import JoinLink, Role, User
from backend.notifications.email import EmailError
from backend.settings import Settings
from backend.tenancy.models import Tenant, TenantDomain
from backend.tests.conftest import RUNTIME_ROLE, TEST_DATABASE_URL
from backend.tests.test_office import ALINEA, NORTE, sign_in_as, tenant_id
from backend.web import attempts, email_confirmation, team
from backend.web.errors import ApiError

pytestmark = pytest.mark.anyio


class Sent:
    def __init__(self):
        self.emails = []
        self.failing = False

    async def send(self, email):
        if self.failing:
            raise EmailError("resend 500: down")
        self.emails.append(email)
        return "id"


@pytest.fixture
async def sent(monkeypatch):
    attempts.reset()
    box = Sent()
    monkeypatch.setattr(team, "sender_for", lambda settings, http: box)
    monkeypatch.setattr(email_confirmation, "sender_for", lambda settings, http: box)
    yield box
    attempts.reset()


@pytest.fixture
async def owner(client, db_session):
    await seed(db_session)
    return await sign_in_as(client, db_session, "dona@alinea.example", Role.OWNER)


def token_in(text: str) -> str:
    return re.search(r"#token=([\w-]+)", text).group(1)


def code_in(text: str) -> str:
    return re.search(r"^(\d{6})$", text, re.MULTILINE).group(1)


async def invite(client, headers, **body):
    body = {"name": "Bia Souza", "email": "bia@alinea.example"} | body
    return await client.post("/api/team/invites", json=body, headers=headers)


async def choose_password(client, token, host=ALINEA):
    return await client.post(
        "/api/password", json={"token": token, "password": "a good password"}, headers=host
    )


# -- personal invites --------------------------------------------------------------


async def test_an_invite_emails_a_link_that_lets_them_choose_a_password_and_come_in(
    client, owner, sent
):
    response = await invite(client, owner, email="  Bia@Alinea.example ", name=" Bia   Souza ")
    assert response.status_code == 201
    out = response.json()
    assert out["member"] | {"id": None} == {
        "id": None,
        "name": "Bia Souza",
        "email": "bia@alinea.example",
        "role": "member",
        "status": "invited",
        "me": False,
    }
    assert out["emailed"] is True
    [email] = sent.emails
    assert email.to == "bia@alinea.example"
    assert "Bia Souza" not in email.subject and "Alinea" in email.subject
    # The office's own address, the link to copy is the emailed one.
    assert "http://alinea.localhost:5173/painel/definir-senha#token=" in email.text
    assert token_in(email.text) == token_in(out["link"])
    client.cookies.clear()
    signed_in = await choose_password(client, token_in(out["link"]))
    assert (signed_in.status_code, signed_in.json()["role"]) == (200, "member")


async def test_an_owner_can_invite_another_owner(client, owner, sent):
    response = await invite(client, owner, role="owner")
    assert response.json()["member"]["role"] == "owner"


async def test_the_team_lists_who_is_in_then_who_is_invited(client, owner, sent):
    await invite(client, owner, name="Zeca", email="zeca@alinea.example")
    team_now = (await client.get("/api/team", headers=owner)).json()
    assert [(m["email"], m["status"], m["me"]) for m in team_now["members"]] == [
        ("dona@alinea.example", "active", True),
        ("zeca@alinea.example", "invited", False),
    ]
    assert team_now["can_manage"] is True
    assert team_now["join_link"] == {"on": False, "expires_at": None}


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ({"email": "bia@alinea"}, "invalid_email"),
        ({"email": "bia..souza@alinea.example"}, "invalid_email"),
        ({"name": "   "}, "invalid_staff_name"),
        ({"name": "x" * 81}, "invalid_staff_name"),
    ],
)
async def test_a_bad_invite_is_refused_and_nothing_is_made(client, owner, sent, body, error):
    response = await invite(client, owner, **body)
    assert (response.status_code, response.json()["error"]) == (422, error)
    assert sent.emails == []
    assert len((await client.get("/api/team", headers=owner)).json()["members"]) == 1


async def test_someone_already_in_is_not_invited_again(client, owner, sent):
    response = await invite(client, owner, email="dona@alinea.example")
    assert response.status_code == 409
    assert response.json() == {"error": "already_staff", "conflict_name": "Ana"}
    assert sent.emails == []


async def test_inviting_a_pending_address_again_sends_a_new_link_and_the_old_one_stops(
    client, owner, sent
):
    first = (await invite(client, owner)).json()
    again = await invite(client, owner, name="Beatriz Souza", role="owner")
    assert again.status_code == 201
    assert again.json()["member"]["name"] == "Beatriz Souza"
    assert again.json()["member"]["role"] == "owner"
    client.cookies.clear()
    assert (await choose_password(client, token_in(first["link"]))).status_code == 404
    assert (await choose_password(client, token_in(again.json()["link"]))).status_code == 200


async def test_a_new_link_for_a_pending_invite_replaces_the_old(client, owner, sent):
    first = (await invite(client, owner)).json()
    member = first["member"]["id"]
    again = await client.post(f"/api/team/invites/{member}/link", headers=owner)
    assert again.status_code == 200
    assert len(sent.emails) == 2
    client.cookies.clear()
    assert (await choose_password(client, token_in(first["link"]))).status_code == 404
    assert (await choose_password(client, token_in(again.json()["link"]))).status_code == 200


async def test_a_cancelled_invite_takes_its_account_and_link_with_it(client, owner, sent):
    first = (await invite(client, owner)).json()
    member = first["member"]["id"]
    assert (await client.delete(f"/api/team/invites/{member}", headers=owner)).status_code == 204
    assert len((await client.get("/api/team", headers=owner)).json()["members"]) == 1
    client.cookies.clear()
    assert (await choose_password(client, token_in(first["link"]))).status_code == 404


async def test_only_pending_invites_can_be_cancelled_or_sent_again(client, owner, sent):
    team_now = (await client.get("/api/team", headers=owner)).json()
    me = team_now["members"][0]["id"]
    assert (await client.delete(f"/api/team/invites/{me}", headers=owner)).status_code == 409
    assert (await client.post(f"/api/team/invites/{me}/link", headers=owner)).status_code == 409
    unknown = "00000000-0000-0000-0000-000000000009"
    response = await client.delete(f"/api/team/invites/{unknown}", headers=owner)
    assert (response.status_code, response.json()["error"]) == (404, "not_an_invite")


async def test_when_the_email_cannot_go_the_invite_stands_and_says_so(client, owner, sent, caplog):
    sent.failing = True
    with caplog.at_level(logging.ERROR):
        response = await invite(client, owner)
    assert response.status_code == 201
    assert response.json()["emailed"] is False
    assert "invite email failed" in caplog.text and "tenant=alinea" in caplog.text
    # The link to copy still works.
    client.cookies.clear()
    assert (await choose_password(client, token_in(response.json()["link"]))).status_code == 200


async def test_members_see_the_team_but_only_owners_invite(client, owner, db_session, sent):
    member = await sign_in_as(client, db_session, "rui@alinea.example", Role.MEMBER)
    team_now = (await client.get("/api/team", headers=member)).json()
    assert team_now["can_manage"] is False
    for response in (
        await invite(client, member),
        await client.post("/api/team/join-link", headers=member),
        await client.delete("/api/team/join-link", headers=member),
    ):
        assert (response.status_code, response.json()["error"]) == (403, "owner_only")


async def test_inviting_needs_a_signed_in_request_with_its_csrf_token(client, owner, sent):
    assert (await invite(client, ALINEA)).status_code == 403
    client.cookies.clear()
    assert (await client.get("/api/team", headers=ALINEA)).status_code == 401


async def test_each_office_sees_only_its_own_team(client, owner, db_session, sent):
    await invite(client, owner)
    other = await sign_in_as(client, db_session, "rui@norte.example", Role.OWNER, NORTE, "norte")
    emails = [m["email"] for m in (await client.get("/api/team", headers=other)).json()["members"]]
    assert emails == ["rui@norte.example"]


# -- the shared link ---------------------------------------------------------------


async def turn_on(client, owner) -> str:
    response = await client.post("/api/team/join-link", headers=owner)
    assert response.status_code == 201
    return response.json()["link"]


async def join(client, token, host=ALINEA, **body):
    body = {
        "token": token,
        "name": "Caio Reis",
        "email": "caio@gmail.com",
        "password": "a good password",
    } | body
    return await client.post("/api/join", json=body, headers=host)


def csrf(response) -> dict:
    return ALINEA | {"X-CSRF-Token": response.json()["csrf_token"]}


async def test_whoever_opens_the_shared_link_chooses_a_password_and_confirms_with_a_code(
    client, owner, sent
):
    link = await turn_on(client, owner)
    assert link.startswith("http://alinea.localhost:5173/painel/entrar-na-equipe#token=")
    on = (await client.get("/api/team", headers=owner)).json()["join_link"]
    assert on["on"] is True and on["expires_at"]
    client.cookies.clear()
    token = token_in(link)
    checked = await client.post("/api/join/check", json={"token": token}, headers=ALINEA)
    assert checked.json() == {"office": "Alinea (dev)", "role": "member"}
    joined = await join(client, token, email=" Caio@Gmail.com ")
    assert joined.status_code == 201
    me = joined.json()
    assert (me["email"], me["role"], me["email_confirmed"]) == ("caio@gmail.com", "member", False)
    [email] = sent.emails
    assert email.to == "caio@gmail.com"
    code = code_in(email.text)
    assert code in email.subject
    assert "http://alinea.localhost:5173/painel/confirmar-email#token=" in email.text
    # Signed in, but nothing works until the email is confirmed.
    assert (await client.get("/api/me", headers=ALINEA)).json()["email_confirmed"] is False
    refused = await client.get("/api/team", headers=ALINEA)
    assert (refused.status_code, refused.json()["error"]) == (403, "email_unconfirmed")
    confirmed = await client.post("/api/me/email-code", json={"code": code}, headers=csrf(joined))
    assert (confirmed.status_code, confirmed.json()["email_confirmed"]) == (200, True)
    assert (await client.get("/api/team", headers=ALINEA)).status_code == 200


async def test_the_owner_sees_who_has_not_confirmed_yet(client, owner, sent):
    token = token_in(await turn_on(client, owner))
    owner_cookies = dict(client.cookies)
    client.cookies.clear()
    await join(client, token)
    client.cookies.clear()
    client.cookies.update(owner_cookies)
    team_now = (await client.get("/api/team", headers=owner)).json()
    assert [(m["email"], m["status"]) for m in team_now["members"]] == [
        ("dona@alinea.example", "active"),  # Ana
        ("caio@gmail.com", "unconfirmed"),
    ]


async def test_an_address_with_an_account_is_refused_and_nothing_is_sent(client, owner, sent):
    token = token_in(await turn_on(client, owner))
    await invite(client, owner, email="bia@alinea.example")  # a pending invite counts too
    sent.emails.clear()
    for address in ("dona@alinea.example", "bia@alinea.example"):
        response = await join(client, token, email=address)
        assert (response.status_code, response.json()) == (409, {"error": "account_exists"})
    assert sent.emails == []


async def test_a_new_shared_link_turns_the_old_one_off_and_off_means_off(client, owner, sent):
    old = token_in(await turn_on(client, owner))
    new = token_in(await turn_on(client, owner))
    assert (await join(client, old)).status_code == 404
    assert (await client.delete("/api/team/join-link", headers=owner)).status_code == 204
    response = await client.post("/api/join/check", json={"token": new}, headers=ALINEA)
    assert (response.status_code, response.json()["error"]) == (404, "join_link_invalid")
    assert (await join(client, new)).status_code == 404
    assert (await client.get("/api/team", headers=owner)).json()["join_link"]["on"] is False


async def test_a_shared_link_works_only_on_its_own_offices_address(client, owner, sent):
    token = token_in(await turn_on(client, owner))
    assert (await join(client, token, host=NORTE)).status_code == 404
    assert sent.emails == []


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ({"email": "caio@"}, "invalid_email"),
        ({"name": " "}, "invalid_staff_name"),
        ({"password": "short"}, "password_too_short"),
    ],
)
async def test_a_bad_join_is_refused_and_nothing_is_made(client, owner, sent, body, error):
    token = token_in(await turn_on(client, owner))
    response = await join(client, token, **body)
    assert (response.status_code, response.json()["error"]) == (422, error)
    assert sent.emails == []
    assert len((await client.get("/api/team", headers=owner)).json()["members"]) == 1


async def test_when_the_email_cannot_go_the_account_is_made_and_a_code_can_be_asked_again(
    client, owner, sent, caplog
):
    token = token_in(await turn_on(client, owner))
    client.cookies.clear()
    sent.failing = True
    with caplog.at_level(logging.ERROR):
        joined = await join(client, token)
    assert joined.status_code == 201
    assert "resend 500" in caplog.text and "/api/join" in caplog.text
    assert sent.emails == []


async def test_a_device_asking_again_and_again_must_wait(client, owner, sent):
    token = token_in(await turn_on(client, owner))
    for n in range(attempts.LIMIT):
        await join(client, token, email=f"pessoa{n}@gmail.com")
    response = await join(client, token, email="outra@gmail.com")
    assert (response.status_code, response.json()) == (429, {"error": "too_many_attempts"})


async def test_requests_for_one_address_wait_for_each_other(client, owner, sent):
    """Two at once for a new address must not both find no account and both make
    one: the second waits for the first's lock, which holds across connections."""
    token = token_in(await turn_on(client, owner))
    other = create_async_engine(TEST_DATABASE_URL)
    done = anyio.Event()
    answers = []

    async def request():
        answers.append((await join(client, token)).status_code)
        done.set()

    try:
        async with other.connect() as holder:
            async with holder.begin():
                await holder.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext('staff-email'), hashtext(:e))"),
                    {"e": "caio@gmail.com"},
                )
                async with anyio.create_task_group() as tasks:
                    tasks.start_soon(request)
                    await anyio.sleep(0.5)
                    assert not done.is_set()  # waiting for the lock
                    await holder.commit()  # let go
            await done.wait()
    finally:
        await other.dispose()
    assert answers == [201]
    assert (await join(client, token)).status_code == 409  # and again: it exists now


async def _waits_for(lock_sql: str, key: str, call) -> int:
    """Runs `call` while another connection holds the lock: it must wait, then answer."""
    other = create_async_engine(TEST_DATABASE_URL)
    done = anyio.Event()
    answers = []

    async def request():
        answers.append((await call()).status_code)
        done.set()

    try:
        async with other.connect() as holder:
            async with holder.begin():
                await holder.execute(text(lock_sql), {"k": key})
                async with anyio.create_task_group() as tasks:
                    tasks.start_soon(request)
                    await anyio.sleep(0.5)
                    assert not done.is_set()  # waiting for the lock
                    await holder.commit()
            await done.wait()
    finally:
        await other.dispose()
    return answers[0]


# Each test makes one locking request: the tests run inside one transaction
# (conftest), so a lock an earlier request took would be held until the test ends.


async def test_turning_the_shared_link_on_waits_for_another_change(client, db_session, owner, sent):
    office = str(await tenant_id(db_session, "alinea"))
    lock = "SELECT pg_advisory_xact_lock(hashtext('join-link'), hashtext(:k))"
    call = lambda: client.post("/api/team/join-link", headers=owner)  # noqa: E731
    assert await _waits_for(lock, office, call) == 201


async def test_turning_the_shared_link_off_waits_for_another_change(
    client, db_session, owner, sent
):
    office = str(await tenant_id(db_session, "alinea"))
    lock = "SELECT pg_advisory_xact_lock(hashtext('join-link'), hashtext(:k))"
    call = lambda: client.delete("/api/team/join-link", headers=owner)  # noqa: E731
    assert await _waits_for(lock, office, call) == 204


async def test_sending_an_invite_again_waits_for_another_on_the_same_address(
    client, db_session, owner, sent
):
    pending = await accounts.create_user(db_session, email="bia@alinea.example", name="Bia")
    lock = "SELECT pg_advisory_xact_lock(hashtext('staff-email'), hashtext(:k))"
    call = lambda: client.post(f"/api/team/invites/{pending.id}/link", headers=owner)  # noqa: E731
    assert await _waits_for(lock, "bia@alinea.example", call) == 200


async def test_a_shared_link_stops_working_after_24_hours(client, db_session, owner, sent):
    token = token_in(await turn_on(client, owner))
    await db_session.execute(
        text("UPDATE join_links SET created_at = now() - interval '24 hours 1 minute'")
    )
    response = await client.post("/api/join/check", json={"token": token}, headers=ALINEA)
    assert (response.status_code, response.json()["error"]) == (404, "join_link_invalid")
    assert (await join(client, token)).status_code == 404
    assert (await client.get("/api/team", headers=owner)).json()["join_link"]["on"] is False


async def test_an_account_that_came_in_meanwhile_is_never_deleted(client, db_session, owner, sent):
    """Its invite used between reading it and deleting it: the delete finds
    nothing to delete, and the account stays."""
    pending = await accounts.create_user(db_session, email="bia@alinea.example", name="Bia")
    await db_session.execute(
        text("UPDATE users SET password_hash = 'chosen' WHERE id = :u"), {"u": str(pending.id)}
    )
    assert await team._delete_pending(db_session, pending) is False
    still = await db_session.scalar(
        text("SELECT count(*) FROM users WHERE email = 'bia@alinea.example'")
    )
    assert still == 1


async def test_a_pending_check_reads_the_database_not_the_sessions_copy(db_session, owner):
    """After waiting for a lock, "still pending?" must see what changed meanwhile:
    the session's earlier copy of the account would still say pending."""
    pending = await accounts.create_user(db_session, email="bia@alinea.example", name="Bia")
    assert (await team._pending(db_session, pending.id)).password_hash is None
    await db_session.execute(
        text("UPDATE users SET password_hash = 'chosen' WHERE id = :u"), {"u": str(pending.id)}
    )
    with pytest.raises(ApiError) as refused:
        await team._pending(db_session, pending.id)
    assert refused.value.code == "not_an_invite"


# -- one-time owner links ---------------------------------------------------------


async def owner_token(db, **values):
    token = secrets.token_urlsafe(24)
    db.add(
        JoinLink(
            **(
                {
                    "token_hash": team._hash(token),
                    "role": Role.OWNER,
                    "single_use": True,
                    "expires_at": datetime.now(UTC) + timedelta(days=7),
                }
                | values
            )
        )
    )
    await db.flush()
    return token


async def test_owner_link_creates_an_owner_who_must_confirm_the_email(
    client, db_session, owner, sent
):
    token = await owner_token(db_session)
    client.cookies.clear()
    checked = await client.post("/api/join/check", json={"token": token}, headers=ALINEA)
    assert checked.json() == {"office": "Alinea (dev)", "role": "owner"}
    joined = await join(client, token)
    assert joined.status_code == 201
    assert (joined.json()["role"], joined.json()["email_confirmed"]) == ("owner", False)
    refused = await client.get("/api/team", headers=ALINEA)
    assert (refused.status_code, refused.json()["error"]) == (403, "email_unconfirmed")
    code = code_in(sent.emails[0].text)
    confirmed = await client.post("/api/me/email-code", json={"code": code}, headers=csrf(joined))
    assert confirmed.status_code == 200 and confirmed.json()["email_confirmed"] is True
    assert (await client.get("/api/team", headers=ALINEA)).json()["can_manage"] is True


async def test_owner_link_can_be_used_only_once(client, db_session, owner, sent):
    token = await owner_token(db_session)
    assert (await join(client, token)).status_code == 201
    again = await join(client, token, email="outra@example.com")
    assert (again.status_code, again.json()) == (404, {"error": "join_link_invalid"})
    checked = await client.post("/api/join/check", json={"token": token}, headers=ALINEA)
    assert checked.status_code == 404
    assert len(sent.emails) == 1


async def test_owner_link_uses_its_own_expiry_instead_of_24_hours(client, db_session, owner, sent):
    token = await owner_token(db_session, created_at=datetime.now(UTC) - timedelta(days=2))
    assert (
        await client.post("/api/join/check", json={"token": token}, headers=ALINEA)
    ).status_code == 200
    assert (await join(client, token)).status_code == 201


async def test_owner_link_is_invalid_after_its_expiry(client, db_session, owner, sent):
    token = await owner_token(db_session, expires_at=datetime.now(UTC) - timedelta(seconds=1))
    checked = await client.post("/api/join/check", json={"token": token}, headers=ALINEA)
    assert (checked.status_code, checked.json()) == (404, {"error": "join_link_invalid"})
    assert (await join(client, token)).status_code == 404
    assert sent.emails == []


async def test_owner_links_are_separate_from_the_shared_link(client, db_session, owner, sent):
    token = await owner_token(db_session)
    assert (await client.get("/api/team", headers=owner)).json()["join_link"] == {
        "on": False,
        "expires_at": None,
    }
    await turn_on(client, owner)
    member = token_in(await turn_on(client, owner))
    assert (await client.get("/api/team", headers=owner)).json()["join_link"]["on"] is True
    assert (await client.delete("/api/team/join-link", headers=owner)).status_code == 204
    assert (await client.get("/api/team", headers=owner)).json()["join_link"]["on"] is False
    assert (await join(client, member)).status_code == 404
    assert (await join(client, token)).status_code == 201


async def test_owner_link_rejects_another_tenant_and_revocation(client, db_session, owner, sent):
    token = await owner_token(db_session)
    assert (await join(client, token, host=NORTE)).status_code == 404
    await db_session.execute(text("UPDATE join_links SET revoked_at = now()"))
    assert (await join(client, token)).status_code == 404
    assert sent.emails == []


async def test_invalid_signup_does_not_spend_the_owner_link(client, db_session, owner, sent):
    token = await owner_token(db_session)
    assert (await join(client, token, password="short")).status_code == 422
    exists = await join(client, token, email="dona@alinea.example")
    assert (exists.status_code, exists.json()) == (409, {"error": "account_exists"})
    assert (await join(client, token)).status_code == 201


async def test_failed_account_transaction_does_not_spend_the_owner_link(
    client,
    db_session,
    owner,
    sent,
    monkeypatch,
):
    token = await owner_token(db_session)

    async def fail(*args):
        raise RuntimeError("confirmation creation failed")

    with monkeypatch.context() as patch:
        patch.setattr(email_confirmation, "new_code", fail)
        assert (await join(client, token)).status_code == 500
    assert (await join(client, token)).status_code == 201
    assert len(sent.emails) == 1


async def test_concurrent_owner_joins_create_only_one_account(test_database_url, sent):
    """Like _waits_for, hold a real database lock before starting the requests.
    Separate committed connections exercise PostgreSQL's conditional update, not
    the per-test savepoint shared by the ordinary API fixtures.
    """
    owner_engine = create_async_engine(test_database_url)
    app_engine = create_async_engine(make_url(test_database_url).set(username=RUNTIME_ROLE))
    application = create_app(Settings(environment="test", database_url=test_database_url))
    application.state.sessionmaker = async_sessionmaker(app_engine, expire_on_commit=False)
    host = {"host": "owner-race.localhost"}
    tenant = Tenant(slug="owner-race", name="Escritório Horizonte")
    answers = []

    async def request(email):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=application), base_url="http://testserver"
        ) as visitor:
            answers.append(await join(visitor, token, host=host, email=email))

    try:
        async with AsyncSession(owner_engine, expire_on_commit=False) as setup:
            setup.add(tenant)
            await setup.flush()
            setup.add(TenantDomain(tenant_id=tenant.id, hostname=host["host"], is_primary=True))
            await setup.commit()
            scope_to_tenant(setup.sync_session, tenant.id)
            token = await owner_token(setup)
            await setup.commit()
        async with owner_engine.connect() as holder:
            async with holder.begin():
                await holder.execute(
                    text("SELECT id FROM join_links WHERE token_hash = :hash FOR UPDATE"),
                    {"hash": team._hash(token)},
                )
                async with anyio.create_task_group() as tasks:
                    tasks.start_soon(request, "ana@example.com")
                    tasks.start_soon(request, "bia@example.com")
                    async with owner_engine.connect() as observer:
                        with anyio.fail_after(10):
                            while True:
                                waiting = await observer.scalar(
                                    text(
                                        "SELECT count(*) FROM pg_stat_activity "
                                        "WHERE datname = current_database() "
                                        "AND wait_event_type = 'Lock' "
                                        "AND query LIKE 'UPDATE join_links%'"
                                    )
                                )
                                await observer.commit()  # fresh activity snapshot
                                if waiting == 2 or answers:
                                    break
                                await anyio.sleep(0.02)
                    assert waiting == 2 and answers == []
                    await holder.commit()
        assert sorted(answer.status_code for answer in answers) == [201, 404]
        rejected = next(answer for answer in answers if answer.status_code == 404)
        assert rejected.json() == {"error": "join_link_invalid"}
        assert len(sent.emails) == 1
        async with AsyncSession(owner_engine) as check:
            users = list(await check.scalars(select(User).where(User.tenant_id == tenant.id)))
            assert len(users) == 1 and users[0].role is Role.OWNER
            assert await check.scalar(
                select(JoinLink.used_at).where(JoinLink.tenant_id == tenant.id)
            )
    finally:
        async with owner_engine.begin() as cleanup:
            # Tenant-owned foreign keys deliberately don't cascade from the registry.
            await cleanup.execute(delete(User).where(User.tenant_id == tenant.id))
            await cleanup.execute(delete(JoinLink).where(JoinLink.tenant_id == tenant.id))
            await cleanup.execute(delete(Tenant).where(Tenant.id == tenant.id))
        await app_engine.dispose()
        await owner_engine.dispose()
