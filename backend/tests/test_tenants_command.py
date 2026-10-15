"""The tenants command: offices and addresses in a real (non-seeded) database."""

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from backend.commands import tenants
from backend.tests.conftest import alembic_config

pytestmark = pytest.mark.anyio


@pytest.fixture
def database(migrated_url):
    command.upgrade(alembic_config(migrated_url), "head")
    return migrated_url


def addresses(url):
    engine = create_engine(url)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT t.slug, t.locale, d.hostname, d.is_primary FROM tenant_domains d "
                "JOIN tenants t ON t.id = d.tenant_id ORDER BY d.hostname"
            )
        ).all()
    engine.dispose()
    return [tuple(row) for row in rows]


async def run(url, *argv):
    return await tenants.run(list(argv), url)


async def test_an_office_starts_with_its_primary_address(database):
    message = await run(
        database, "add", "--slug", "alinea", "--name", "ALINEA", "--host", "Staging.Run.App."
    )
    assert message == "Created office alinea on staging.run.app"
    assert addresses(database) == [("alinea", "pt-BR", "staging.run.app", True)]


async def test_a_new_primary_address_demotes_the_old_one(database):
    await run(database, "add", "--slug", "alinea", "--name", "A", "--host", "old.example")
    await run(database, "add-host", "--slug", "alinea", "--host", "new.example", "--primary")
    await run(database, "add-host", "--slug", "alinea", "--host", "alias.example")
    assert addresses(database) == [
        ("alinea", "pt-BR", "alias.example", False),
        ("alinea", "pt-BR", "new.example", True),
        ("alinea", "pt-BR", "old.example", False),
    ]


@pytest.mark.parametrize(
    ("argv", "error"),
    [
        (["add", "--slug", "outra", "--name", "B", "--host", "taken.example"], "already belongs"),
        (["add", "--slug", "alinea", "--name", "B", "--host", "free.example"], "already an office"),
        (["add-host", "--slug", "nowhere", "--host", "free.example"], "No office"),
        (["add-host", "--slug", "alinea", "--host", "www.free.example"], "Not a usable"),
        (["add-host", "--slug", "alinea", "--host", "https://free.example"], "Not a usable"),
        (["add-host", "--slug", "alinea", "--host", "free.example:443"], "Not a usable"),
        (["add-host", "--slug", "alinea", "--host", "free.example/painel"], "Not a usable"),
    ],
)
async def test_mistakes_are_refused_and_change_nothing(database, argv, error):
    await run(database, "add", "--slug", "alinea", "--name", "A", "--host", "taken.example")
    with pytest.raises(SystemExit, match=error):
        await run(database, *argv)
    assert addresses(database) == [("alinea", "pt-BR", "taken.example", True)]
