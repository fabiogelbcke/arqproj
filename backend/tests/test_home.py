"""The OAuth homepage is public even without an office or a database session."""

from contextlib import asynccontextmanager
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx2
import pytest

from backend.app import create_app
from backend.settings import Settings

pytestmark = pytest.mark.anyio
EXAMPLE = "/tour-projeto"


class Resources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = set()
        self.assets = set()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.links.add(values["href"])
        if tag in ("img", "link"):
            self.assets.add(values.get("src") or values.get("href"))


@pytest.mark.parametrize("host", ["myunio.app", "staging.myunio.app", "alinea.localhost"])
async def test_home_and_all_its_resources_are_public_without_tenant_or_login(host):
    # No lifespan/database: any accidental tenant lookup or auth dependency fails.
    app = create_app(Settings())
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url=f"https://{host}"
    ) as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "set-cookie" not in response.headers
        page = Resources()
        page.feed(response.text)
        assert {"/privacidade", "/termos", EXAMPLE} <= page.links
        # The example's page is the client page's build: tested below.
        local = {link for link in page.links if link.startswith("/")} - {EXAMPLE}
        for path in page.assets | local:
            resource = await client.get(path)
            assert resource.status_code == 200, path
            assert "location" not in resource.headers
        assert (await client.head("/")).status_code == 200


async def test_home_assets_are_typed_and_not_a_general_file_server():
    app = create_app(Settings())
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="https://myunio.app"
    ) as client:
        page = Resources()
        page.feed((await client.get("/")).text)
        for path in page.assets:
            response = await client.get(path)
            suffix = urlsplit(path).path.rsplit(".", 1)[-1]
            assert response.headers["content-type"].startswith(
                {"png": "image/png", "css": "text/css"}[suffix]
            )
            assert response.headers["x-content-type-options"] == "nosniff"


async def test_public_home_does_not_bypass_tenant_checks_for_other_routes(monkeypatch):
    from backend.tenancy import middleware

    looked_up = []

    @asynccontextmanager
    async def session():
        yield None

    async def unknown_host(db, host):
        looked_up.append(host)
        return None

    monkeypatch.setattr(middleware, "resolve", unknown_host)
    app = create_app(Settings())
    app.state.sessionmaker = session
    paths = ("/painel", "/api/projects", "/casa-jardim", "/brand/unknown.png", EXAMPLE)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="https://unknown.example"
    ) as client:
        for path in paths:
            assert (await client.get(path)).status_code == 404
    assert len(looked_up) == len(paths)


async def test_the_example_project_opens_from_unios_own_address(tmp_path):
    """The home links to it (plan section 16): on Unio's address it needs no office."""
    (tmp_path / "client.html").write_text("<head><!--page-head--></head><div id=page>")
    settings = Settings(operator_host="myunio.app", frontend_dist=str(tmp_path))
    app = create_app(settings)  # no database: a tenant lookup would fail
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="https://myunio.app"
    ) as client:
        response = await client.get(EXAMPLE)
    assert response.status_code == 200
    assert "<title>Projeto de exemplo</title>" in response.text and "id=page" in response.text
    assert response.headers["x-robots-tag"] == "noindex"
