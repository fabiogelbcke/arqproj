"""Someone who joined through the office's shared link confirms their email (A36,
revised 25 Oct 2026): a code typed where they signed up, or the email's link."""

import logging

import pytest
from sqlalchemy import text

from backend.commands.seed import seed
from backend.identity import links
from backend.identity.models import Role
from backend.tests.test_office import ALINEA, sign_in_as
from backend.tests.test_team import Sent, code_in, csrf, join, token_in, turn_on
from backend.web import attempts, auth, email_confirmation, team

pytestmark = pytest.mark.anyio


@pytest.fixture
async def sent(monkeypatch):
    attempts.reset()
    box = Sent()
    for module in (team, email_confirmation, auth):
        monkeypatch.setattr(module, "sender_for", lambda settings, http: box)
    monkeypatch.setattr(auth, "RESET_ANSWER_AT", 0)
    yield box
    attempts.reset()


@pytest.fixture
async def owner(client, db_session):
    await seed(db_session)
    return await sign_in_as(client, db_session, "dona@alinea.example", Role.OWNER)


@pytest.fixture
async def joined(client, owner, sent):
    """Caio, just joined: signed in, unconfirmed, his code emailed."""
    token = token_in(await turn_on(client, owner))
    client.cookies.clear()
    response = await join(client, token)
    assert response.status_code == 201
    return csrf(response)


async def enter(client, headers, code):
    return await client.post("/api/me/email-code", json={"code": code}, headers=headers)


async def resend(client, headers):
    return await client.post("/api/me/email-code/resend", headers=headers)


async def make_resend_due(db_session):
    await db_session.execute(
        text("UPDATE password_links SET created_at = now() - interval '3 minutes'")
    )


async def test_until_confirmed_only_confirming_works(client, joined, sent):
    for method, path in (
        ("GET", "/api/team"),
        ("GET", "/api/projects"),
        ("GET", "/api/office"),
        ("POST", "/api/me/tour-seen"),
    ):
        response = await client.request(method, path, headers=joined)
        assert (response.status_code, response.json()["error"]) == (403, "email_unconfirmed")
    assert (await client.get("/api/me", headers=ALINEA)).status_code == 200
    assert (await client.delete("/api/session", headers=joined)).status_code == 204


async def test_signing_in_again_brings_back_the_unconfirmed_account(client, joined, sent):
    await client.delete("/api/session", headers=joined)
    again = await client.post(
        "/api/session",
        json={"email": "caio@gmail.com", "password": "a good password"},
        headers=ALINEA,
    )
    assert (again.status_code, again.json()["email_confirmed"]) == (200, False)
    # The code from before still works in the new session.
    confirmed = await enter(client, csrf(again), code_in(sent.emails[0].text))
    assert confirmed.json()["email_confirmed"] is True


async def test_a_wrong_code_is_refused_and_enough_of_them_use_it_up(client, joined, sent):
    code = code_in(sent.emails[0].text)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(links.CODE_TRIES - 1):
        response = await enter(client, joined, wrong)
        assert (response.status_code, response.json()["error"]) == (422, "email_code_wrong")
    last = await enter(client, joined, wrong)
    assert (last.status_code, last.json()["error"]) == (410, "email_code_expired")
    attempts.reset()  # only the code's own count left to stop the right one
    late = await enter(client, joined, code)
    assert (late.status_code, late.json()["error"]) == (410, "email_code_expired")


async def test_wrong_codes_count_per_account_across_new_codes(
    client,
    db_session,
    joined,
    sent,
):
    for _ in range(links.CODE_TRIES):
        await enter(client, joined, "000000")
    await make_resend_due(db_session)
    assert (await resend(client, joined)).status_code == 204
    response = await enter(client, joined, code_in(sent.emails[-1].text))
    assert (response.status_code, response.json()["error"]) == (429, "too_many_attempts")


async def test_a_new_code_waits_two_minutes_and_replaces_the_old(
    client,
    db_session,
    joined,
    sent,
):
    first = code_in(sent.emails[0].text)
    soon = await resend(client, joined)
    assert (soon.status_code, soon.json()["error"]) == (429, "email_code_recent")
    await make_resend_due(db_session)
    assert (await resend(client, joined)).status_code == 204
    second = code_in(sent.emails[1].text)
    assert sent.emails[1].to == "caio@gmail.com"
    if first != second:
        old = await enter(client, joined, first)
        assert old.json()["error"] == "email_code_wrong"  # replaced
    assert (await enter(client, joined, second)).json()["email_confirmed"] is True


async def test_when_a_new_code_cannot_go_they_are_told(
    client,
    db_session,
    joined,
    sent,
    caplog,
):
    await make_resend_due(db_session)
    sent.failing = True
    with caplog.at_level(logging.ERROR):
        response = await resend(client, joined)
    assert (response.status_code, response.json()) == (503, {"error": "email_not_sent"})
    assert "resend 500" in caplog.text


async def test_a_mistyped_address_is_corrected_and_the_code_goes_there(client, joined, sent):
    old_code = code_in(sent.emails[0].text)
    corrected = await client.put(
        "/api/me/email", json={"email": " Caio@Hotmail.com "}, headers=joined
    )
    assert (corrected.status_code, corrected.json()["email"]) == (200, "caio@hotmail.com")
    assert corrected.json()["email_confirmed"] is False
    assert sent.emails[-1].to == "caio@hotmail.com"
    new_code = code_in(sent.emails[-1].text)
    if old_code != new_code:
        assert (await enter(client, joined, old_code)).json()["error"] == "email_code_wrong"
    assert (await enter(client, joined, new_code)).json()["email"] == "caio@hotmail.com"


@pytest.mark.parametrize(
    ("address", "status", "error"),
    [
        ("dona@alinea.example", 409, "account_exists"),
        ("caio@", 422, "invalid_email"),
    ],
)
async def test_an_address_is_not_corrected_to_one_taken_or_invalid(
    client,
    joined,
    sent,
    address,
    status,
    error,
):
    response = await client.put("/api/me/email", json={"email": address}, headers=joined)
    assert (response.status_code, response.json()["error"]) == (status, error)
    assert len(sent.emails) == 1


async def test_a_confirmed_account_has_nothing_to_confirm_or_correct(client, joined, sent):
    await enter(client, joined, code_in(sent.emails[0].text))
    for response in (
        await enter(client, joined, "123456"),
        await resend(client, joined),
        await client.put("/api/me/email", json={"email": "x@gmail.com"}, headers=joined),
    ):
        assert (response.status_code, response.json()["error"]) == (409, "already_confirmed")


async def test_the_emails_link_confirms_wherever_it_is_opened(client, joined, sent):
    token = token_in(sent.emails[0].text)
    elsewhere = await client.post("/api/email-confirmation", json={"token": token}, headers=ALINEA)
    assert elsewhere.status_code == 204
    assert (await client.get("/api/me", headers=ALINEA)).json()["email_confirmed"] is True
    again = await client.post("/api/email-confirmation", json={"token": token}, headers=ALINEA)
    assert (again.status_code, again.json()["error"]) == (404, "link_invalid")


async def test_a_confirmation_link_never_sets_a_password_nor_a_password_link_confirms(
    client,
    owner,
    sent,
):
    invited = await client.post(
        "/api/team/invites", json={"name": "Bia", "email": "bia@alinea.example"}, headers=owner
    )
    invite_token = token_in(invited.json()["link"])
    token = token_in(await turn_on(client, owner))
    client.cookies.clear()
    await join(client, token)
    confirm_token = token_in(sent.emails[-1].text)
    for path, body in (
        ("/api/password-link", {"token": confirm_token}),
        ("/api/password", {"token": confirm_token, "password": "another password"}),
        ("/api/email-confirmation", {"token": invite_token}),
    ):
        response = await client.post(path, json=body, headers=ALINEA)
        assert (response.status_code, response.json()["error"]) == (404, "link_invalid")


async def test_a_reset_link_confirms_the_email_too(client, joined, sent):
    """Forgot the password before confirming: the reset link came to the inbox."""
    await client.post("/api/password-reset", json={"email": "caio@gmail.com"}, headers=ALINEA)
    reset = sent.emails[-1]
    assert "definir-senha" in reset.text
    chosen = await client.post(
        "/api/password",
        json={"token": token_in(reset.text), "password": "a new password"},
        headers=ALINEA,
    )
    assert chosen.json()["email_confirmed"] is True
