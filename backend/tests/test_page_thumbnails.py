"""The small pictures on the client page's file cards (GET .../files/{key}/thumb):
the same rules as opening the file itself."""

import pytest

from backend.storage.folder import FolderStorage
from backend.tests import test_office
from backend.tests.test_office import ALINEA, PNG
from backend.tests.test_page_access import PROTECTED, SEED_PASSWORD, Roles, unlock
from backend.web import attempts

owner = test_office.owner  # fixtures

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def fresh_attempts():
    attempts.reset()
    yield
    attempts.reset()


@pytest.fixture
def photo(tmp_path, monkeypatch):
    """A photo in Refúgio da Mantiqueira's first stage (a password-protected page in
    the seed), with a thumbnail as Drive would give one (local folders have none)."""
    folder = tmp_path / "Projeto Padrão" / "01 - Proposta"
    folder.mkdir(parents=True)
    (folder / "Fachada.png").write_bytes(PNG)

    async def thumbnail(self, item, size=640):
        return PNG

    monkeypatch.setattr(FolderStorage, "thumbnail", thumbnail)


async def thumb_url(client) -> str:
    """As staff: the photo's thumbnail address, as the page lists it."""
    listed = await client.get(f"/api/pages/{PROTECTED}/files", headers=ALINEA)
    key = listed.json()["stages"][0]["groups"][0]["files"][0]["key"]
    return f"/api/pages/{PROTECTED}/files/{key}/thumb"


async def test_a_protected_pages_thumbnail_needs_its_password(client, owner, photo):
    url = await thumb_url(client)
    Roles(client).visitor()
    locked = await client.get(url, headers=ALINEA)
    assert locked.status_code == 404 and PNG not in locked.content
    # The self-test: the same address shows the picture once the page is unlocked.
    assert (await unlock(client, SEED_PASSWORD)).status_code == 204
    opened = await client.get(url, headers=ALINEA)
    assert (opened.status_code, opened.content) == (200, PNG)
    assert opened.headers["content-type"] == "image/png"
    assert opened.headers["cache-control"] == "private, no-store"


async def test_staff_see_the_thumbnail_without_the_password(client, owner, photo):
    response = await client.get(await thumb_url(client), headers=ALINEA)
    assert (response.status_code, response.content) == (200, PNG)


async def test_a_thumbnail_that_isnt_a_picture_is_never_served(client, owner, photo, monkeypatch):
    """Storage with no thumbnail (local folders), or bytes that aren't an image the
    browser may show inline: the card keeps its icon."""
    url = await thumb_url(client)

    async def none(self, item, size=640):
        return None

    monkeypatch.setattr(FolderStorage, "thumbnail", none)
    assert (await client.get(url, headers=ALINEA)).status_code == 404

    async def page(self, item, size=640):
        return b"<html><script>alert(1)</script></html>"

    monkeypatch.setattr(FolderStorage, "thumbnail", page)
    response = await client.get(url, headers=ALINEA)
    assert response.status_code == 404 and b"script" not in response.content


async def test_a_key_from_another_page_shows_no_thumbnail(client, owner, photo):
    url = await thumb_url(client)
    elsewhere = url.replace(PROTECTED, "casa-jardim")
    assert (await client.get(elsewhere, headers=ALINEA)).status_code == 404
