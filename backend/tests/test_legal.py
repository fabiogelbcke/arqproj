"""Unio's privacy policy and terms of use (A33): Unio's, on every address."""

import pytest

from backend.tests.test_office import ALINEA

pytestmark = pytest.mark.anyio

UNIO = {"host": "myunio.app"}  # no office's address


@pytest.mark.parametrize("headers", [UNIO, ALINEA], ids=["myunio.app", "an office's address"])
@pytest.mark.parametrize("path", ["/privacidade", "/termos"])
async def test_the_legal_pages_answer_on_every_address(client, headers, path):
    response = await client.get(path, headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Unio" in response.text
    assert "arqdevproj@gmail.com" in response.text  # where requests go
    assert "ALINEA" not in response.text.upper()  # Unio's, not an office's


async def test_the_privacy_policy_has_what_google_checks(client):
    """The OAuth consent screen links here; Google's review looks for the scope,
    the Limited Use statement and how to revoke access."""
    text = (await client.get("/privacidade", headers=UNIO)).text
    assert "drive.file" in text
    assert "Uso Limitado" in text and "Limited Use" in text
    assert "https://developers.google.com/terms/api-services-user-data-policy" in text
    assert "myaccount.google.com/permissions" in text


async def test_a_project_page_is_still_unknown_on_myunio_app(client):
    assert (await client.get("/casa-jardim", headers=UNIO)).status_code == 404
