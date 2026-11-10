"""Local copies of the app on different ports don't sign each other out. The test
client keeps one cookie jar across ports, as a browser does."""

import pytest

from backend.app import create_app
from backend.commands.seed import seed
from backend.identity.models import Role
from backend.settings import Settings
from backend.tests.conftest import TEST_DATABASE_URL
from backend.tests.test_office import sign_in_as
from backend.web import auth
from backend.web.local_cookies import LocalCookiesMiddleware

pytestmark = pytest.mark.anyio

ONE = {"host": "alinea.localhost:8027"}
OTHER = {"host": "alinea.localhost:8030"}


async def signed_in_email(client, host):
    response = await client.get("/api/me", headers=host)
    return response.json()["email"] if response.status_code == 200 else None


@pytest.fixture
async def seeded(db_session):
    await seed(db_session)


async def test_signing_in_on_one_port_leaves_another_signed_in(client, db_session, seeded):
    await sign_in_as(client, db_session, "ana@alinea.example", Role.OWNER, host=ONE)
    assert await signed_in_email(client, OTHER) is None

    await sign_in_as(client, db_session, "bia@alinea.example", Role.OWNER, host=OTHER)

    assert await signed_in_email(client, ONE) == "ana@alinea.example"
    assert await signed_in_email(client, OTHER) == "bia@alinea.example"


async def test_signing_out_on_one_port_leaves_another_signed_in(client, db_session, seeded):
    await sign_in_as(client, db_session, "ana@alinea.example", Role.OWNER, host=ONE)
    other = await sign_in_as(client, db_session, "bia@alinea.example", Role.OWNER, host=OTHER)

    response = await client.delete("/api/session", headers=other)

    assert response.status_code == 204, response.text
    assert await signed_in_email(client, OTHER) is None
    assert await signed_in_email(client, ONE) == "ana@alinea.example"


async def test_an_address_without_a_port_keeps_the_usual_name(client, db_session, seeded):
    host = {"host": "alinea.localhost"}
    await sign_in_as(client, db_session, "ana@alinea.example", Role.OWNER, host=host)

    assert client.cookies.get(auth.COOKIE)
    assert await signed_in_email(client, host) == "ana@alinea.example"


@pytest.mark.parametrize(
    ("environment", "installed"), [("local", True), ("staging", False), ("production", False)]
)
def test_only_local_copies_rename_cookies(environment, installed):
    app = create_app(Settings(environment=environment, database_url=TEST_DATABASE_URL))
    assert (LocalCookiesMiddleware in [m.cls for m in app.user_middleware]) is installed
