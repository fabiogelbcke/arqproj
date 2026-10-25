"""Uploads from the project page's edit mode, and "Ocultar do cliente" (A31)."""

import pytest
from sqlalchemy import text

from backend.identity.models import Role
from backend.projects import creation
from backend.storage.google_connect import ConnectError, ConnectProblem
from backend.tests import test_office
from backend.tests.test_office import ALINEA, NORTE, sign_in_as
from backend.web import page_uploads

owner = test_office.owner  # fixtures

pytestmark = pytest.mark.anyio

PDF = b"%PDF-1.4 planta"
PDF_SIZE = len(PDF)


@pytest.fixture
def folders(tmp_path):
    """Casa Jardim's first two stage folders, as the seed binds them."""
    briefing = tmp_path / "Casa Jardim" / "01 - Briefing"
    briefing.mkdir(parents=True)
    (briefing / "Programa.pdf").write_bytes(PDF)
    (tmp_path / "Casa Jardim" / "02 - Conceito").mkdir()
    return tmp_path / "Casa Jardim"


async def staff_of(client):
    return (await client.get("/api/pages/casa-jardim", headers=ALINEA)).json()["staff"]


async def project_id(client):
    return (await staff_of(client))["project_id"]


async def start(client, headers, stage=1, name="Planta baixa.pdf", size=PDF_SIZE, **extra):
    staff = await staff_of(client)
    body = {"row_version": staff["row_version"], "name": name, "size": size}
    return await client.post(
        f"/api/projects/{staff['project_id']}/stages/{stage}/uploads",
        json=body | {"mime_type": "application/pdf"} | extra,
        headers=headers,
    )


async def send(client, response, content=PDF):
    return await client.put(
        response.json()["upload_url"], content=content, headers={"host": ALINEA["host"]}
    )


async def stage_files(client, position=1):
    stages = (await client.get("/api/pages/casa-jardim/files", headers=ALINEA)).json()["stages"]
    groups = stages[position - 1]["groups"]
    return [f["name"] for g in groups for f in g["files"]]


async def test_a_staff_member_uploads_into_a_stage_and_the_page_shows_it(client, owner, folders):
    opened = await start(client, owner)
    assert opened.status_code == 200, opened.text
    sent = await send(client, opened)
    assert sent.status_code == 201
    assert (folders / "01 - Briefing" / "Planta baixa.pdf").read_bytes() == PDF
    assert "Planta baixa.pdf" in await stage_files(client)


async def test_members_upload_too(client, db_session, owner, folders):
    member = await sign_in_as(client, db_session, "membro@alinea.example", Role.MEMBER)
    assert (await start(client, member)).status_code == 200


async def test_a_name_already_there_is_kept_beside_it(client, owner, folders):
    await send(client, await start(client, owner, name="Programa.pdf"))
    assert sorted(await stage_files(client)) == ["Programa (2).pdf", "Programa.pdf"]


@pytest.mark.parametrize(
    ("changes", "status", "error"),
    [
        ({"size": page_uploads.UPLOAD_MAX + 1}, 422, "file_too_large"),
        ({"name": " \t "}, 422, "invalid_file_name"),
        ({"name": "_Rascunho.pdf"}, 422, "hidden_file_name"),  # the page would never show it
        ({"stage": 6}, 409, "stage_has_no_folder"),  # the seed binds five folders
        ({"stage": 42}, 404, "project_not_found"),
    ],
)
async def test_an_upload_that_cant_go_is_refused_before_anything_is_sent(
    client, owner, folders, changes, status, error
):
    response = await start(client, owner, **changes)
    assert (response.status_code, response.json()["error"]) == (status, error)


async def test_after_stages_moved_meanwhile_the_upload_is_refused(client, owner, folders):
    """Position 1 is another stage now: the file would land in its folder."""
    stale = (await staff_of(client))["row_version"]
    moved = await client.post(
        f"/api/projects/{await project_id(client)}/stages/1/move",
        json={"row_version": stale, "direction": 1},
        headers=owner,
    )
    assert moved.status_code == 204
    response = await start(client, owner, row_version=stale)
    assert (response.status_code, response.json()["error"]) == (409, "project_changed")


async def test_a_stage_folder_moved_out_of_the_project_takes_no_uploads(client, owner, folders):
    """The page no longer shows that folder: a file sent there would never appear."""
    (folders.parent / "Outro projeto").mkdir()
    (folders / "01 - Briefing").rename(folders.parent / "Outro projeto" / "01 - Briefing")
    response = await start(client, owner)
    assert (response.status_code, response.json()["error"]) == (409, "stage_has_no_folder")


async def test_a_name_never_becomes_a_path(client, owner, folders):
    await send(client, await start(client, owner, name="../../Fora.pdf"))
    assert (folders / "01 - Briefing" / "..-..-Fora.pdf").exists()
    assert not (folders.parent / "Fora.pdf").exists()


async def test_an_archived_project_takes_no_uploads(client, db_session, owner, folders):
    await db_session.execute(
        text(
            "UPDATE projects SET status = 'archived', archived_from = 'active' WHERE name = "
            "'Casa Jardim' AND tenant_id = (SELECT id FROM tenants WHERE slug = 'alinea')"
        )
    )
    response = await start(client, owner)
    assert (response.status_code, response.json()["error"]) == (409, "project_archived")


async def test_only_staff_with_their_token_open_uploads(client, db_session, owner, folders):
    pid = await project_id(client)
    url = f"/api/projects/{pid}/stages/1/uploads"
    body = {"row_version": (await staff_of(client))["row_version"], "name": "x.pdf", "size": 3}
    assert (await client.post(url, json=body, headers=ALINEA)).status_code in (401, 403)
    norte = await sign_in_as(client, db_session, "dona@norte.example", Role.OWNER, NORTE, "norte")
    response = await client.post(url, json=body, headers=norte)
    assert (response.status_code, response.json()["error"]) == (404, "project_not_found")


async def test_a_failed_send_is_logged_with_its_context_and_answers_with_the_code(
    client, owner, folders, caplog
):
    """The bytes never pass through the app: the page reports a send that failed."""
    pid = await project_id(client)
    response = await client.post(
        f"/api/projects/{pid}/stages/1/uploads/failed",
        json={"name": "Planta.pdf", "size": 9, "status": 403, "detail": "storageQuotaExceeded"},
        headers=owner,
    )
    assert (response.status_code, response.json()) == (502, {"error": "upload_failed"})
    reference = response.headers["x-request-id"]
    logged = [r for r in caplog.records if "sending failed" in r.getMessage()]
    assert logged and logged[0].levelname == "ERROR"
    assert pid in logged[0].getMessage() and "storageQuotaExceeded" in logged[0].getMessage()
    assert reference  # the same code the log line carries
    no_token = await client.post(
        f"/api/projects/{pid}/stages/1/uploads/failed",
        json={"name": "x", "size": 1, "status": 0},
        headers=ALINEA,
    )
    assert no_token.status_code in (401, 403)


# -- the local stand-in for Google's upload session -----------------------------------


async def test_more_or_fewer_bytes_than_declared_leave_nothing(client, owner, folders):
    before = sorted(p.name for p in (folders / "01 - Briefing").iterdir())
    too_many = await send(client, await start(client, owner), PDF + b"more")
    assert (too_many.status_code, too_many.json()["error"]) == (413, "file_too_large")
    too_few = await send(client, await start(client, owner), PDF[:3])
    assert too_few.status_code == 400
    assert sorted(p.name for p in (folders / "01 - Briefing").iterdir()) == before


async def test_a_forged_or_another_offices_upload_address_takes_nothing(client, owner, folders):
    opened = await start(client, owner)
    url = opened.json()["upload_url"]
    forged = await client.put(url[:-4] + "AAAA", content=PDF, headers=ALINEA)
    assert forged.status_code == 404
    elsewhere = await client.put(url, content=PDF, headers=NORTE)
    assert elsewhere.status_code == 404
    assert not (folders / "01 - Briefing" / "Planta baixa.pdf").exists()


async def test_the_local_stand_in_never_runs_when_deployed(app, client, owner, folders):
    from backend.settings import Environment

    opened = await start(client, owner)
    app.state.settings = app.state.settings.model_copy(update={"environment": Environment.STAGING})
    assert (await send(client, opened)).status_code == 404
    assert not (folders / "01 - Briefing" / "Planta baixa.pdf").exists()


# -- Google Drive ---------------------------------------------------------------------


class FakeWriter:
    def __init__(self, fails=False):
        self.calls = []
        self.fails = fails

    async def start_upload(self, name, parent, size, mime_type, origin):
        if self.fails:
            raise ConnectError(ConnectProblem.UNAVAILABLE, "503 from Google")
        self.calls.append((name, parent, size, mime_type, origin))
        return "https://www.googleapis.com/upload/drive/v3/files?upload_id=abc"


async def test_on_drive_the_browser_gets_googles_session_for_its_own_origin(
    client, owner, folders, monkeypatch
):
    writer = FakeWriter()

    async def drive(_request, _db):
        return writer, "root"

    monkeypatch.setattr(page_uploads, "_folders", drive)
    pid = await project_id(client)
    response = await client.post(
        f"/api/projects/{pid}/stages/1/uploads",
        json={
            "row_version": (await staff_of(client))["row_version"],
            "name": "Planta.pdf",
            "size": 1234,
            "mime_type": "application/pdf",
        },
        headers=owner | {"origin": "http://alinea.localhost"},
    )
    assert response.json()["upload_url"].startswith("https://www.googleapis.com/upload/")
    assert writer.calls == [
        (
            "Planta.pdf",
            "Casa Jardim/01 - Briefing",
            1234,
            "application/pdf",
            "http://alinea.localhost",
        )
    ]


async def test_drive_failing_to_open_an_upload_says_try_again_and_logs_it(
    client, owner, folders, monkeypatch, caplog
):
    async def drive(_request, _db):
        return FakeWriter(fails=True), "root"

    monkeypatch.setattr(page_uploads, "_folders", drive)
    response = await start(client, owner)
    assert (response.status_code, response.json()["error"]) == (503, "drive_connect_failed")
    logged = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    assert any("opening an upload failed" in m and "503 from Google" in m for m in logged)


async def test_the_writer_opens_a_resumable_upload_with_the_size_fixed():
    import httpx2

    from backend.storage.google_connect import DriveWriter

    seen = {}

    def google(request):
        seen.update(
            params=dict(request.url.params),
            length=request.headers["x-upload-content-length"],
            origin=request.headers["origin"],
            body=request.content,
        )
        return httpx2.Response(200, headers={"Location": "https://upload.example/session"})

    http = httpx2.AsyncClient(transport=httpx2.MockTransport(google))
    url = await DriveWriter(http, "token").start_upload(
        "Planta.pdf", "folder1", 99, "application/pdf", "https://alinea.example"
    )
    assert url == "https://upload.example/session"
    assert seen["params"]["uploadType"] == "resumable"
    assert (seen["length"], seen["origin"]) == ("99", "https://alinea.example")
    assert b'"parents": ["folder1"]' in seen["body"] or b'"parents":["folder1"]' in seen["body"]


# -- Ocultar do cliente ---------------------------------------------------------------


async def file_key(client, name="Programa.pdf"):
    stages = (await client.get("/api/pages/casa-jardim/files", headers=ALINEA)).json()["stages"]
    return next(f["key"] for g in stages[0]["groups"] for f in g["files"] if f["name"] == name)


async def test_hiding_renames_with_an_underscore_and_the_page_stops_showing_it(
    client, owner, folders
):
    key = await file_key(client)
    response = await client.post(f"/api/pages/casa-jardim/files/{key}/hide", headers=owner)
    assert response.status_code == 204, response.text
    assert (folders / "01 - Briefing" / "_Programa.pdf").exists()  # still in Drive
    assert "Programa.pdf" not in await stage_files(client)


async def test_a_file_put_straight_into_drive_is_hidden_there(client, owner, folders, monkeypatch):
    async def not_ours(self, item_id):
        return False  # drive.file: the grant sees only what the app created

    monkeypatch.setattr(creation.LocalFolders, "can_rename", not_ours)
    key = await file_key(client)
    response = await client.post(f"/api/pages/casa-jardim/files/{key}/hide", headers=owner)
    assert (response.status_code, response.json()["error"]) == (409, "file_not_ours")
    assert (folders / "01 - Briefing" / "Programa.pdf").exists()


async def test_only_staff_hide_files(client, owner, folders):
    key = await file_key(client)
    response = await client.post(f"/api/pages/casa-jardim/files/{key}/hide", headers=ALINEA)
    assert response.status_code in (401, 403)
    assert (folders / "01 - Briefing" / "Programa.pdf").exists()


# -- Mover para outra etapa -------------------------------------------------------------


async def move(client, headers, key, position=2, row_version=None):
    if row_version is None:
        row_version = (await staff_of(client))["row_version"]
    return await client.post(
        f"/api/pages/casa-jardim/files/{key}/move",
        json={"position": position, "row_version": row_version},
        headers=headers,
    )


async def test_moving_a_file_puts_it_in_the_other_stage(client, owner, folders):
    key = await file_key(client)
    response = await move(client, owner, key)
    assert response.status_code == 204, response.text
    assert (folders / "02 - Conceito" / "Programa.pdf").read_bytes() == PDF
    assert await stage_files(client, 1) == []
    assert await stage_files(client, 2) == ["Programa.pdf"]


async def test_a_moved_file_keeps_its_place_in_the_updates(app, client, owner, folders):
    from backend.tests.test_maintenance_scan import run

    await run(app)  # notes what's there
    await send(client, await start(client, owner, name="Planta.pdf"))
    await run(app)  # new: "file_published" in stage 1
    await move(client, owner, await file_key(client, "Planta.pdf"))
    await run(app)  # the same file, not new again
    files = (await client.get("/api/pages/casa-jardim/files", headers=ALINEA)).json()
    assert [(u["kind"], u["stage_position"], u["name"]) for u in files["updates"]] == [
        ("file_published", 2, "Planta.pdf")
    ]


async def test_a_name_already_in_the_other_stage_is_kept_beside_it(client, owner, folders):
    (folders / "02 - Conceito" / "Programa.pdf").write_bytes(b"%PDF-1.4 outro")
    assert (await move(client, owner, await file_key(client))).status_code == 204
    assert sorted(await stage_files(client, 2)) == ["Programa (2).pdf", "Programa.pdf"]


async def test_moving_after_stages_changed_is_refused(client, owner, folders):
    key = await file_key(client)
    stale = (await staff_of(client))["row_version"] - 1
    response = await move(client, owner, key, row_version=stale)
    assert (response.status_code, response.json()["error"]) == (409, "project_changed")
    assert (folders / "01 - Briefing" / "Programa.pdf").exists()


async def test_a_file_put_straight_into_drive_is_moved_there(client, owner, folders, monkeypatch):
    async def not_ours(self, item_id):
        return False

    monkeypatch.setattr(creation.LocalFolders, "can_rename", not_ours)
    response = await move(client, owner, await file_key(client))
    assert (response.status_code, response.json()["error"]) == (409, "file_not_ours_to_move")
    assert (folders / "01 - Briefing" / "Programa.pdf").exists()


async def test_only_staff_move_files(client, owner, folders):
    key = await file_key(client)
    response = await move(client, ALINEA, key, row_version=0)
    assert response.status_code in (401, 403)
    assert (folders / "01 - Briefing" / "Programa.pdf").exists()


async def test_the_writer_moves_out_of_the_old_folder_and_skips_a_file_already_there():
    import httpx2

    from backend.storage.google_connect import DriveWriter

    calls = []

    def google(request):
        calls.append((request.method, dict(request.url.params)))
        if request.method == "GET":
            return httpx2.Response(200, json={"parents": ["stage1"]})
        return httpx2.Response(200, json={"id": "file1"})

    writer = DriveWriter(httpx2.AsyncClient(transport=httpx2.MockTransport(google)), "token")
    assert await writer.move("file1", "stage2") == "file1"
    assert calls[1][0] == "PATCH"
    assert (calls[1][1]["addParents"], calls[1][1]["removeParents"]) == ("stage2", "stage1")
    calls.clear()
    await writer.move("file1", "stage1")  # already there
    assert [method for method, _ in calls] == ["GET"]


# -- Versions (A25, plan section 12) ----------------------------------------------------


async def test_a_new_version_is_saved_as_the_next_and_becomes_current(client, owner, folders):
    key = await file_key(client)
    new = b"%PDF nova"
    opened = await start(client, owner, name="programa revisado.pdf", size=len(new), version_of=key)
    assert opened.status_code == 200, opened.text
    await send(client, opened, new)
    assert (folders / "01 - Briefing" / "Programa v2.pdf").read_bytes() == new
    assert (folders / "01 - Briefing" / "Programa.pdf").read_bytes() == PDF  # never renamed
    stages = (await client.get("/api/pages/casa-jardim/files", headers=ALINEA)).json()["stages"]
    (shown,) = stages[0]["groups"][0]["files"]
    assert (shown["name"], shown["version"], len(shown["older"])) == ("Programa.pdf", 2, 1)
    # And the next one after that, from the current version or an older one alike.
    await send(client, await start(client, owner, version_of=shown["older"][0]["key"]))
    assert (folders / "01 - Briefing" / "Programa v3.pdf").exists()


async def test_a_new_version_goes_into_its_files_own_subfolder(client, owner, folders):
    (folders / "01 - Briefing" / "Plantas").mkdir()
    (folders / "01 - Briefing" / "Plantas" / "Planta v4.pdf").write_bytes(PDF)
    stages = (await client.get("/api/pages/casa-jardim/files", headers=ALINEA)).json()["stages"]
    plantas = next(g for g in stages[0]["groups"] if g["folder"] == "Plantas")
    key = plantas["files"][0]["key"]
    await send(client, await start(client, owner, version_of=key))
    assert (folders / "01 - Briefing" / "Plantas" / "Planta v5.pdf").exists()


async def test_a_new_version_of_another_type_is_refused(client, owner, folders):
    key = await file_key(client)
    response = await start(client, owner, name="Programa.dwg", version_of=key)
    assert (response.status_code, response.json()["error"]) == (422, "version_type_mismatch")


async def test_a_new_version_for_a_file_in_another_stage_is_refused(client, owner, folders):
    key = await file_key(client)  # in stage 1
    response = await start(client, owner, stage=2, version_of=key)
    assert (response.status_code, response.json()["error"]) == (409, "project_changed")


async def test_a_new_version_of_a_file_gone_meanwhile_is_not_found(client, owner, folders):
    key = await file_key(client)
    (folders / "01 - Briefing" / "Programa.pdf").unlink()
    response = await start(client, owner, version_of=key)
    assert (response.status_code, response.json()["error"]) == (404, "file_not_found")


async def test_an_upload_named_like_a_document_never_joins_it_without_yes(client, owner, folders):
    # Its name alone would make it v2 of "Programa.pdf"; that is what "yes" is for.
    await send(client, await start(client, owner, name="Programa v2.pdf"))
    assert sorted(await stage_files(client)) == ["Programa v2 (2).pdf", "Programa.pdf"]


async def check(client, headers, names, stage=1):
    staff = await staff_of(client)
    return await client.post(
        f"/api/projects/{staff['project_id']}/stages/{stage}/uploads/check",
        json={"row_version": staff["row_version"], "names": names},
        headers=headers,
    )


async def test_the_check_names_the_document_a_file_would_be_a_new_version_of(
    client, owner, folders
):
    (folders / "01 - Briefing" / "Programa v2.pdf").write_bytes(PDF)
    response = await check(client, owner, ["programa.pdf", "Fachada.jpg", "Programa v7.pdf"])
    assert response.status_code == 200, response.text
    matches = response.json()["matches"]
    assert [(m["name"], m["document"], m["current"], m["saved_as"]) for m in matches] == [
        ("programa.pdf", "Programa.pdf", "Programa v2.pdf", "Programa v3.pdf"),
        ("Programa v7.pdf", "Programa.pdf", "Programa v2.pdf", "Programa v3.pdf"),
    ]
    assert (matches[0]["current_version"], matches[0]["next_version"]) == (2, 3)
    # "Yes" sends the key it gives: the upload becomes that next version.
    await send(client, await start(client, owner, version_of=matches[0]["key"]))
    assert (folders / "01 - Briefing" / "Programa v3.pdf").exists()


async def test_only_staff_check_names(client, db_session, owner, folders):
    staff = await staff_of(client)
    url = f"/api/projects/{staff['project_id']}/stages/1/uploads/check"
    body = {"row_version": staff["row_version"], "names": ["Programa.pdf"]}
    assert (await client.post(url, json=body, headers=ALINEA)).status_code in (401, 403)
    norte = await sign_in_as(client, db_session, "dona@norte.example", Role.OWNER, NORTE, "norte")
    response = await client.post(url, json=body, headers=norte)
    assert (response.status_code, response.json()["error"]) == (404, "project_not_found")
