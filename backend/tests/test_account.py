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
