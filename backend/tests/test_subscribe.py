"""Clients add themselves to a project's emails (A32, 20 Oct 2026): only a
confirmed address is listed."""

import re

import pytest
from sqlalchemy import select, text

from backend.notifications import subscribe as tokens
from backend.notifications.email import EmailError
from backend.notifications.models import ProjectRecipient
from backend.tests import test_office
from backend.tests.test_office import ALINEA, NORTE, tenant_id
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


def link_in(email) -> str:
    return re.search(r"(/api/emails/subscribe/[^\s\"<]+)", email.text).group(1)


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


async def test_an_address_is_listed_only_once_its_link_is_confirmed(client, db_session, sent):
    assert (await ask(client, " Ana@Gmail.com ")).status_code == 202
    [email] = sent.emails
    assert email.to == "ana@gmail.com"
    assert "http://alinea.localhost:5173/api/emails/subscribe/" in email.text
    assert "ana@gmail.com" not in link_in(email)  # the address stays out of the address bar
    assert "ana@gmail.com" not in await listed(db_session)
    # Opening the link only asks (mail scanners open links).
    opened = await client.get(link_in(email), headers=ALINEA)
    assert opened.status_code == 200 and "<form" in opened.text
    assert "ana@gmail.com" not in await listed(db_session)
    confirmed = await client.post(link_in(email), headers=ALINEA)
    assert confirmed.status_code == 200
    assert (await listed(db_session))["ana@gmail.com"] == "subscribed"
    # Twice changes nothing.
    assert (await client.post(link_in(email), headers=ALINEA)).status_code == 200


async def test_an_address_already_listed_gets_the_same_answer_and_no_email(
    client, db_session, sent
):
    first = await ask(client, "ana@gmail.com")
    await client.post(link_in(sent.emails[0]), headers=ALINEA)
    again = await ask(client, "ana@gmail.com")
    assert (first.status_code, again.status_code) == (202, 202)
    assert len(sent.emails) == 1


async def test_a_client_who_unsubscribed_can_turn_the_emails_back_on(client, db_session, sent):
    await ask(client, "ana@gmail.com")
    await client.post(link_in(sent.emails[0]), headers=ALINEA)
    await db_session.execute(text("UPDATE project_recipients SET status = 'unsubscribed'"))
    await ask(client, "ana@gmail.com")
    assert len(sent.emails) == 2
    await client.post(link_in(sent.emails[1]), headers=ALINEA)
    assert (await listed(db_session))["ana@gmail.com"] == "subscribed"


async def test_a_bad_address_is_refused(client, sent):
    response = await ask(client, "ana@gmail")
    assert (response.status_code, response.json()["error"]) == (422, "invalid_email")
    assert sent.emails == []


async def test_a_locked_or_unknown_page_takes_no_subscriptions(client, db_session, sent):
    await db_session.execute(
        text("UPDATE projects SET access_mode = 'password', password_hash = 'x' WHERE id = :p"),
        {"p": str(await project_id(db_session, "casa-jardim"))},
    )
    assert (await ask(client, "ana@gmail.com")).status_code == 403
    assert (await ask(client, "ana@gmail.com", slug="nao-existe")).status_code == 404
    assert sent.emails == []


async def test_an_archived_project_takes_no_subscriptions(client, db_session, sent):
    await db_session.execute(
        text("UPDATE projects SET status = 'archived', archived_from = 'active' WHERE id = :p"),
        {"p": str(await project_id(db_session, "casa-jardim"))},
    )
    response = await ask(client, "ana@gmail.com")
    assert (response.status_code, response.json()["error"]) == (409, "project_archived")


async def test_a_link_works_only_on_its_offices_address_and_while_it_lasts(
    app, client, db_session, sent, monkeypatch
):
    await ask(client, "ana@gmail.com")
    link = link_in(sent.emails[0])
    assert (await client.post(link, headers=NORTE)).status_code == 404
    assert (
        await client.post(link.replace("subscribe/", "subscribe/x"), headers=ALINEA)
    ).status_code == 404
    monkeypatch.setattr(tokens.time, "time", lambda: 10**10)  # far past its 7 days
    assert (await client.post(link, headers=ALINEA)).status_code == 404
    assert "ana@gmail.com" not in await listed(db_session)


async def test_a_full_list_takes_no_more(client, db_session, sent):
    pid = await project_id(db_session, "casa-jardim")
    for n in range(20):
        db_session.add(ProjectRecipient(project_id=pid, email=f"p{n}@x.com"))
    await db_session.flush()
    await ask(client, "ana@gmail.com")
    response = await client.post(link_in(sent.emails[0]), headers=ALINEA)
    assert response.status_code == 409
    assert "ana@gmail.com" not in await listed(db_session)


async def test_a_device_asking_again_and_again_must_wait(client, sent):
    for n in range(attempts.LIMIT):
        await ask(client, f"p{n}@gmail.com")
    response = await ask(client, "outra@gmail.com")
    assert (response.status_code, response.json()) == (429, {"error": "too_many_attempts"})
