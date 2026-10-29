"""Creating an office from a link an operator sent (backend/web/office_signup.py)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from backend.tests import test_admin, test_operator_actions

operators = test_admin.operators  # fixtures
actions_enabled = test_operator_actions.actions_enabled
UNIO = test_admin.UNIO
pytestmark = pytest.mark.anyio


async def make_link(client) -> str:
    headers = await test_admin.sign_in(client)
    response = await client.post("/api/admin/signup-links", headers=headers)
    assert response.status_code == 200, response.text
    url = response.json()["url"]
    assert url.startswith("http://localhost:5173/criar-escritorio#token=")
    client.cookies.clear()  # its holder is no operator
    return url.split("#token=")[1]


async def check(client, token, address=None, headers=UNIO):
    body = {"token": token} | ({"address": address} if address is not None else {})
    return await client.post("/api/office-signup/check", json=body, headers=headers)


async def create(client, token, name="Estúdio Ipê", address="ipe", headers=UNIO):
    return await client.post(
        "/api/office-signup/create",
        json={"token": token, "name": name, "address": address},
        headers=headers,
    )


async def test_a_link_creates_the_office_at_its_address_and_hands_over_to_the_owner_signup(
    client, actions_enabled, db_session
):
    token = await make_link(client)
    checked = await check(client, token)
    assert checked.json() == {"domain": "localhost", "address_free": None}
    assert (await check(client, token, "ipe")).json()["address_free"] is True
    response = await create(client, token, name="  Estúdio   Ipê ")
    assert response.status_code == 200, response.text
    owner_url = response.json()["owner_url"]
    assert owner_url.startswith("http://ipe.localhost:5173/painel/entrar-na-equipe#token=")
    office = (
        await db_session.execute(
            text(
                "SELECT t.name, t.status, d.hostname FROM tenants t "
                "JOIN tenant_domains d ON d.tenant_id = t.id AND d.is_primary WHERE t.slug = 'ipe'"
            )
        )
    ).one()
    assert tuple(office) == ("Estúdio Ipê", "active", "ipe.localhost")
    # Used up: the link creates one office only.
    again = await create(client, token, address="outro")
    assert (again.status_code, again.json()["error"]) == (404, "signup_link_invalid")
    assert (await check(client, token)).status_code == 404
    audit = (
        await db_session.execute(
            text("SELECT action, actor FROM operator_audit_events WHERE target_slug = 'ipe'")
        )
    ).one()
    assert audit.action == "create" and audit.actor.startswith("signup-link:")


async def test_the_owner_link_it_hands_over_opens_the_new_offices_signup(client, actions_enabled):
    token = await make_link(client)
    owner = (await create(client, token)).json()["owner_url"].split("#token=")[1]
    response = await client.post(
        "/api/join/check", json={"token": owner}, headers={"host": "ipe.localhost"}
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"office": "Estúdio Ipê", "role": "owner"}


async def test_an_address_in_use_is_refused_and_the_link_stays_good(client, actions_enabled):
    token = await make_link(client)
    assert (await check(client, token, "alinea")).json()["address_free"] is False
    response = await create(client, token, address="alinea")
    assert (response.status_code, response.json()["error"]) == (409, "office_address_taken")
    assert (await create(client, token, address="ipe")).status_code == 200


@pytest.mark.parametrize(
    "address",
    ["ab", "-ipe", "ipe-", "xn--ipe", "ipê", "ipe.app", "admin", "www", "a" * 41, "i pe"],
)
async def test_an_address_that_isnt_a_plain_subdomain_or_is_reserved_is_refused(
    client, actions_enabled, address
):
    token = await make_link(client)
    response = await create(client, token, address=address)
    assert (response.status_code, response.json()["error"]) == (422, "invalid_office_address")
    assert (await check(client, token)).status_code == 200  # not used up


@pytest.mark.parametrize("name", ["   ", "x" * 29])
async def test_an_office_needs_a_name_clients_can_read(client, actions_enabled, name):
    token = await make_link(client)
    response = await create(client, token, name=name)
    assert (response.status_code, response.json()["error"]) == (422, "invalid_office_name")


async def test_an_expired_or_unknown_link_creates_nothing(client, actions_enabled, db_session):
    token = await make_link(client)
    await db_session.execute(
        text("UPDATE office_signup_links SET expires_at = :past"),
        {"past": datetime.now(UTC) - timedelta(minutes=1)},
    )
    for attempt in (token, "nao-existe"):
        response = await create(client, attempt)
        assert (response.status_code, response.json()["error"]) == (404, "signup_link_invalid")
    assert await db_session.scalar(text("SELECT count(*) FROM tenants WHERE slug = 'ipe'")) == 0


async def test_only_unios_address_serves_it(client, actions_enabled):
    token = await make_link(client)
    office = {"host": "alinea.localhost"}
    assert (await check(client, token, headers=office)).status_code == 404
    assert (await create(client, token, headers=office)).status_code == 404
    assert (await check(client, token)).status_code == 200  # still unused


async def test_only_signed_in_operators_make_links(client, operators, actions_enabled):
    assert (await client.post("/api/admin/signup-links", headers=UNIO)).status_code == 401
    headers = await test_admin.sign_in(client)
    assert (await client.post("/api/admin/signup-links", headers=UNIO)).status_code == 403
    elsewhere = headers | {"host": "alinea.localhost"}
    assert (await client.post("/api/admin/signup-links", headers=elsewhere)).status_code == 404


async def test_without_the_operator_login_nothing_is_created(client, operators):
    headers = await test_admin.sign_in(client)
    response = await client.post("/api/admin/signup-links", headers=headers)
    assert (response.status_code, response.json()["error"]) == (503, "operator_actions_unavailable")
    response = await create(client, "qualquer")
    assert response.status_code == 503


async def test_the_app_role_cannot_read_signup_links(app, actions_enabled):
    # Only the operator login reads them: the app's own login, which every office
    # page uses, has no grant at all (a violation case for the rule).
    async with app.state.sessionmaker() as db:
        with pytest.raises(ProgrammingError):
            await db.execute(text("SELECT * FROM office_signup_links"))
    async with app.state.operator_sessionmaker() as db:
        await db.execute(text("SELECT count(*) FROM office_signup_links"))


async def test_the_page_answers_only_on_unios_address(app, client, operators, tmp_path):
    (tmp_path / "admin.html").write_text("<!doctype html><title>Admin</title>")
    (tmp_path / "client.html").write_text("<!doctype html><head><!--page-head--></head>")
    app.state.settings = app.state.settings.model_copy(update={"frontend_dist": str(tmp_path)})
    page = await client.get("/criar-escritorio", headers=UNIO)
    assert page.status_code == 200 and "Admin" in page.text
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    elsewhere = await client.get("/criar-escritorio", headers={"host": "alinea.localhost"})
    assert elsewhere.status_code == 404 and "Admin" not in elsewhere.text


async def test_a_project_at_that_address_stays_reachable_on_its_office(
    app, client, operators, db_session, tmp_path
):
    (tmp_path / "client.html").write_text("<!doctype html><head><!--page-head--></head>")
    app.state.settings = app.state.settings.model_copy(update={"frontend_dist": str(tmp_path)})
    await db_session.execute(
        text("UPDATE project_slugs SET slug = 'criar-escritorio' WHERE slug = 'casa-jardim'")
    )
    page = await client.get("/criar-escritorio", headers={"host": "alinea.localhost"})
    assert page.status_code == 200 and "Casa Jardim" in page.text
