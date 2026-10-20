"""Clients sign themselves up for a project's emails (A32, 20 Oct 2026): listed at
once, and welcomed with a link to stop them."""

import re

import anyio
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.notifications.email import EmailError
from backend.notifications.models import ProjectRecipient
from backend.tests import test_office
from backend.tests.conftest import TEST_DATABASE_URL
from backend.tests.test_office import ALINEA, tenant_id
from backend.tests.test_pages import project_id
from backend.web import attempts, subscribe

pytestmark = pytest.mark.anyio

owner = test_office.owner  # fixture: seeds the offices


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
async def sent(client, owner, monkeypatch):
    client.cookies.clear()  # a visitor
    attempts.reset()
    box = Sent()
    monkeypatch.setattr(subscribe, "sender_for", lambda settings, http: box)
    yield box
    attempts.reset()


async def ask(client, email, slug="casa-jardim", host=ALINEA):
    return await client.post(f"/api/pages/{slug}/subscribe", json={"email": email}, headers=host)


def stop_link_in(email) -> str:
    return re.search(r"(/api/emails/unsubscribe/[^\s\"<]+)", email.text).group(1)


async def listed(db, slug="casa-jardim"):
    pid = await project_id(db, slug)
    office = str(await tenant_id(db, "alinea"))
    await db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": office})
    return {
        r.email: r.status.value
        for r in await db.scalars(
            select(ProjectRecipient).where(ProjectRecipient.project_id == pid)
        )
    }


async def test_a_client_is_signed_up_at_once_and_welcomed_with_a_way_to_stop(
    client, db_session, sent
):
    assert (await ask(client, " Ana@Gmail.com ")).status_code == 204
    assert (await listed(db_session))["ana@gmail.com"] == "subscribed"
    [email] = sent.emails
    assert email.to == "ana@gmail.com"
    assert "http://alinea.localhost:5173/casa-jardim" in email.text  # the project's page
    assert email.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    # "Não foi você?": the unsubscribe link every update has.
    stopped = await client.post(stop_link_in(email), headers=ALINEA)
    assert stopped.status_code == 200
    assert (await listed(db_session))["ana@gmail.com"] == "unsubscribed"


async def test_an_address_already_in_gets_the_same_answer_and_no_second_email(
    client, db_session, sent
):
    assert (await ask(client, "ana@gmail.com")).status_code == 204
    assert (await ask(client, "ana@gmail.com")).status_code == 204
    assert len(sent.emails) == 1


async def test_a_client_who_unsubscribed_can_sign_up_again(client, db_session, sent):
    await ask(client, "ana@gmail.com")
    await client.post(stop_link_in(sent.emails[0]), headers=ALINEA)
    assert (await ask(client, "ana@gmail.com")).status_code == 204
    assert (await listed(db_session))["ana@gmail.com"] == "subscribed"
    assert len(sent.emails) == 2


async def test_a_bad_address_is_refused(client, db_session, sent):
    response = await ask(client, "ana@gmail")
    assert (response.status_code, response.json()["error"]) == (422, "invalid_email")
    assert sent.emails == [] and await listed(db_session) == {}


async def test_a_locked_or_unknown_page_takes_no_sign_ups(client, db_session, sent):
    await db_session.execute(
        text("UPDATE projects SET access_mode = 'password', password_hash = 'x' WHERE id = :p"),
        {"p": str(await project_id(db_session, "casa-jardim"))},
    )
    assert (await ask(client, "ana@gmail.com")).status_code == 403
    assert (await ask(client, "ana@gmail.com", slug="nao-existe")).status_code == 404
    assert sent.emails == []


async def test_an_archived_project_takes_no_sign_ups(client, db_session, sent):
    await db_session.execute(
        text("UPDATE projects SET status = 'archived', archived_from = 'active' WHERE id = :p"),
        {"p": str(await project_id(db_session, "casa-jardim"))},
    )
    response = await ask(client, "ana@gmail.com")
    assert (response.status_code, response.json()["error"]) == (409, "project_archived")


async def test_a_full_list_takes_no_more(client, db_session, sent):
    pid = await project_id(db_session, "casa-jardim")
    for n in range(20):
        db_session.add(ProjectRecipient(project_id=pid, email=f"p{n}@x.com"))
    await db_session.flush()
    response = await ask(client, "ana@gmail.com")
    assert (response.status_code, response.json()["error"]) == (409, "recipients_full")
    assert "ana@gmail.com" not in await listed(db_session) and sent.emails == []


async def test_sign_ups_for_one_project_wait_for_each_other(client, db_session, sent):
    """Two at once must not both find room, or both insert: the second waits for
    the first's lock, which holds across connections."""
    pid = str(await project_id(db_session, "casa-jardim"))
    other = create_async_engine(TEST_DATABASE_URL)
    done = anyio.Event()
    answers = []

    async def request():
        answers.append((await ask(client, "ana@gmail.com")).status_code)
        done.set()

    try:
        async with other.connect() as holder:
            async with holder.begin():
                await holder.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext('recipients'), hashtext(:p))"),
                    {"p": pid},
                )
                async with anyio.create_task_group() as tasks:
                    tasks.start_soon(request)
                    await anyio.sleep(0.5)
                    assert not done.is_set()  # waiting for the lock
                    await holder.commit()
            await done.wait()
    finally:
        await other.dispose()
    assert answers == [204]


async def test_a_device_asking_again_and_again_must_wait(client, sent):
    for n in range(attempts.LIMIT):
        await ask(client, f"p{n}@gmail.com")
    response = await ask(client, "outra@gmail.com")
    assert (response.status_code, response.json()) == (429, {"error": "too_many_attempts"})
