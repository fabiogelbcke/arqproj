"""Configurações → Equipe (A36): owners invite staff, personally or with a shared
link whose joiners still prove their email."""

import logging
import re

import anyio
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.commands.seed import seed
from backend.identity import accounts
from backend.identity.models import Role
from backend.notifications.email import EmailError
from backend.tests.conftest import TEST_DATABASE_URL
from backend.tests.test_office import ALINEA, NORTE, sign_in_as, tenant_id
from backend.web import attempts, team

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
    monkeypatch.setattr(team, "JOIN_ANSWER_AT", 0)  # fast tests
    yield box
    attempts.reset()


@pytest.fixture
async def owner(client, db_session):
    await seed(db_session)
    return await sign_in_as(client, db_session, "dona@alinea.example", Role.OWNER)


def token_in(text: str) -> str:
    return re.search(r"#token=([\w-]+)", text).group(1)


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
    assert team_now["join_link"] == {"on": False, "made_at": None}


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
    body = {"token": token, "name": "Caio Reis", "email": "caio@gmail.com"} | body
    return await client.post("/api/join", json=body, headers=host)


async def test_whoever_opens_the_shared_link_is_emailed_a_link_and_joins_as_a_member(
    client, owner, sent
):
    link = await turn_on(client, owner)
    assert link.startswith("http://alinea.localhost:5173/painel/entrar-na-equipe#token=")
    on = (await client.get("/api/team", headers=owner)).json()["join_link"]
    assert on["on"] is True and on["made_at"]
    client.cookies.clear()
    token = token_in(link)
    checked = await client.post("/api/join/check", json={"token": token}, headers=ALINEA)
    assert checked.json() == {"office": "Alinea (dev)"}
    assert (await join(client, token, email=" Caio@Gmail.com ")).status_code == 202
    [email] = sent.emails
    assert email.to == "caio@gmail.com"
    # Not in until they use the emailed link: the email is proven theirs.
    assert "http://alinea.localhost:5173/painel/definir-senha#token=" in email.text
    signed_in = await choose_password(client, token_in(email.text))
    assert (signed_in.status_code, signed_in.json()["role"]) == (200, "member")


async def test_the_answer_is_the_same_for_an_address_already_in_and_nothing_is_sent(
    client, owner, sent
):
    token = token_in(await turn_on(client, owner))
    response = await join(client, token, email="dona@alinea.example")
    assert response.status_code == 202
    assert sent.emails == []


async def test_asking_again_soon_sends_no_second_email(client, owner, sent):
    token = token_in(await turn_on(client, owner))
    assert (await join(client, token)).status_code == 202
    assert (await join(client, token)).status_code == 202
    assert len(sent.emails) == 1


async def test_a_new_shared_link_turns_the_old_one_off_and_off_means_off(client, owner, sent):
    old = token_in(await turn_on(client, owner))
    new = token_in(await turn_on(client, owner))
    assert (await join(client, old)).status_code == 404
    assert (await join(client, new)).status_code == 202
    assert (await client.delete("/api/team/join-link", headers=owner)).status_code == 204
    response = await client.post("/api/join/check", json={"token": new}, headers=ALINEA)
    assert (response.status_code, response.json()["error"]) == (404, "join_link_invalid")
    assert (await join(client, new)).status_code == 404
    assert (await client.get("/api/team", headers=owner)).json()["join_link"]["on"] is False


async def test_a_shared_link_works_only_on_its_own_offices_address(client, owner, sent):
    token = token_in(await turn_on(client, owner))
    assert (await join(client, token, host=NORTE)).status_code == 404
    assert sent.emails == []


async def test_a_bad_join_is_refused(client, owner, sent):
    token = token_in(await turn_on(client, owner))
    response = await join(client, token, email="caio@")
    assert (response.status_code, response.json()["error"]) == (422, "invalid_email")
    response = await join(client, token, name=" ")
    assert (response.status_code, response.json()["error"]) == (422, "invalid_staff_name")
    assert sent.emails == []


async def test_a_device_asking_again_and_again_must_wait(client, owner, sent):
    token = token_in(await turn_on(client, owner))
    for n in range(attempts.LIMIT):
        await join(client, token, email=f"pessoa{n}@gmail.com")
    response = await join(client, token, email="outra@gmail.com")
    assert (response.status_code, response.json()) == (429, {"error": "too_many_attempts"})


async def test_requests_for_one_address_wait_for_each_other(client, owner, sent):
    """Two at once for a new address must not both find no account and both make
    one (the second would fail, and say the account exists): the second waits for
    the first's lock, which holds across connections."""
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
    assert answers == [202]
    assert (await join(client, token)).status_code == 202  # and again: the same answer


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
