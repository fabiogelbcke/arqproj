"""The staff command: creating accounts and password links, as the owner login."""

import hashlib
import re

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.commands import staff
from backend.commands.seed import seed
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


def rows(url, sql):
    engine = create_engine(url)
    with engine.connect() as connection:
        found = connection.execute(text(sql)).all()
    engine.dispose()
    return found


def accounts_in(url):
    return rows(
        url,
        "SELECT t.slug, u.email, u.role, u.password_hash FROM users u "
        "JOIN tenants t ON t.id = u.tenant_id ORDER BY t.slug",
    )


def unused_links(url):
    return rows(
        url,
        "SELECT u.email, l.kind, l.token_hash FROM password_links l "
        "JOIN users u ON u.id = l.user_id WHERE l.used_at IS NULL",
    )


def token_in(output):
    return re.search(r"#token=(\S+)", output).group(1)


async def run(url, *argv):
    return await staff.run(list(argv), url)


async def test_add_creates_an_account_without_a_password_and_prints_an_invite(database):
    output = await run(
        database,
        "add",
        "--tenant",
        "alinea",
        "--email",
        "Ana@Example.com",
        "--name",
        "Ana",
        "--role",
        "owner",
    )
    assert output.startswith("Created owner ana@example.com in alinea")
    # On the office's primary address, with the token in the fragment.
    assert "http://alinea.localhost:5173/painel/definir-senha#token=" in output
    assert accounts_in(database) == [("alinea", "ana@example.com", "owner", None)]
    [(_, kind, stored)] = unused_links(database)
    assert kind == "invite"
    assert stored == hashlib.sha256(token_in(output).encode()).hexdigest()


async def test_the_same_email_gets_a_separate_account_in_each_tenant(database):
    """The owner login is a superuser locally, so tenant isolation does not hide
    other tenants' accounts from it: the command must still keep them apart."""
    for tenant in ("alinea", "norte"):
        await run(database, "add", "--tenant", tenant, "--email", "ana@example.com", "--name", "A")
    assert [(slug, email) for slug, email, *_ in accounts_in(database)] == [
        ("alinea", "ana@example.com"),
        ("norte", "ana@example.com"),
    ]


async def test_an_email_is_added_only_once_per_tenant(database):
    add = ["add", "--tenant", "alinea", "--email", "ana@example.com", "--name", "Ana"]
    await run(database, *add)
    with pytest.raises(SystemExit, match="already an account"):
        await run(database, *add[:4], "ANA@example.com", "--name", "Ana")
    assert len(accounts_in(database)) == 1


async def test_a_reset_link_replaces_any_earlier_link(database):
    await run(database, "add", "--tenant", "alinea", "--email", "ana@example.com", "--name", "A")
    output = await run(database, "reset-link", "--tenant", "alinea", "--email", "ana@example.com")
    [(_, kind, stored)] = unused_links(database)  # the invite no longer works
    assert kind == "reset"
    assert stored == hashlib.sha256(token_in(output).encode()).hexdigest()


async def test_a_reset_link_is_for_that_tenants_account_only(database):
    await run(database, "add", "--tenant", "norte", "--email", "ana@example.com", "--name", "A")
    with pytest.raises(SystemExit, match="No account"):
        await run(database, "reset-link", "--tenant", "alinea", "--email", "ana@example.com")


@pytest.mark.parametrize(
    ("argv", "error"),
    [
        (["add", "--tenant", "nowhere", "--email", "a@b.c", "--name", "A"], "No tenant"),
        (["add", "--tenant", "alinea", "--email", "a@b.c", "--name", "A", "--role", "admin"], "2"),
        (["reset-link", "--tenant", "alinea", "--email", "who@b.c"], "No account"),
    ],
)
async def test_mistakes_are_refused_and_change_nothing(database, argv, error):
    with pytest.raises(SystemExit, match=error):
        await run(database, *argv)
    assert accounts_in(database) == []
    assert unused_links(database) == []
