"""Step 2.5: each stage's files on the client's page (local folder storage)."""

import os
import time

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
        ("Plantas antigas", ["Planta.dwg"])  # one level: "Mais fundo" isn't shown
    ]
    assert first[1]["files"][0]["version"] is None  # "v1" in the name: no version shown (A25)
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


async def pdf_url(client):
    first = (await listing(client)).json()["stages"][0]["groups"][0]["files"]
    return f"/api/pages/casa-jardim/files/{next(f for f in first if f['kind'] == 'pdf')['key']}"


async def test_a_download_says_it_takes_ranges_and_names_its_version(client, owner, files):
    whole = await client.get(await pdf_url(client), headers=ALINEA)
    assert whole.headers["accept-ranges"] == "bytes"
    assert whole.headers["etag"].startswith('"') and len(whole.headers["etag"]) == 34


@pytest.mark.parametrize(
    ("asked", "first", "last"),
    [("bytes=2-5", 2, 5), ("bytes=5-", 5, len(PDF) - 1), ("bytes=-3", len(PDF) - 3, len(PDF) - 1),
     ("bytes=4-999", 4, len(PDF) - 1)],
)  # fmt: skip
async def test_a_range_gets_just_those_bytes(client, owner, files, asked, first, last):
    """A PDF opens at any page; a broken download resumes (plan section 15)."""
    part = await client.get(await pdf_url(client), headers=ALINEA | {"range": asked})
    assert (part.status_code, part.content) == (206, PDF[first : last + 1])
    assert part.headers["content-range"] == f"bytes {first}-{last}/{len(PDF)}"
    assert part.headers["content-length"] == str(last - first + 1)


async def test_a_range_past_the_end_is_refused_with_the_size(client, owner, files):
    for asked in (f"bytes={len(PDF)}-", "bytes=-0"):
        refused = await client.get(await pdf_url(client), headers=ALINEA | {"range": asked})
        assert refused.status_code == 416
        assert refused.headers["content-range"] == f"bytes */{len(PDF)}"


def test_an_empty_file_has_no_last_bytes_to_send():
    from types import SimpleNamespace

    from backend.storage.base import StorageItem

    empty = StorageItem("f1", "Vazio.pdf", "application/pdf", 0, None)
    with pytest.raises(page_files.RangeNotSatisfiable):  # not bytes 0--1
        page_files.byte_range(SimpleNamespace(headers={"range": "bytes=-5"}), empty)


@pytest.mark.parametrize(
    "asked", ["bytes=0-1,4-5", "items=0-3", "bytes=abc", "bytes=-", "bytes=5-2"]
)
async def test_a_range_we_dont_read_gets_the_whole_file(client, owner, files, asked):
    whole = await client.get(await pdf_url(client), headers=ALINEA | {"range": asked})
    assert (whole.status_code, whole.content) == (200, PDF)


async def test_a_resumed_download_of_a_changed_file_starts_over(client, owner, files):
    url = await pdf_url(client)
    tag = (await client.get(url, headers=ALINEA)).headers["etag"]
    same = await client.get(url, headers=ALINEA | {"range": "bytes=2-", "if-range": tag})
    assert same.status_code == 206
    # The file changed since (or a date was sent): the whole file, never a mix.
    for other in ('"0000"', "Wed, 21 Oct 2026 07:28:00 GMT"):
        whole = await client.get(url, headers=ALINEA | {"range": "bytes=2-", "if-range": other})
        assert (whole.status_code, whole.content) == (200, PDF)


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


@pytest.fixture
def drive(monkeypatch):
    """Drive-like storage: ids stay the same when a folder moves (local folders
    can't show this, their ids are paths)."""
    from backend.storage.memory import MemoryStorage

    storage = MemoryStorage()
    storage.add_folder("Casa Jardim", "Casa Jardim")
    storage.add_folder("Casa Jardim/01 - Briefing", "01 - Briefing", "Casa Jardim")
    storage.add_file("plan", "Planta.pdf", "Casa Jardim/01 - Briefing", PDF, "application/pdf")
    storage.add_folder("other-project", "Outro Projeto")
    monkeypatch.setattr(page_files, "storage_for", lambda *_args: storage)
    return storage


async def test_a_stage_folder_moved_to_another_project_stops_showing(client, owner, drive):
    first = (await listing(client)).json()["stages"][0]
    key = first["groups"][0]["files"][0]["key"]
    url = f"/api/pages/casa-jardim/files/{key}"
    assert (await client.get(url, headers=ALINEA)).status_code == 200
    drive._parents["Casa Jardim/01 - Briefing"] = "other-project"  # moved in Drive
    moved = (await listing(client)).json()["stages"][0]
    assert (moved["groups"], moved["unavailable"]) == ([], False)
    assert (await client.get(url, headers=ALINEA)).status_code == 404


async def test_a_failed_file_link_shows_a_translated_page_with_the_code(
    client, owner, files, monkeypatch
):
    """The page's links open the file address directly: a failure there must
    read like the site, never like the API."""
    from backend.storage.base import StorageError, StorageProblem
    from backend.storage.folder import FolderStorage

    first = (await listing(client)).json()["stages"][0]["groups"][0]["files"]

    async def down(self, item, byte_range=None):
        raise StorageError(StorageProblem.UNAVAILABLE, "Drive said 500 for item drive-item-xyz")

    monkeypatch.setattr(FolderStorage, "download", down)
    response = await client.get(f"/api/pages/casa-jardim/files/{first[0]['key']}", headers=ALINEA)
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("text/html")
    assert "Não foi possível abrir o arquivo agora" in response.text
    assert response.headers["x-request-id"] in response.text  # the support code
    assert 'href="/casa-jardim"' in response.text
    # Not hex, unlike the support code, which once contained "abc" by chance.
    assert "files_unavailable" not in response.text and "drive-item-xyz" not in response.text


async def test_a_stale_file_link_says_so_in_the_offices_language(client, owner, files):
    response = await client.get("/api/pages/casa-jardim/files/not-a-key", headers=ALINEA)
    assert response.status_code == 404
    assert "Este arquivo não está mais disponível" in response.text


async def test_a_download_that_breaks_off_is_logged_with_its_context(
    client, owner, drive, caplog, monkeypatch
):
    from backend.storage.base import Download, StorageError, StorageProblem
    from backend.storage.memory import MemoryStorage

    async def breaks(self, item, byte_range=None):
        async def chunks():
            yield b"%PDF"
            raise StorageError(StorageProblem.UNAVAILABLE, "connection reset")

        return Download(item.mime_type, None, chunks())

    monkeypatch.setattr(MemoryStorage, "download", breaks)
    key = (await listing(client)).json()["stages"][0]["groups"][0]["files"][0]["key"]
    with pytest.raises(StorageError):
        await client.get(f"/api/pages/casa-jardim/files/{key}", headers=ALINEA)
    logged = [r for r in caplog.records if "broke off" in r.getMessage()]
    assert logged and logged[0].levelname == "ERROR"
    assert "connection reset" in logged[0].getMessage() and "plan" in logged[0].getMessage()


async def test_a_public_pages_files_are_never_kept_by_the_browser(client, owner, files):
    """The list may be kept a moment; a file never, so one removed in Drive stops
    opening at once instead of coming back from the browser's cache."""
    Roles(client).visitor()
    listed = await listing(client)
    assert "no-store" not in listed.headers["cache-control"]  # Casa Jardim is public
    first = listed.json()["stages"][0]["groups"][0]["files"]
    image = next(f for f in first if f["kind"] == "image")
    url = f"/api/pages/casa-jardim/files/{image['key']}"
    for response in (
        await client.get(url, headers=ALINEA),
        await client.get(f"{url}?inline=true", headers=ALINEA),
    ):
        assert response.status_code == 200
        assert "no-store" in response.headers["cache-control"]


# -- versions from names (A25, plan section 12) ------------------------------------


def _aged(path, days):
    when = time.time() - days * 86400
    os.utime(path, (when, when))


async def first_stage(client):
    groups = (await listing(client)).json()["stages"][0]["groups"]
    return {f["name"]: f for g in groups if g["folder"] is None for f in g["files"]}


async def test_versions_show_as_one_file_with_the_older_ones_downloadable(client, owner, files):
    briefing = files / "Casa Jardim" / "01 - Briefing"
    (briefing / "Planta.pdf").write_bytes(b"%PDF v1")
    (briefing / "Planta v2.pdf").write_bytes(b"%PDF v2")
    _aged(briefing / "Planta.pdf", 30)
    shown = await first_stage(client)
    assert "Planta v2.pdf" not in shown
    plan = shown["Planta.pdf"]
    assert (plan["version"], plan["updated"], plan["clash"]) == (2, True, False)
    assert [(o["name"], o["version"]) for o in plan["older"]] == [("Planta.pdf", 1)]
    # Each version opens on its own; the download keeps Drive's name, with its version.
    current = await client.get(f"/api/pages/casa-jardim/files/{plan['key']}", headers=ALINEA)
    assert current.content == b"%PDF v2"
    assert 'filename="Planta v2.pdf"' in current.headers["content-disposition"]
    older = await client.get(
        f"/api/pages/casa-jardim/files/{plan['older'][0]['key']}", headers=ALINEA
    )
    assert older.content == b"%PDF v1"
    # Files without versions are as before.
    assert shown["Programa de necessidades.pdf"]["version"] is None
    assert shown["Programa de necessidades.pdf"]["older"] == []


async def test_atualizado_only_for_a_few_days_after_the_new_version(client, owner, files):
    briefing = files / "Casa Jardim" / "01 - Briefing"
    (briefing / "Planta.pdf").write_bytes(PDF)
    (briefing / "Planta v2.pdf").write_bytes(PDF)
    _aged(briefing / "Planta v2.pdf", 8)
    assert (await first_stage(client))["Planta.pdf"]["updated"] is False


async def test_the_newest_version_removed_brings_the_one_before_back(client, owner, files):
    briefing = files / "Casa Jardim" / "01 - Briefing"
    (briefing / "Planta.pdf").write_bytes(PDF)
    (briefing / "Planta v2.pdf").write_bytes(PDF)
    (briefing / "Planta v2.pdf").rename(briefing / "_Planta v2.pdf")  # hidden from the client
    plan = (await first_stage(client))["Planta.pdf"]
    assert (plan["version"], plan["older"]) == (None, [])


async def test_two_files_claiming_one_version_show_apart_and_flagged(client, owner, files):
    briefing = files / "Casa Jardim" / "01 - Briefing"
    (briefing / "Planta v2.pdf").write_bytes(PDF)
    (briefing / "planta_v2.pdf").write_bytes(PDF)
    shown = await first_stage(client)
    assert shown["Planta v2.pdf"]["clash"] and shown["planta_v2.pdf"]["clash"]
    assert shown["Foto do terreno.png"]["clash"] is False


async def test_versions_group_only_within_one_folder(client, owner, files):
    # "Plantas antigas" holds "Planta v1.dwg"; a v2 beside the stage's own files
    # is another document.
    (files / "Casa Jardim" / "01 - Briefing" / "Planta v2.dwg").write_bytes(b"dwg")
    groups = (await listing(client)).json()["stages"][0]["groups"]
    by_folder = {g["folder"]: g["files"] for g in groups}
    assert [(f["name"], f["version"]) for f in by_folder["Plantas antigas"]] == [
        ("Planta.dwg", None)
    ]
    top = {f["name"]: f for f in by_folder[None]}
    assert (top["Planta.dwg"]["version"], top["Planta.dwg"]["older"]) == (2, [])
