"""A staff member's own account: "Minha conta" (backend/web/account.py)."""

import pytest

from backend.identity.models import Role
from backend.tests import test_office
from backend.tests.test_office import ALINEA, NORTE, sign_in_as
from backend.web import account, attempts, auth

owner = test_office.owner  # fixtures

pytestmark = pytest.mark.anyio

PASSWORD = "a good password"  # sign_in_as's


@pytest.fixture(autouse=True)
def fast_and_fresh(monkeypatch):
    monkeypatch.setattr(account, "FAILED_LOGIN_DELAY", 0)
    attempts.reset()
    yield
    attempts.reset()


async def change(client, headers, current=PASSWORD, password="uma senha nova e boa"):
    return await client.post(
        "/api/me/password", json={"current": current, "password": password}, headers=headers
    )


async def test_a_staff_member_renames_themselves(client, owner):
    response = await client.patch("/api/me", json={"name": "  Ana   Paula  "}, headers=owner)
    assert response.status_code == 204, response.text
    assert (await client.get("/api/me", headers=ALINEA)).json()["name"] == "Ana Paula"


@pytest.mark.parametrize("name", ["   ", "x" * 81])
async def test_a_name_must_be_one_people_can_read(client, owner, name):
    response = await client.patch("/api/me", json={"name": name}, headers=owner)
    assert (response.status_code, response.json()["error"]) == (422, "invalid_staff_name")


async def test_changing_the_password_ends_every_other_sign_in_and_keeps_this_one(client, owner):
    before = client.cookies.get(auth.COOKIE)
    response = await change(client, owner)
    assert response.status_code == 200, response.text
    fresh = {**ALINEA, auth.CSRF_HEADER: response.json()["csrf_token"]}
    # This device carries on, on a new session.
    assert client.cookies.get(auth.COOKIE) != before
    assert (await client.get("/api/me", headers=fresh)).status_code == 200
    # The old cookie (another device, or a stolen one) no longer works.
    client.cookies.set(auth.COOKIE, before)
    assert (await client.get("/api/me", headers=ALINEA)).status_code == 401
    # And only the new password signs in.
    client.cookies.clear()
    old = await client.post(
        "/api/session", json={"email": "dona@alinea.example", "password": PASSWORD}, headers=ALINEA
    )
    assert old.status_code == 401
    new = await client.post(
        "/api/session",
        json={"email": "dona@alinea.example", "password": "uma senha nova e boa"},
        headers=ALINEA,
    )
    assert new.status_code == 200


async def test_the_current_password_must_be_right(client, owner):
    response = await change(client, owner, current="not it")
    assert (response.status_code, response.json()["error"]) == (422, "current_password_wrong")
    assert (await client.get("/api/me", headers=ALINEA)).status_code == 200  # still signed in


async def test_a_short_new_password_is_refused_without_counting_a_try(client, owner):
    for _ in range(6):
        response = await change(client, owner, password="curta")
        assert (response.status_code, response.json()["error"]) == (422, "password_too_short")
    assert (await change(client, owner)).status_code == 200


async def test_five_wrong_current_passwords_then_a_wait(client, owner):
    for _ in range(5):
        assert (await change(client, owner, current="wrong")).status_code == 422
    refused = await change(client, owner)  # even the right one, for now
    assert (refused.status_code, refused.json()["error"]) == (429, "too_many_attempts")


async def test_the_wait_is_per_account(client, db_session, owner):
    for _ in range(5):
        await change(client, owner, current="wrong")
    member = await sign_in_as(client, db_session, "membro@alinea.example", Role.MEMBER)
    assert (await change(client, member)).status_code == 200


async def test_only_a_signed_in_staff_member_with_their_token(client, db_session, owner):
    assert (await client.patch("/api/me", json={"name": "X"}, headers=ALINEA)).status_code == 403
    assert (await change(client, ALINEA)).status_code == 403
    client.cookies.clear()
    assert (await client.patch("/api/me", json={"name": "X"}, headers=owner)).status_code == 401
    # Another office's staff change only their own account, on their own address.
    norte = await sign_in_as(client, db_session, "dona@norte.example", Role.OWNER, NORTE, "norte")
    assert (await client.patch("/api/me", json={"name": "Nora"}, headers=norte)).status_code == 204


# -- the email ---------------------------------------------------------------------------


@pytest.fixture
def sent(monkeypatch):
    from backend.tests.test_team import Sent
    from backend.web import email_confirmation

    box = Sent()
    monkeypatch.setattr(email_confirmation, "sender_for", lambda settings, http: box)
    return box


async def change_email(client, headers, email="ana.nova@alinea.example", current=PASSWORD):
    return await client.post(
        "/api/me/email/change", json={"current": current, "email": email}, headers=headers
    )


async def test_a_new_email_is_confirmed_by_its_code_and_the_old_one_is_told(client, owner, sent):
    from backend.tests.test_team import code_in

    response = await change_email(client, owner, email="  Ana.Nova@Alinea.example ")
    assert response.status_code == 200, response.text
    assert (response.json()["email"], response.json()["email_confirmed"]) == (
        "ana.nova@alinea.example",
        False,
    )
    notice, code = sent.emails
    assert notice.to == "dona@alinea.example" and "foi alterado" in notice.subject
    assert "ana.nova@alinea.example" in notice.text
    assert code.to == "ana.nova@alinea.example"
    # Until the code from the new address is typed, nothing else works.
    blocked = await client.get("/api/projects", headers=ALINEA)
    assert (blocked.status_code, blocked.json()["error"]) == (403, "email_unconfirmed")
    typed = await client.post(
        "/api/me/email-code", json={"code": code_in(code.text)}, headers=owner
    )
    assert typed.status_code == 200, typed.text
    assert (await client.get("/api/projects", headers=ALINEA)).status_code == 200
    # The new address signs in; the old one no longer does.
    client.cookies.clear()
    for email, status in (("ana.nova@alinea.example", 200), ("dona@alinea.example", 401)):
        signed = await client.post(
            "/api/session", json={"email": email, "password": PASSWORD}, headers=ALINEA
        )
        assert signed.status_code == status


async def test_changing_the_email_needs_the_current_password(client, owner, sent):
    response = await change_email(client, owner, current="not it")
    assert (response.status_code, response.json()["error"]) == (422, "current_password_wrong")
    assert sent.emails == []
    assert (await client.get("/api/me", headers=ALINEA)).json()["email"] == "dona@alinea.example"


@pytest.mark.parametrize(
    ("email", "status", "error"),
    [
        ("not an email", 422, "invalid_email"),
        ("dona@alinea.example", 422, "email_unchanged"),
        ("membro@alinea.example", 409, "account_exists"),  # another account's
    ],
)
async def test_an_email_that_cant_be_the_accounts_is_refused(
    client, db_session, owner, sent, email, status, error
):
    from backend.identity import accounts  # another account, not signed in here

    await accounts.create_user(
        db_session, email="membro@alinea.example", name="Caio", password=PASSWORD, role=Role.MEMBER
    )
    response = await change_email(client, owner, email=email)
    assert (response.status_code, response.json()["error"]) == (status, error)
    assert sent.emails == []


async def test_wrong_passwords_for_the_email_count_with_the_passwords(client, owner, sent):
    for _ in range(5):
        await change(client, owner, current="wrong")
    refused = await change_email(client, owner)
    assert (refused.status_code, refused.json()["error"]) == (429, "too_many_attempts")


async def test_a_password_changed_while_checking_the_current_one_wins(
    client, db_session, owner, monkeypatch
):
    """Two changes at once: the one checked against an outdated password loses."""
    from sqlalchemy import text

    real = account.verify_password

    async def meanwhile(password_hash, password):
        ok = await real(password_hash, password)
        # Another tab's change (or a reset) lands while this one is being checked.
        await db_session.execute(
            text("UPDATE users SET password_hash = 'changed' WHERE email = 'dona@alinea.example'")
        )
        return ok

    monkeypatch.setattr(account, "verify_password", meanwhile)
    response = await change(client, owner)
    assert (response.status_code, response.json()["error"]) == (422, "current_password_wrong")
    stored = await db_session.scalar(
        text("SELECT password_hash FROM users WHERE email = 'dona@alinea.example'")
    )
    assert stored == "changed"  # the other change stands


async def test_each_email_change_notifies_the_old_address_under_its_own_key(client, owner, sent):
    """The provider drops a repeated key for a day: A→B, B→A, A→B must all go."""
    from backend.tests.test_team import code_in

    keys = []
    for new in ("b@alinea.example", "dona@alinea.example", "b@alinea.example"):
        response = await change_email(client, owner, email=new)
        assert response.status_code == 200, response.text
        notice, code = sent.emails[-2:]
        keys.append(notice.idempotency_key)
        typed = await client.post(
            "/api/me/email-code", json={"code": code_in(code.text)}, headers=owner
        )
        assert typed.status_code == 200
    assert len(set(keys)) == 3
