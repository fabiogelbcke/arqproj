""" "Esqueceu a senha?": a link by email to choose a new password, with nothing
saying whether an account exists."""

import logging
import re
import time

import anyio
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.commands.seed import seed
from backend.identity import accounts
from backend.notifications.email import EmailError
from backend.tenancy.models import Tenant
from backend.tests.conftest import TEST_DATABASE_URL
from backend.web import attempts, auth

pytestmark = pytest.mark.anyio

ALINEA = {"host": "alinea.localhost"}


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
async def sent(db_session, monkeypatch):
    await seed(db_session)
    for slug, email in (("alinea", "ana@alinea.example"), ("norte", "rui@norte.example")):
        tenant = await db_session.scalar(select(Tenant.id).where(Tenant.slug == slug))
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)}
        )
        await accounts.create_user(
            db_session, email=email, name="Ana Lima", password="old password"
        )
    attempts.reset()
    box = Sent()
    monkeypatch.setattr(auth, "sender_for", lambda settings, http: box)
    monkeypatch.setattr(auth, "RESET_ANSWER_AT", 0)  # fast tests; its own test below
    yield box
    attempts.reset()


async def ask(client, email, headers=ALINEA):
    return await client.post("/api/password-reset", json={"email": email}, headers=headers)


def token_in(email) -> str:
    return re.search(r"#token=([\w-]+)", email.text).group(1)


async def test_an_account_gets_a_link_on_its_offices_address_that_sets_a_new_password(client, sent):
    response = await ask(client, "  Ana@Alinea.example ")
    assert response.status_code == 204
    [email] = sent.emails
    assert email.to == "ana@alinea.example"
    assert "Olá, Ana." in email.text
    assert "http://alinea.localhost:5173/painel/definir-senha#token=" in email.text
    chosen = await client.post(
        "/api/password", json={"token": token_in(email), "password": "a new one!"}, headers=ALINEA
    )
    assert chosen.status_code == 200
    signed_in = await client.post(
        "/api/session",
        json={"email": "ana@alinea.example", "password": "a new one!"},
        headers=ALINEA,
    )
    assert signed_in.status_code == 200


async def test_the_answer_is_the_same_without_an_account(client, sent):
    for email in ("nobody@alinea.example", "rui@norte.example"):  # none here, or another office's
        assert (await ask(client, email)).status_code == 204
    assert sent.emails == []


async def test_no_answer_comes_sooner_without_an_account(client, sent, monkeypatch):
    monkeypatch.setattr(auth, "RESET_ANSWER_AT", 0.3)
    for email in ("nobody@alinea.example", "ana@alinea.example"):
        started = time.monotonic()
        await ask(client, email)
        assert time.monotonic() - started >= 0.3


async def test_the_link_never_takes_its_address_from_the_request(client, sent):
    headers = {**ALINEA, "x-forwarded-host": "evil.example", "forwarded": "host=evil.example"}
    await ask(client, "ana@alinea.example", headers)
    assert "evil" not in sent.emails[0].text
    assert "http://alinea.localhost:5173/" in sent.emails[0].text


async def test_one_email_every_few_minutes_and_the_first_link_still_works(client, sent):
    await ask(client, "ana@alinea.example")
    await ask(client, "ana@alinea.example")
    assert len(sent.emails) == 1
    chosen = await client.post(
        "/api/password",
        json={"token": token_in(sent.emails[0]), "password": "a new one!"},
        headers=ALINEA,
    )
    assert chosen.status_code == 200


async def test_a_link_used_at_once_still_counts_toward_the_wait(client, sent):
    await ask(client, "ana@alinea.example")
    await client.post(
        "/api/password",
        json={"token": token_in(sent.emails[0]), "password": "a new one!"},
        headers=ALINEA,
    )
    await ask(client, "ana@alinea.example")
    assert len(sent.emails) == 1


async def test_requests_for_one_account_wait_for_each_other(client, sent, db_session):
    """Two at once must not both find no recent link and both send: the second
    waits for the first's lock, which holds across connections."""
    user = await db_session.scalar(text("SELECT id FROM users WHERE email = 'ana@alinea.example'"))
    other = create_async_engine(TEST_DATABASE_URL)
    done = anyio.Event()

    async def request():
        await ask(client, "ana@alinea.example")
        done.set()

    try:
        async with other.connect() as holder:
            async with holder.begin():
                await holder.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext('password-reset'), hashtext(:u))"),
                    {"u": str(user)},
                )
                async with anyio.create_task_group() as tasks:
                    tasks.start_soon(request)
                    await anyio.sleep(0.5)
                    assert not done.is_set()  # waiting for the lock
                    await holder.commit()  # let go
            await done.wait()
    finally:
        await other.dispose()
    assert len(sent.emails) == 1


async def test_a_device_asking_again_and_again_must_wait(client, sent):
    for _ in range(attempts.LIMIT):
        assert (await ask(client, "nobody@alinea.example")).status_code == 204
    response = await ask(client, "ana@alinea.example")
    assert (response.status_code, response.json()) == (429, {"error": "too_many_attempts"})
    assert sent.emails == []


async def test_a_failed_send_is_logged_and_still_says_nothing(client, sent, caplog):
    sent.failing = True
    with caplog.at_level(logging.ERROR):
        assert (await ask(client, "ana@alinea.example")).status_code == 204
    assert "password reset email failed" in caplog.text
    assert "tenant=alinea" in caplog.text
