"""Step 2.5: each stage's files on the client's page (local folder storage)."""

import pytest
from sqlalchemy import text

from backend.tests import test_office
from backend.tests.test_office import ALINEA, PNG
from backend.tests.test_page_access import SEED_PASSWORD, Roles, change, unlock
from backend.web import attempts, page_files

owner = test_office.owner  # fixtures

pytestmark = pytest.mark.anyio

PDF = b"%PDF-1.4 fictional"


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
    (briefing / "_rascunho interno.txt").write_text("só o escritório")
    (briefing / "Plantas antigas").mkdir()
    (briefing / "Plantas antigas" / "Planta v1.dwg").write_bytes(b"dwg")
    (briefing / "Plantas antigas" / "Mais fundo").mkdir()
    (briefing / "Plantas antigas" / "Mais fundo" / "Escondido.pdf").write_bytes(PDF)
    (briefing / "_interno").mkdir()
    (briefing / "_interno" / "Orçamento.pdf").write_bytes(PDF)
    (tmp_path / "Casa Jardim" / "02 - Conceito").mkdir()
    return tmp_path


async def listing(client, slug="casa-jardim"):
    return await client.get(f"/api/pages/{slug}/files", headers=ALINEA)


async def test_each_stage_shows_its_files_and_subfolders_as_groups(client, owner, files):
    response = await listing(client)
    assert response.status_code == 200, response.text
    stages = response.json()["stages"]
    assert [s["position"] for s in stages] == list(range(1, 8))
    first = stages[0]["groups"]
    assert first[0]["folder"] is None
    assert {f["name"]: f["kind"] for f in first[0]["files"]} == {
        "Foto do terreno.png": "image",
        "Programa de necessidades.pdf": "pdf",
    }
    assert [(g["folder"], [f["name"] for f in g["files"]]) for g in first[1:]] == [
        ("Plantas antigas", ["Planta v1.dwg"])  # one level: "Mais fundo" isn't shown
    ]
    assert stages[1]["groups"] == []  # an empty folder
    assert stages[5]["groups"] == []  # no folder bound (the seed binds five)


async def test_the_offices_own_files_stay_hidden(client, owner, files):
    shown = (await listing(client)).text
    for hidden in ("_rascunho", "_interno", "Orçamento", "Escondido"):
        assert hidden not in shown


async def test_files_download_and_images_and_pdfs_also_show_inline(client, owner, files):
    first = (await listing(client)).json()["stages"][0]["groups"][0]["files"]
    pdf = next(f for f in first if f["kind"] == "pdf")
    download = await client.get(f"/api/pages/casa-jardim/files/{pdf['key']}", headers=ALINEA)
    assert (download.status_code, download.content) == (200, PDF)
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["content-type"] == "application/octet-stream"
    assert download.headers["x-content-type-options"] == "nosniff"
    shown = await client.get(
        f"/api/pages/casa-jardim/files/{pdf['key']}?inline=true", headers=ALINEA
    )
    assert shown.headers["content-type"] == "application/pdf"
    assert shown.headers["content-disposition"].startswith("inline;")
    image = next(f for f in first if f["kind"] == "image")
    inline = await client.get(
        f"/api/pages/casa-jardim/files/{image['key']}?inline=true", headers=ALINEA
    )
    assert inline.headers["content-type"] == "image/png"
    assert "sandbox" in inline.headers["content-security-policy"]


async def test_other_files_never_open_on_the_offices_address(client, owner, files):
    """A .dwg (or an .html) only downloads, as raw bytes, sandboxed."""
    groups = (await listing(client)).json()["stages"][0]["groups"]
    dwg = groups[1]["files"][0]
    response = await client.get(
        f"/api/pages/casa-jardim/files/{dwg['key']}?inline=true", headers=ALINEA
    )
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["content-type"] == "application/octet-stream"
    assert "sandbox" in response.headers["content-security-policy"]


async def test_names_with_accents_download_with_their_name(client, owner, files):
    first = (await listing(client)).json()["stages"][0]["groups"][0]["files"]
    pdf = next(f for f in first if f["kind"] == "pdf")
    disposition = (
        await client.get(f"/api/pages/casa-jardim/files/{pdf['key']}", headers=ALINEA)
    ).headers["content-disposition"]
    assert "filename*=UTF-8''Programa%20de%20necessidades.pdf" in disposition


async def test_a_key_opens_only_its_own_project(client, owner, files):
    first = (await listing(client)).json()["stages"][0]["groups"][0]["files"]
    key = first[0]["key"]
    elsewhere = await client.get(f"/api/pages/apartamento-atlantico/files/{key}", headers=ALINEA)
    assert elsewhere.status_code == 404
    forged = await client.get(f"/api/pages/casa-jardim/files/{key[:-4]}AAAA", headers=ALINEA)
    assert forged.status_code == 404


async def test_a_protected_pages_files_need_its_password(client, owner, tmp_path):
    folder = tmp_path / "Projeto Padrão" / "01 - Proposta"  # Refúgio's first stage
    folder.mkdir(parents=True)
    (folder / "Proposta.pdf").write_bytes(PDF)
    roles = Roles(client)
    roles.visitor()
    assert (await listing(client, "refugio-da-mantiqueira")).status_code == 403
    await unlock(client, SEED_PASSWORD)
    listed = await listing(client, "refugio-da-mantiqueira")
    assert listed.status_code == 200
    assert listed.headers["cache-control"] == "private, no-store"
    key = listed.json()["stages"][0]["groups"][0]["files"][0]["key"]
    opened = await client.get(f"/api/pages/refugio-da-mantiqueira/files/{key}", headers=ALINEA)
    assert opened.status_code == 200
    # A new password ends the keys handed out before.
    roles.staff()
    await change(
        client, owner, "refugio-da-mantiqueira", access_mode="password", password="outra-senha"
    )
    roles.visitor()
    await unlock(client, "outra-senha")
    old = await client.get(f"/api/pages/refugio-da-mantiqueira/files/{key}", headers=ALINEA)
    assert old.status_code == 404


async def test_a_drafts_files_are_not_found_for_visitors(client, db_session, owner, files):
    await db_session.execute(
        text("UPDATE projects SET status = 'draft' WHERE name = 'Casa Jardim' AND tenant_id = "
             "(SELECT id FROM tenants WHERE slug = 'alinea')")
    )  # fmt: skip
    first = (await listing(client)).json()["stages"][0]["groups"][0]["files"]  # staff see them
    Roles(client).visitor()
    assert (await listing(client)).status_code == 404
    response = await client.get(f"/api/pages/casa-jardim/files/{first[0]['key']}", headers=ALINEA)
    assert response.status_code == 404


async def test_a_missing_stage_folder_marks_that_stage_unavailable(client, owner, tmp_path):
    """No folder on disk for Casa Jardim: each bound stage says so; the page lives on."""
    stages = (await listing(client)).json()["stages"]
    assert stages[0]["unavailable"] is True
    assert stages[5]["unavailable"] is False  # no folder bound: simply empty


async def test_a_file_moved_out_of_the_stage_no_longer_opens(client, owner, files):
    """A key opens what the page listed only while it's still there (A05)."""
    first = (await listing(client)).json()["stages"][0]["groups"][0]["files"]
    pdf = next(f for f in first if f["kind"] == "pdf")
    url = f"/api/pages/casa-jardim/files/{pdf['key']}"
    assert (await client.get(url, headers=ALINEA)).status_code == 200
    briefing = files / "Casa Jardim" / "01 - Briefing"
    (briefing / "Programa de necessidades.pdf").rename(files / "Programa de necessidades.pdf")
    assert (await client.get(url, headers=ALINEA)).status_code == 404


async def test_a_file_in_a_folder_hidden_later_no_longer_opens(client, owner, files):
    groups = (await listing(client)).json()["stages"][0]["groups"]
    dwg = groups[1]["files"][0]  # in "Plantas antigas"
    briefing = files / "Casa Jardim" / "01 - Briefing"
    (briefing / "Plantas antigas").rename(briefing / "_Plantas antigas")
    response = await client.get(f"/api/pages/casa-jardim/files/{dwg['key']}", headers=ALINEA)
    assert response.status_code == 404


async def test_disconnected_storage_marks_stages_unavailable_with_a_reference(
    client, owner, files, monkeypatch
):
    from backend.storage.base import StorageError, StorageProblem

    def disconnected(*_args):
        raise StorageError(StorageProblem.NO_ACCESS, "office disconnected Drive")

    monkeypatch.setattr(page_files, "storage_for", disconnected)
    response = await listing(client)
    assert response.status_code == 200
    shown = response.json()
    assert shown["stages"][0]["unavailable"] is True
    assert shown["stages"][5]["unavailable"] is False  # no folder bound
    assert shown["reference"] == response.headers["x-request-id"]


async def test_the_database_is_released_before_a_file_streams(client, owner, files, monkeypatch):
    """A slow download must not hold one of the few database connections."""
    from sqlalchemy.ext.asyncio import AsyncSession

    events = []
    real_close = AsyncSession.close
    real_stream = page_files.StreamingResponse

    async def close(self):
        events.append("database released")
        await real_close(self)

    def stream(*args, **kwargs):
        events.append("streaming")
        return real_stream(*args, **kwargs)

    first = (await listing(client)).json()["stages"][0]["groups"][0]["files"]
    monkeypatch.setattr(AsyncSession, "close", close)
    monkeypatch.setattr(page_files, "StreamingResponse", stream)
    await client.get(f"/api/pages/casa-jardim/files/{first[0]['key']}", headers=ALINEA)
    assert events.index("database released") < events.index("streaming")


async def test_a_files_key_reveals_no_ids(client, owner, files):
    import base64

    first = (await listing(client)).json()["stages"][0]["groups"][0]["files"]
    key = first[0]["key"]
    raw = base64.urlsafe_b64decode(key.split(":", 1)[1] + "==")
    assert b"Casa Jardim" not in raw and b"Programa" not in raw  # encrypted, not encoded


async def test_drive_down_during_a_download_says_try_again(client, owner, files, monkeypatch):
    from backend.storage.base import StorageError, StorageProblem
    from backend.storage.folder import FolderStorage

    first = (await listing(client)).json()["stages"][0]["groups"][0]["files"]

    async def down(self, item):
        raise StorageError(StorageProblem.UNAVAILABLE, "simulated")

    monkeypatch.setattr(FolderStorage, "download", down)
    response = await client.get(f"/api/pages/casa-jardim/files/{first[0]['key']}", headers=ALINEA)
    assert (response.status_code, response.json()) == (503, {"error": "files_unavailable"})
    assert response.headers["x-request-id"]
