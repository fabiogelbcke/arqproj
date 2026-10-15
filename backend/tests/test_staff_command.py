"""The staff command: creating accounts and setting passwords, as the owner login."""

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.commands import staff
from backend.commands.seed import seed
from backend.identity.passwords import verify_password
from backend.tests.conftest import alembic_config

pytestmark = pytest.mark.anyio


@pytest.fixture
def migrated(migrated_url):
    command.upgrade(alembic_config(migrated_url), "head")  # runs its own event loop
    return migrated_url


@pytest.fixture
async def database(migrated):
    """A migrated database with the two dev tenants, committed (the command connects itself)."""
    migrated_url = migrated
    engine = create_async_engine(migrated_url)
    async with AsyncSession(engine) as session:
        await seed(session)
        await session.commit()
    await engine.dispose()
    return migrated_url


def accounts_in(url):
    engine = create_engine(url)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT t.slug, u.email, u.role, u.password_hash FROM users u "
                "JOIN tenants t ON t.id = u.tenant_id ORDER BY t.slug"
            )
        ).all()
    engine.dispose()
    return rows


async def run(url, *argv, password="a good password"):
    return await staff.run(list(argv), url, lambda: password)


async def test_the_same_email_gets_a_separate_account_in_each_tenant(database):
    """The owner login is a superuser locally, so tenant isolation does not hide
    other tenants' accounts from it: the command must still keep them apart."""
    add = ["add", "--email", "Ana@Example.com", "--name", "Ana"]
    assert await run(database, *add, "--tenant", "alinea", "--role", "owner") == (
        "Created owner ana@example.com in alinea"
    )
    await run(database, *add, "--tenant", "norte", password="norte's password")
    rows = accounts_in(database)
    assert [(slug, email, role) for slug, email, role, _ in rows] == [
        ("alinea", "ana@example.com", "owner"),
        ("norte", "ana@example.com", "member"),
    ]
    assert await verify_password(rows[0].password_hash, "a good password")
    assert not await verify_password(rows[1].password_hash, "a good password")


async def test_an_email_is_added_only_once_per_tenant(database):
    add = ["add", "--tenant", "alinea", "--email", "ana@example.com", "--name", "Ana"]
    await run(database, *add)
    with pytest.raises(SystemExit, match="already an account"):
        await run(database, *add[:4], "ANA@example.com", "--name", "Ana")
    assert len(accounts_in(database)) == 1


async def test_set_password_changes_only_that_tenants_account(database):
    for tenant in ("alinea", "norte"):
        await run(database, "add", "--tenant", tenant, "--email", "ana@example.com", "--name", "A")
    await run(
        database,
        "set-password",
        "--tenant",
        "norte",
        "--email",
        "ana@example.com",
        password="a brand new password",
    )
    alinea, norte = accounts_in(database)
    assert await verify_password(alinea.password_hash, "a good password")
    assert await verify_password(norte.password_hash, "a brand new password")


@pytest.mark.parametrize(
    ("argv", "password", "error"),
    [
        (
            ["add", "--tenant", "nowhere", "--email", "a@b.c", "--name", "A"],
            "long enough!",
            "No tenant",
        ),
        (["add", "--tenant", "alinea", "--email", "a@b.c", "--name", "A"], "short", "at least"),
        (
            ["set-password", "--tenant", "alinea", "--email", "who@b.c"],
            "long enough!",
            "No account",
        ),
    ],
)
async def test_mistakes_are_refused_and_change_nothing(database, argv, password, error):
    with pytest.raises(SystemExit, match=error):
        await run(database, *argv, password=password)
    assert accounts_in(database) == []
