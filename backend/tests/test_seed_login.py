"""The seed's dev login: each fictional office gets an owner who can sign in with
the documented password, and the seed puts that password back when it changed."""

import pytest
from sqlalchemy import select

from backend.commands.seed import STAFF_PASSWORD, TENANTS, seed
from backend.identity import accounts
from backend.identity.models import Role, User
from backend.identity.passwords import hash_password

pytestmark = pytest.mark.anyio

ALINEA = {"host": "alinea.localhost"}
EMAIL, _NAME = next(t["staff"] for t in TENANTS if t["slug"] == "alinea")


async def _owner(db_session) -> User:
    return await db_session.scalar(select(User).where(User.email == EMAIL))


async def test_the_seed_creates_an_owner_who_can_sign_in(client, db_session):
    added = await seed(db_session, with_staff=True)
    assert f"login {EMAIL}" in added
    owner = await _owner(db_session)
    assert owner.role == Role.OWNER and owner.email_confirmed_at is not None
    signed_in = await client.post(
        "/api/session", json={"email": EMAIL, "password": STAFF_PASSWORD}, headers=ALINEA
    )
    assert signed_in.status_code == 200 and signed_in.json()["email"] == EMAIL
    # Every office has one, in its own office.
    emails = {t["staff"][0] for t in TENANTS}
    rows = (await db_session.execute(select(User.email, User.tenant_id))).all()
    assert {email for email, _ in rows} == emails
    assert len({tenant for _, tenant in rows}) == len(TENANTS)


async def test_seeding_again_changes_nothing_while_the_password_stands(db_session):
    await seed(db_session, with_staff=True)
    before = (await _owner(db_session)).password_hash
    assert await seed(db_session, with_staff=True) == []
    assert (await _owner(db_session)).password_hash == before


async def test_seeding_again_puts_a_changed_password_back(client, db_session):
    await seed(db_session, with_staff=True)
    owner = await _owner(db_session)
    await accounts.set_password(db_session, owner, await hash_password("outra-senha-123"))
    await db_session.commit()
    wrong = await client.post(
        "/api/session", json={"email": EMAIL, "password": STAFF_PASSWORD}, headers=ALINEA
    )
    assert wrong.status_code == 401
    assert await seed(db_session, with_staff=True) == [f"login {EMAIL}"]
    back = await client.post(
        "/api/session", json={"email": EMAIL, "password": STAFF_PASSWORD}, headers=ALINEA
    )
    assert back.status_code == 200
