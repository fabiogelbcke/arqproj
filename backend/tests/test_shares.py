"""Sharing files by link (A37): made from the page's files, served as they were
picked, managed by staff or the device that made them (local folder storage)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from backend.tests import test_office
from backend.tests.test_maintenance_scan import CASA
from backend.tests.test_office import ALINEA, NORTE, PNG
from backend.tests.test_page_access import Roles
from backend.web import attempts, shares

owner = test_office.owner  # fixtures

pytestmark = pytest.mark.anyio

PDF = b"%PDF-1.4 fictional"
SHELL = "<html><head><!--page-head--></head><body>page</body></html>"


@pytest.fixture(autouse=True)
def fresh_attempts():
    attempts.reset()
    yield
    attempts.reset()


@pytest.fixture
def files(tmp_path):
    """Casa Jardim's first two stage folders (as the seed binds them), with files."""
    briefing = tmp_path / "Casa Jardim" / "01 - Briefing"
    briefing.mkdir(parents=True)
    (briefing / "Programa de necessidades.pdf").write_bytes(PDF)
    (briefing / "Foto do terreno.png").write_bytes(PNG)
    (briefing / "Planta.pdf").write_bytes(PDF + b" v1")
    (tmp_path / "Casa Jardim" / "02 - Conceito").mkdir()
    return tmp_path


async def page_files(client):
    """The page's files of the first stage, by name, as the page lists them."""
    response = await client.get("/api/pages/casa-jardim/files", headers=ALINEA)
    assert response.status_code == 200, response.text
    return {f["name"]: f for g in response.json()["stages"][0]["groups"] for f in g["files"]}


async def make(client, names, headers=ALINEA, **body):
    listed = await page_files(client)
    return await client.post(
        "/api/pages/casa-jardim/shares",
        json={"files": [listed[n]["key"] for n in names], "expiry": "30d", **body},
        headers=headers,
    )


async def made(client, names, headers=ALINEA, **body):
    response = await make(client, names, headers, **body)
    assert response.status_code == 201, response.text
    return response.json()


def token_of(link):
    return link["url"].rsplit("/", 1)[1]


async def shared(client, link, host=ALINEA):
    return await client.get(f"/api/share/{token_of(link)}", headers=host)


async def shared_names(client, link):
    response = await shared(client, link)
    assert response.status_code == 200, response.text
    return [f["name"] for f in response.json()["files"]]


async def listed(client, headers):
    response = await client.get("/api/pages/casa-jardim/shares", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# -- making one ------------------------------------------------------------------------


async def test_a_client_shares_files_and_the_supplier_downloads_them(client, owner, files):
    Roles(client).visitor()
    link = await made(client, ["Planta.pdf", "Foto do terreno.png"], label="Marcenaria Silva")
    assert link["url"].startswith("http://alinea.localhost/share/")
    assert (link["link"]["made_by"], link["link"]["files"]) == (None, 2)  # the client
    assert link["link"]["label"] == "Marcenaria Silva"
    page = await shared(client, link)
    assert page.headers["x-robots-tag"] == "noindex"
    assert page.headers["referrer-policy"] == "no-referrer"
    body = page.json()
    assert (body["project"], body["label"], body["unavailable"]) == (
        "Casa Jardim",
        "Marcenaria Silva",
        0,
    )
    assert [(f["name"], f["stage"]) for f in body["files"]] == [
        ("Planta.pdf", "01 Briefing"),
        ("Foto do terreno.png", "01 Briefing"),
    ]  # in the order picked
    download = await client.get(
        f"/api/share/{token_of(link)}/files/{body['files'][0]['key']}", headers=ALINEA
    )
    assert (download.status_code, download.content) == (200, PDF + b" v1")
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["referrer-policy"] == "no-referrer"


async def test_staff_links_say_who_made_them(client, owner, files):
    link = await made(client, ["Planta.pdf"], headers=owner)
    assert link["link"]["made_by"] == "Ana"
    # Without the session's CSRF token, staff count as anyone: the client.
    other = await made(client, ["Planta.pdf"])
    assert other["link"]["made_by"] is None


async def test_the_expiry_is_the_senders_choice(client, owner, files):
    week = await made(client, ["Planta.pdf"], expiry="7d")
    never = await made(client, ["Planta.pdf"], expiry="never")
    expires = datetime.fromisoformat(week["link"]["expires_at"])
    assert timedelta(days=6, hours=23) < expires - datetime.now(UTC) <= timedelta(days=7)
    assert never["link"]["expires_at"] is None


async def test_only_files_the_page_listed_can_be_shared(client, owner, files):
    response = await client.post(
        "/api/pages/casa-jardim/shares",
        json={"files": ["not-a-key"], "expiry": "7d"},
        headers=ALINEA,
    )
    assert (response.status_code, response.json()["error"]) == (404, "file_not_found")


async def test_a_file_hidden_since_the_page_opened_is_refused(client, owner, files):
    listed_now = await page_files(client)
    (files / "Casa Jardim" / "01 - Briefing" / "Planta.pdf").rename(
        files / "Casa Jardim" / "01 - Briefing" / "_Planta.pdf"
    )
    response = await client.post(
        "/api/pages/casa-jardim/shares",
        json={"files": [listed_now["Planta.pdf"]["key"]], "expiry": "7d"},
        headers=ALINEA,
    )
    assert (response.status_code, response.json()["error"]) == (409, "share_files_changed")


async def test_a_link_holds_at_most_300_mb(client, owner, files, monkeypatch):
    monkeypatch.setattr(shares, "SIZE_MAX", len(PDF) * 2)
    response = await make(
        client, ["Planta.pdf", "Programa de necessidades.pdf", "Foto do terreno.png"]
    )
    assert (response.status_code, response.json()["error"]) == (422, "share_too_large")
    assert (await make(client, ["Planta.pdf"])).status_code == 201


async def test_a_device_makes_only_a_few_links_at_a_time(client, owner, files):
    for _ in range(attempts.LIMIT):
        assert (await make(client, ["Planta.pdf"])).status_code == 201
    response = await make(client, ["Planta.pdf"])
    assert (response.status_code, response.json()["error"]) == (429, "too_many_attempts")


async def test_a_locked_page_shares_nothing_and_its_links_need_no_password(
    client, db_session, owner, files
):
    link = await made(client, ["Planta.pdf"], headers=owner)
    await db_session.execute(
        text(f"UPDATE projects SET access_mode = 'password', password_hash = 'x' WHERE id = {CASA}")
    )
    Roles(client).visitor()
    refused = await client.post(
        "/api/pages/casa-jardim/shares", json={"files": ["x"], "expiry": "7d"}, headers=ALINEA
    )
    assert refused.status_code == 403  # the page asks for its password first
    assert await shared_names(client, link) == ["Planta.pdf"]  # the sender had it


# -- what a link serves ----------------------------------------------------------------


async def test_renamed_or_moved_to_another_stage_a_file_stays_in_the_link(client, owner, files):
    link = await made(client, ["Planta.pdf"])
    stage = files / "Casa Jardim"
    (stage / "01 - Briefing" / "Planta.pdf").rename(stage / "02 - Conceito" / "Planta baixa.pdf")
    body = (await shared(client, link)).json()
    assert [(f["name"], f["stage"]) for f in body["files"]] == [
        ("Planta baixa.pdf", "02 Levantamento")
    ]


async def test_hidden_or_deleted_files_drop_out_and_are_counted(client, owner, files):
    link = await made(client, ["Planta.pdf", "Foto do terreno.png", "Programa de necessidades.pdf"])
    briefing = files / "Casa Jardim" / "01 - Briefing"
    old_key = (await shared(client, link)).json()["files"][0]["key"]
    (briefing / "Planta.pdf").rename(briefing / "_Planta.pdf")  # hidden from the client
    (briefing / "Foto do terreno.png").unlink()
    body = (await shared(client, link)).json()
    assert ([f["name"] for f in body["files"]], body["unavailable"]) == (
        ["Programa de necessidades.pdf"],
        2,
    )
    assert (await listed(client, owner))[0]["available"] == 1
    # A key handed out before it was hidden opens nothing now.
    gone = await client.get(f"/api/share/{token_of(link)}/files/{old_key}", headers=ALINEA)
    assert gone.status_code == 404
    assert "Voltar aos arquivos" in gone.text
    # Shown again: back in the link.
    (briefing / "_Planta.pdf").rename(briefing / "Planta.pdf")
    assert "Planta.pdf" in await shared_names(client, link)


async def test_a_link_serves_the_version_it_was_sent_with_until_updated(client, owner, files):
    Roles(client).visitor()
    link = await made(client, ["Planta.pdf"])
    (files / "Casa Jardim" / "01 - Briefing" / "Planta v2.pdf").write_bytes(PDF + b" v2")
    body = (await shared(client, link)).json()
    assert [f["name"] for f in body["files"]] == ["Planta.pdf"]  # what the supplier was sent
    download = await client.get(
        f"/api/share/{token_of(link)}/files/{body['files'][0]['key']}", headers=ALINEA
    )
    assert download.content == PDF + b" v1"
    mine = await client.post(
        "/api/pages/casa-jardim/shares/mine", json={"owners": [link["owner"]]}, headers=ALINEA
    )
    assert mine.json()[0]["newer"] == 1  # "1 arquivo tem versão mais recente"
    # "Atualizar link", from the device that made it: the same address, now v2.
    updated = await client.post(
        f"/api/pages/casa-jardim/shares/{link['link']['id']}/refresh",
        json={"owner": link["owner"]},
        headers=ALINEA,
    )
    assert updated.status_code == 200, updated.text
    assert (updated.json()["newer"], updated.json()["files"]) == (0, 1)
    body = (await shared(client, link)).json()
    assert [f["name"] for f in body["files"]] == ["Planta v2.pdf"]
    # The old version's key stops opening: the link no longer holds it.
    stale = await client.get(
        f"/api/share/{token_of(link)}/files/{download.request.url.path.rsplit('/', 1)[1]}",
        headers=ALINEA,
    )
    assert stale.status_code == 404


async def test_a_link_lists_only_on_its_offices_address(client, owner, files):
    link = await made(client, ["Planta.pdf"])
    assert (await shared(client, link, host=NORTE)).status_code == 404


# -- managing links --------------------------------------------------------------------


async def test_staff_see_every_link_of_the_project_and_visitors_none(client, owner, files):
    roles = Roles(client)
    roles.visitor()
    mine = await made(client, ["Planta.pdf"], label="Vidraçaria")
    roles.staff()
    theirs = await made(client, ["Planta.pdf", "Foto do terreno.png"], headers=owner)
    shown = await listed(client, owner)
    assert sorted((s["id"], s["made_by"], s["files"]) for s in shown) == sorted(
        [(theirs["link"]["id"], "Ana", 2), (mine["link"]["id"], None, 1)]
    )
    roles.visitor()
    assert (await client.get("/api/pages/casa-jardim/shares", headers=ALINEA)).status_code == 401


async def test_a_device_lists_only_the_links_it_made(client, owner, files):
    Roles(client).visitor()
    first = await made(client, ["Planta.pdf"])
    await made(client, ["Planta.pdf"])  # made elsewhere: its owner key isn't sent
    response = await client.post(
        "/api/pages/casa-jardim/shares/mine",
        json={"owners": [first["owner"], "forged.key"]},
        headers=ALINEA,
    )
    assert [s["id"] for s in response.json()] == [first["link"]["id"]]


async def test_staff_or_the_device_that_made_it_turn_a_link_off(client, owner, files):
    roles = Roles(client)
    roles.visitor()
    first = await made(client, ["Planta.pdf"])
    second = await made(client, ["Planta.pdf"])

    async def disable(link, owner_key, headers=ALINEA):
        return await client.post(
            f"/api/pages/casa-jardim/shares/{link['link']['id']}/disable",
            json={"owner": owner_key},
            headers=headers,
        )

    assert (await disable(first, None)).status_code == 404  # anyone else: not found
    assert (await disable(first, second["owner"])).status_code == 404  # another link's key
    assert (await disable(first, first["owner"])).json()["disabled"] is True
    assert (await shared(client, first)).json()["error"] == "share_not_found"
    roles.staff()
    assert (await disable(second, None, headers=owner)).json()["disabled"] is True
    assert (await shared(client, second)).status_code == 404


async def test_an_expired_link_or_a_deleted_project_opens_nothing(client, db_session, owner, files):
    link = await made(client, ["Planta.pdf"])
    other = await made(client, ["Planta.pdf"])
    await db_session.execute(
        text(
            "UPDATE share_links SET expires_at = now() - interval '1 minute' "
            f"WHERE id = '{link['link']['id']}'"
        )
    )
    assert (await shared(client, link)).json()["error"] == "share_not_found"
    expired = {s["id"]: s["expired"] for s in await listed(client, owner)}
    assert expired == {link["link"]["id"]: True, other["link"]["id"]: False}
    await db_session.execute(text(f"UPDATE projects SET deleted_at = now() WHERE id = {CASA}"))
    assert (await shared(client, other)).status_code == 404


async def test_a_link_downloads_up_to_its_daily_limit(
    client, db_session, owner, files, monkeypatch
):
    monkeypatch.setattr(shares, "DAY_BYTES_MAX", len(PDF) * 3)
    link = await made(client, ["Programa de necessidades.pdf"])
    key = (await shared(client, link)).json()["files"][0]["key"]
    url = f"/api/share/{token_of(link)}/files/{key}"
    for _ in range(3):
        assert (await client.get(url, headers=ALINEA)).status_code == 200
    refused = await client.get(url, headers=ALINEA)
    assert refused.status_code == 429
    assert "limite de downloads de hoje" in refused.text
    assert (await listed(client, owner))[0]["downloads"] == 3
    # A new day starts again.
    await db_session.execute(
        text(f"UPDATE share_links SET day = day - 1 WHERE id = '{link['link']['id']}'")
    )
    assert (await client.get(url, headers=ALINEA)).status_code == 200


async def test_a_key_opens_only_within_its_own_link(client, owner, files):
    first = await made(client, ["Planta.pdf"])
    second = await made(client, ["Planta.pdf"])
    key = (await shared(client, first)).json()["files"][0]["key"]
    elsewhere = await client.get(f"/api/share/{token_of(second)}/files/{key}", headers=ALINEA)
    assert elsewhere.status_code == 404
    # A page's own file key isn't a share key either.
    page_key = (await page_files(client))["Planta.pdf"]["key"]
    assert (
        await client.get(f"/api/share/{token_of(first)}/files/{page_key}", headers=ALINEA)
    ).status_code == 404


async def test_the_suppliers_page_names_only_the_office_before_any_script(
    app, client, owner, files, tmp_path
):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "client.html").write_text(SHELL)
    app.state.settings = app.state.settings.model_copy(update={"frontend_dist": str(dist)})
    link = await made(client, ["Planta.pdf"])
    shell = await client.get(f"/share/{token_of(link)}", headers=ALINEA)
    assert shell.status_code == 200
    assert "Casa Jardim" not in shell.text
    assert 'name="robots" content="noindex"' in shell.text
    assert shell.headers["referrer-policy"] == "no-referrer"
    assert (await client.get("/share/unknown", headers=ALINEA)).status_code == 404
