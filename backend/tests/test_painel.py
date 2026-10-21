"""Serving the staff app, the build ID, the public tenant facts, the shared
translations and the frontend's copy of the API description."""

import json
from enum import StrEnum
from pathlib import Path

import pytest
from sqlalchemy import select, text

from backend.commands import openapi
from backend.commands.seed import seed
from backend.identity import accounts
from backend.identity.models import Role
from backend.projects.enums import (
    AccessMode,
    ProjectStatus,
)
from backend.settings import Environment
from backend.tenancy.models import Locale, Tenant
from backend.web import painel
from backend.web.errors import ErrorCode

pytestmark = pytest.mark.anyio

ROOT = Path(__file__).resolve().parents[2]
ALINEA = {"host": "alinea.localhost"}


@pytest.fixture
def dist(app, tmp_path):
    """A stand-in for `frontend/dist`, so these tests need no Node build."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>shell</html>")
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("not an asset")
    app.state.settings = app.state.settings.model_copy(update={"frontend_dist": str(tmp_path)})
    return tmp_path


@pytest.fixture
async def tenants(db_session):
    await seed(db_session)


@pytest.mark.parametrize("path", ["/painel", "/painel/", "/painel/entrar", "/painel/a/deep/link"])
async def test_every_painel_address_gets_the_uncached_shell(client, dist, tenants, path):
    """The app's router picks the screen, so deep links and reloads work; the shell
    names the current build's files, so it must never be cached."""
    response = await client.get(path, headers=ALINEA)
    assert (response.status_code, response.text) == (200, "<html>shell</html>")
    assert response.headers["cache-control"] == painel.SHELL_CACHE
    # Plan section 4; that the real build runs under it is checked by `make e2e`.
    policy = response.headers["content-security-policy"]
    assert "script-src 'self'" in policy and "frame-ancestors 'none'" in policy


async def test_built_files_are_cached_for_a_long_time(client, dist):
    response = await client.get("/painel/assets/index-abc123.js", headers=ALINEA)
    assert response.status_code == 200
    assert "immutable" in response.headers["cache-control"]


@pytest.mark.parametrize("path", ["/painel/assets/index-old999.js", "/painel/assets/../secret.txt"])
async def test_a_missing_or_outside_file_is_a_plain_404(client, dist, path):
    """Not the shell: an old tab asking for a previous build's file must fail
    visibly, so the app can offer a reload. And nothing outside assets/."""
    response = await client.get(path, headers=ALINEA)
    assert response.status_code == 404
    assert "shell" not in response.text and "not an asset" not in response.text


async def test_the_painel_only_answers_on_a_known_office_address(client, dist, tenants):
    assert (await client.get("/painel", headers={"host": "unknown.example"})).status_code == 404


async def test_an_unbuilt_app_says_how_to_build_it(app, client, tenants, tmp_path):
    app.state.settings = app.state.settings.model_copy(update={"frontend_dist": str(tmp_path)})
    response = await client.get("/painel", headers=ALINEA)
    assert response.status_code == 503 and "make build" in response.text


@pytest.fixture
def preview_built(dist):
    (dist / "preview.html").write_text("<html>preview</html>")
    return dist


def environment(app, name):
    app.state.settings = app.state.settings.model_copy(update={"environment": name})


async def test_the_preview_page_is_open_locally_and_may_be_framed_by_its_own_site(
    client, preview_built, tenants
):
    """Plan section 18, "Visual variants": the page draws the client page in a frame
    of its own address; nothing else may frame it."""
    response = await client.get("/painel/previa?frame&view=staff", headers=ALINEA)
    assert (response.status_code, response.text) == (200, "<html>preview</html>")
    assert response.headers["cache-control"] == painel.SHELL_CACHE
    policy = response.headers["content-security-policy"]
    assert "frame-ancestors 'self'" in policy and "frame-ancestors 'none'" not in policy
    assert "script-src 'self'" in policy
    # Every other painel address still refuses to be framed.
    shell = await client.get("/painel/entrar", headers=ALINEA)
    assert "frame-ancestors 'none'" in shell.headers["content-security-policy"]


async def test_the_preview_page_is_never_in_production(app, client, preview_built, db_session):
    await seed(db_session)
    environment(app, Environment.PRODUCTION)
    staff = await sign_in_as(client, db_session, "dona@alinea.example")
    response = await client.get("/painel/previa", headers=staff)
    assert response.status_code == 404 and "preview" not in response.text


async def test_on_staging_the_preview_page_is_for_the_offices_staff(
    app, client, preview_built, db_session
):
    await seed(db_session)
    environment(app, Environment.STAGING)
    visitor = await client.get("/painel/previa?stages=3", headers=ALINEA)
    assert (visitor.status_code, visitor.headers["location"]) == (302, "/painel/")
    assert "preview" not in visitor.text

    # Signed in locally: deployed, the session cookie only travels over HTTPS.
    environment(app, Environment.LOCAL)
    staff = await sign_in_as(client, db_session, "dona@alinea.example")
    environment(app, Environment.STAGING)
    response = await client.get("/painel/previa?stages=3", headers=staff)
    assert (response.status_code, response.text) == (200, "<html>preview</html>")


async def sign_in_as(client, db, email):
    tenant = await db.scalar(select(Tenant.id).where(Tenant.slug == "alinea"))
    await db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
    await accounts.create_user(
        db, email=email, name="Ana", password="a good password", role=Role.OWNER
    )
    await client.post(
        "/api/session", json={"email": email, "password": "a good password"}, headers=ALINEA
    )
    return ALINEA


async def test_every_response_names_its_build(app, client, tenants):
    response = await client.get("/api/tenant", headers=ALINEA)
    assert response.headers["x-build-id"] == app.state.settings.build_id
    assert (await client.get("/health")).headers["x-build-id"] == app.state.settings.build_id


async def test_the_office_name_language_and_logo_are_public(client, tenants):
    response = await client.get("/api/tenant", headers=ALINEA)
    assert response.json() == {
        "name": "Alinea (dev)",
        "locale": "pt-BR",
        "logo_url": None,  # none uploaded yet (test_office covers one)
        "logo_dark_url": None,
    }


# -- translations (plan A26) -----------------------------------------------


def _keys(tree, prefix=""):
    for key, value in tree.items():
        if isinstance(value, dict):
            yield from _keys(value, f"{prefix}{key}.")
        else:
            yield f"{prefix}{key}"


def catalog(locale):
    return json.loads((ROOT / "backend" / "i18n" / f"{locale}.json").read_text("utf-8"))


def test_there_is_a_catalog_for_every_supported_language_and_nothing_else():
    present = {path.stem for path in (ROOT / "backend" / "i18n").glob("*.json")}
    assert present == {locale.value for locale in Locale}


def test_every_language_has_every_text():
    keys = {locale: set(_keys(catalog(locale))) for locale in Locale}
    reference = keys[Locale.PT_BR]
    for locale, present in keys.items():
        assert present == reference, (
            f"{locale}: missing {reference - present}, extra {present - reference}"
        )


@pytest.mark.parametrize(
    ("group", "enum"),
    [
        ("errors", ErrorCode),
        ("role", Role),
        ("locale", Locale),
        ("projectStatus", ProjectStatus),
        ("accessMode", AccessMode),
    ],
)
def test_every_built_in_value_the_screens_show_is_translated(group, enum: type[StrEnum]):
    for locale in Locale:
        texts = catalog(locale)[group]
        missing = {member.value for member in enum} - set(texts)
        assert not missing, f"{locale}: no {group} text for {missing}"


def test_the_translation_check_catches_a_gap(monkeypatch):
    """Self-test: a new error code without a text must fail the check above."""

    class Extended(StrEnum):
        BRAND_NEW = "brand_new_error"

    with pytest.raises(AssertionError, match="brand_new_error"):
        test_every_built_in_value_the_screens_show_is_translated("errors", Extended)


# -- API description for the frontend ----------------------------------------


def test_the_frontends_api_description_is_current():
    """The staff app's types are generated from this file; regenerate with
    `make api-types` after changing the API."""
    committed = (ROOT / "frontend" / "src" / "api" / "openapi.json").read_text("utf-8")
    assert committed == openapi.schema(), "run `make api-types`"
