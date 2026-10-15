"""Which tenant a request belongs to, decided by its exact hostname."""

import json
import logging

import pytest
from fastapi import Depends, Request
from sqlalchemy import update

from backend.app import _CloudLoggingFormatter
from backend.commands.seed import seed
from backend.tenancy.models import Tenant, TenantDomain
from backend.tenancy.resolve import CurrentTenant, current_tenant, normalize_host

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("alinea.localhost", "alinea.localhost"),
        ("Alinea.LocalHost:8000", "alinea.localhost"),
        ("alineaarquitetos.com.", "alineaarquitetos.com"),
        ("  ALINEAARQUITETOS.COM:443 ", "alineaarquitetos.com"),
        ("", None),
        (None, None),
        ("[::1]:8000", None),
    ],
)
def test_normalize_host(raw, expected):
    assert normalize_host(raw) == expected


@pytest.fixture
async def tenants(db_session):
    """Alinea (primary + alias) and Norte, as the local seed creates them."""
    await seed(db_session)


@pytest.fixture
def tenant_route(app):
    """A test-only route that reports the tenant it was given."""

    @app.get("/whoami")
    async def whoami(tenant: CurrentTenant = Depends(current_tenant)):
        return {"slug": tenant.slug, "primary_host": tenant.primary_host}

    return app


async def get(client, host, path="/whoami", **kwargs):
    return await client.get(path, headers={"host": host, **kwargs.pop("headers", {})}, **kwargs)


async def test_each_address_gets_its_own_office(client, tenants, tenant_route):
    alinea = await get(client, "alinea.localhost")
    norte = await get(client, "norte.localhost")
    assert alinea.json() == {"slug": "alinea", "primary_host": "alinea.localhost"}
    assert norte.json() == {"slug": "norte", "primary_host": "norte.localhost"}


async def test_case_and_port_do_not_matter(client, tenants, tenant_route):
    response = await get(client, "ALINEA.localhost:8000")
    assert response.json()["slug"] == "alinea"


async def test_unknown_address_is_not_found(client, tenants, tenant_route):
    response = await get(client, "someone-else.localhost")
    assert response.status_code == 404
    assert response.text == "Not found"  # no hint of which tenants exist


async def test_missing_host_is_not_found(client, tenants, tenant_route):
    response = await get(client, "")
    assert response.status_code == 404


async def test_alias_redirects_to_primary_keeping_path_and_query(client, tenants, tenant_route):
    response = await get(client, "alinea-old.localhost:8000", path="/casa-jardim?v=2&x=%C3%A9")
    assert response.status_code == 301
    assert response.headers["location"] == "http://alinea.localhost:8000/casa-jardim?v=2&x=%C3%A9"
    assert response.headers["cache-control"] == "public, max-age=86400"


async def test_alias_keeps_a_post_a_post(client, tenants, tenant_route):
    response = await client.post("/painel/login", headers={"host": "alinea-old.localhost"})
    assert response.status_code == 308
    assert response.headers["location"] == "http://alinea.localhost/painel/login"


async def test_www_of_a_known_address_redirects(client, tenants, tenant_route):
    response = await get(client, "www.alinea.localhost", path="/casa-jardim")
    assert response.status_code == 301
    assert response.headers["location"] == "http://alinea.localhost/casa-jardim"


async def test_www_of_an_alias_goes_straight_to_the_primary(client, tenants, tenant_route):
    response = await get(client, "www.alinea-old.localhost", path="/x")
    assert response.headers["location"] == "http://alinea.localhost/x"


async def test_www_of_an_unknown_address_is_not_found(client, tenants, tenant_route):
    response = await get(client, "www.someone-else.localhost")
    assert response.status_code == 404


async def test_deployed_redirects_use_https_and_no_port(app, client, tenants, tenant_route):
    app.state.settings = app.state.settings.model_copy(update={"environment": "production"})
    response = await get(client, "alinea-old.localhost:8080", path="/x")
    assert response.headers["location"] == "https://alinea.localhost/x"


async def test_suspended_office_is_not_found(client, db_session, tenants, tenant_route):
    await db_session.execute(
        update(Tenant).where(Tenant.slug == "norte").values(status="suspended")
    )
    response = await get(client, "norte.localhost")
    assert response.status_code == 404


async def test_forwarded_host_headers_are_ignored(client, tenants, tenant_route):
    response = await get(
        client,
        "norte.localhost",
        headers={"x-forwarded-host": "alinea.localhost", "forwarded": "host=alinea.localhost"},
    )
    assert response.json()["slug"] == "norte"


async def test_health_works_on_any_address(client):
    response = await get(client, "not-an-tenant.example", path="/health")
    assert response.status_code == 200


async def test_office_without_primary_is_served_where_asked(
    client, db_session, tenants, tenant_route
):
    await db_session.execute(
        update(TenantDomain)
        .where(TenantDomain.hostname == "norte.localhost")
        .values(is_primary=False)
    )
    response = await get(client, "norte.localhost")
    assert response.status_code == 200
    assert response.json()["primary_host"] == "norte.localhost"


def test_a_route_needing_an_office_fails_loudly_without_one():
    # For example an exempt path (like /health) that asks for a tenant.
    request = Request({"type": "http", "state": {}})
    with pytest.raises(RuntimeError, match="needs a tenant"):
        current_tenant(request)


async def test_seed_is_repeatable(db_session):
    first = await seed(db_session)
    second = await seed(db_session)
    assert "tenant alinea" in first and "address alinea-old.localhost" in first
    assert second == []


# -- request IDs ------------------------------------------------------------


async def test_every_response_has_a_request_id(client, tenants, tenant_route):
    ok = await get(client, "alinea.localhost")
    missing = await get(client, "nobody.localhost")
    redirect = await get(client, "alinea-old.localhost")
    ids = {r.headers["x-request-id"] for r in (ok, missing, redirect)}
    assert len(ids) == 3 and all(len(i) == 32 for i in ids)


async def test_cloud_run_trace_id_becomes_the_request_id(client, tenants, tenant_route):
    trace = "0af7651916cd43dd8448eb211c80319c"
    response = await get(
        client, "alinea.localhost", headers={"x-cloud-trace-context": f"{trace}/1;o=1"}
    )
    assert response.headers["x-request-id"] == trace


async def test_log_lines_carry_the_request_id(app, client, tenants, capsys):
    @app.get("/log-something")
    async def log_something():
        logging.getLogger("backend.test").info("inside the request")
        return {}

    response = await get(client, "alinea.localhost", path="/log-something")
    request_id = response.headers["x-request-id"]
    assert f"INFO backend.test [{request_id}]: inside the request" in capsys.readouterr().out


def test_cloud_logs_link_to_the_trace_when_the_project_is_known():
    record = logging.LogRecord("backend.test", logging.INFO, __file__, 1, "hi", None, None)
    record.request_id = "0af7651916cd43dd8448eb211c80319c"
    entry = json.loads(_CloudLoggingFormatter("arq-proj").format(record))
    assert entry["logging.googleapis.com/trace"] == (
        "projects/arq-proj/traces/0af7651916cd43dd8448eb211c80319c"
    )
    assert "logging.googleapis.com/trace" not in json.loads(
        _CloudLoggingFormatter(None).format(record)
    )


async def test_server_errors_keep_their_request_id(app, client, tenants, capsys):
    """A crash in a route still returns the reference code, and the log has it."""

    @app.get("/boom")
    async def boom():
        raise RuntimeError("simulated database failure")

    response = await get(client, "alinea.localhost", path="/boom")
    request_id = response.headers["x-request-id"]
    assert response.status_code == 500
    assert response.text == f"Internal server error. Reference: {request_id}"
    logged = capsys.readouterr().out
    assert f"ERROR backend.web.request_id [{request_id}]: unhandled error" in logged
    assert "simulated database failure" in logged  # full traceback, for us only
    assert "simulated database failure" not in response.text  # never shown to users
