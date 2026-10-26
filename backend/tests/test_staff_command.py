"""The staff command: creating accounts and password links, as the owner login."""

import hashlib
import re
from datetime import UTC, datetime, timedelta

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


async def test_reset_tour_shows_the_tour_again_for_that_account(database):
    await run(database, "add", "--tenant", "alinea", "--email", "ana@example.com", "--name", "A")
    engine = create_engine(database)
    with engine.begin() as connection:
        connection.execute(text("UPDATE users SET tour_seen_at = now()"))
    engine.dispose()
    output = await run(database, "reset-tour", "--tenant", "alinea", "--email", "ana@example.com")
    assert "starts again" in output
    [(seen,)] = rows(database, "SELECT tour_seen_at FROM users WHERE email = 'ana@example.com'")
    assert seen is None


@pytest.mark.parametrize(
    ("argv", "error"),
    [
        (["add", "--tenant", "nowhere", "--email", "a@b.c", "--name", "A"], "No tenant"),
        (["add", "--tenant", "alinea", "--email", "a@b.c", "--name", "A", "--role", "admin"], "2"),
        (["reset-link", "--tenant", "alinea", "--email", "who@b.c"], "No account"),
        (["reset-tour", "--tenant", "alinea", "--email", "who@b.c"], "No account"),
    ],
)
async def test_mistakes_are_refused_and_change_nothing(database, argv, error):
    with pytest.raises(SystemExit, match=error):
        await run(database, *argv)
    assert accounts_in(database) == []
    assert unused_links(database) == []


@pytest.mark.parametrize(("options", "days"), [((), 7), (("--days", "2"), 2)])
async def test_owner_link_needs_no_account_and_stores_only_the_hash(database, options, days):
    before = datetime.now(UTC)
    output = await run(database, "owner-link", "--tenant", "alinea", *options)
    after = datetime.now(UTC)
    assert "http://alinea.localhost:5173/painel/entrar-na-equipe#token=" in output
    assert f"works once, for {days} day(s)" in output
    assert accounts_in(database) == []
    [(slug, role, single_use, expires_at, created_by, stored, used_at)] = rows(
        database,
        "SELECT t.slug, l.role, l.single_use, l.expires_at, l.created_by, "
        "l.token_hash, l.used_at FROM join_links l JOIN tenants t ON t.id = l.tenant_id",
    )
    assert (slug, role, single_use, created_by, used_at) == ("alinea", "owner", True, None, None)
    assert before + timedelta(days=days) <= expires_at <= after + timedelta(days=days)
    assert stored == hashlib.sha256(token_in(output).encode()).hexdigest()


async def test_owner_links_use_the_primary_host_and_can_be_created_independently(database):
    engine = create_engine(database)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE tenant_domains SET hostname = 'alinea.example' WHERE is_primary "
                "AND tenant_id = (SELECT id FROM tenants WHERE slug = 'alinea')"
            )
        )
    engine.dispose()
    first = await run(database, "owner-link", "--tenant", "alinea")
    second = await run(database, "owner-link", "--tenant", "alinea")
    other = await run(database, "owner-link", "--tenant", "norte")
    assert "https://alinea.example/painel/entrar-na-equipe#token=" in first
    assert "http://norte.localhost:5173/painel/entrar-na-equipe#token=" in other
    assert token_in(first) != token_in(second)
    assert len(rows(database, "SELECT id FROM join_links WHERE revoked_at IS NULL")) == 3
    assert accounts_in(database) == []


@pytest.mark.parametrize("days", ["0", "-1", "one"])
async def test_owner_link_refuses_invalid_lifetimes(database, days, capsys):
    with pytest.raises(SystemExit, match="2"):
        await run(database, "owner-link", "--tenant", "alinea", "--days", days)
    assert "--days" in capsys.readouterr().err
    assert rows(database, "SELECT id FROM join_links") == []


async def test_owner_link_requires_an_existing_tenant_and_primary_address(database):
    with pytest.raises(SystemExit, match="No tenant"):
        await run(database, "owner-link", "--tenant", "nowhere")
    engine = create_engine(database)
    with engine.begin() as connection:
        connection.execute(text("UPDATE tenant_domains SET is_primary = false"))
    engine.dispose()
    with pytest.raises(SystemExit, match="no primary address"):
        await run(database, "owner-link", "--tenant", "alinea")
    assert rows(database, "SELECT id FROM join_links") == []
