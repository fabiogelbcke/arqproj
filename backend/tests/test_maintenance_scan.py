"""The maintenance scan (A10) and the client-visible changes it and staff record
(A28, A32)."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.notifications import scan
from backend.notifications.scan import MAINTENANCE_LOCK, run_maintenance
from backend.storage.base import StorageError, StorageProblem
from backend.tests import test_office
from backend.tests.conftest import TEST_DATABASE_URL
from backend.tests.test_office import ALINEA

owner = test_office.owner  # fixtures

pytestmark = pytest.mark.anyio

PDF = b"%PDF-1.4"
CASA = (
    "(SELECT id FROM projects WHERE name = 'Casa Jardim' AND tenant_id = "
    "(SELECT id FROM tenants WHERE slug = 'alinea'))"
)


@pytest.fixture
def folders(tmp_path):
    """Casa Jardim's first stage folders (as the seed binds them), one file each."""
    briefing = tmp_path / "Casa Jardim" / "01 - Briefing"
    briefing.mkdir(parents=True)
    (briefing / "Programa.pdf").write_bytes(PDF)
    (tmp_path / "Casa Jardim" / "02 - Conceito").mkdir()
    return tmp_path / "Casa Jardim"


async def run(app):
    return await run_maintenance(app.state.sessionmaker, app.state.settings, None)


async def events(db_session, project=CASA):
    rows = await db_session.execute(
        text(
            "SELECT kind, stage_position, title FROM project_events "
            f"WHERE project_id = {project} ORDER BY occurred_at, kind"
        )
    )
    return [tuple(row) for row in rows]


async def casa(db_session, column):
    return await db_session.scalar(text(f"SELECT {column} FROM projects WHERE id = {CASA}"))


# -- the scan -------------------------------------------------------------------------


async def test_a_first_scan_only_notes_what_is_there(app, db_session, owner, folders):
    await run(app)
    assert await events(db_session) == []  # existing files never email
    assert await casa(db_session, "files_scanned_at") is not None


async def test_a_file_shown_for_the_first_time_is_recorded_once(app, db_session, owner, folders):
    await run(app)
    before = await casa(db_session, "last_activity_at")
    (folders / "02 - Conceito" / "Croqui.pdf").write_bytes(PDF)
    report = await run(app)
    assert await events(db_session) == [("file_published", 2, "Croqui.pdf")]
    assert report.new_files >= 1
    assert await casa(db_session, "last_activity_at") != before  # "Atualizado" moves
    await run(app)
    assert len(await events(db_session)) == 1  # not again


async def test_a_quiet_pass_writes_nothing(app, db_session, owner, folders):
    """A project's `updated_at` versions its cover's address: a pass with nothing
    new must not move it."""
    await run(app)
    updated = await casa(db_session, "updated_at")
    await run(app)
    assert await casa(db_session, "updated_at") == updated


async def test_only_what_clients_see_counts(app, db_session, owner, folders):
    await run(app)
    briefing = folders / "01 - Briefing"
    (briefing / "_interno.pdf").write_bytes(PDF)  # hidden name
    (briefing / "Fotos").mkdir()
    (briefing / "Fotos" / "Terreno.jpg").write_bytes(b"jpg")  # a subfolder: shown
    (briefing / "Fotos" / "Antigas").mkdir()
    (briefing / "Fotos" / "Antigas" / "Velha.jpg").write_bytes(b"jpg")  # too deep
    await run(app)
    assert await events(db_session) == [("file_published", 1, "Terreno.jpg")]


async def test_a_stage_folder_moved_out_of_the_project_is_not_scanned(
    app, db_session, owner, folders
):
    await run(app)
    (folders.parent / "Outro").mkdir()
    (folders / "02 - Conceito").rename(folders.parent / "Outro" / "02 - Conceito")
    (folders.parent / "Outro" / "02 - Conceito" / "Alheio.pdf").write_bytes(PDF)
    await run(app)
    assert await events(db_session) == []


async def test_drafts_are_not_scanned(app, db_session, owner, folders):
    await db_session.execute(text(f"UPDATE projects SET status = 'draft' WHERE id = {CASA}"))
    await run(app)
    assert await casa(db_session, "files_scanned_at") is None


async def test_one_project_failing_is_logged_and_the_rest_go_on(
    app, db_session, owner, folders, monkeypatch, caplog
):
    real = scan.stage_groups

    async def fails_for_briefing(storage, folder):
        if folder.endswith("01 - Briefing"):
            raise StorageError(StorageProblem.UNAVAILABLE, "Drive said 503")
        return await real(storage, folder)

    monkeypatch.setattr(scan, "stage_groups", fails_for_briefing)
    report = await run(app)
    assert report.failed >= 1
    assert await casa(db_session, "files_scanned_at") is None  # tried again next pass
    logged = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    assert any("scanning files" in m and "Drive said 503" in m for m in logged)


async def test_a_project_another_pass_is_scanning_is_skipped(app, db_session, owner, folders):
    """Two Cloud Run instances may run a pass at once: each project is scanned by
    one of them, under a lock that holds across connections."""
    other = create_async_engine(TEST_DATABASE_URL)
    try:
        async with other.connect() as holder, holder.begin():
            project = await db_session.scalar(text(f"SELECT {CASA}"))
            await holder.execute(
                text("SELECT pg_advisory_xact_lock(:key, hashtext(:project))"),
                {"key": MAINTENANCE_LOCK, "project": str(project)},
            )
            report = await run(app)
            assert report.busy == 1
            assert await casa(db_session, "files_scanned_at") is None
    finally:
        await other.dispose()
    await run(app)
    assert await casa(db_session, "files_scanned_at") is not None


# -- what staff do --------------------------------------------------------------------


async def page(client):
    return (await client.get("/api/pages/casa-jardim", headers=ALINEA)).json()


async def call(client, headers, method, path, **body):
    staff = (await page(client))["staff"]
    url = f"/api/projects/{staff['project_id']}{path}"
    if method == "DELETE":
        return await client.delete(f"{url}?row_version={staff['row_version']}", headers=headers)
    return await client.request(
        method, url, json={"row_version": staff["row_version"], **body}, headers=headers
    )


async def test_advancing_and_completing_are_recorded_going_back_is_not(
    client, db_session, owner, folders
):
    current = (await page(client))["current_position"]
    await call(client, owner, "POST", "/progress", action="advance")
    await call(client, owner, "POST", "/progress", action="back")
    title = (await page(client))["stages"][current]["title"]
    assert await events(db_session) == [("stage_advanced", current + 1, title)]
    await db_session.execute(text(f"UPDATE projects SET current_position = 7 WHERE id = {CASA}"))
    completed = await call(client, owner, "POST", "/progress", action="complete")
    assert completed.status_code == 204, completed.text
    # (One test transaction: every event has the same time, so not in order here.)
    assert sorted(await events(db_session)) == [
        ("project_completed", None, None),
        ("stage_advanced", current + 1, title),
    ]


async def test_meetings_and_notes_are_recorded(client, db_session, owner, folders):
    from datetime import date, timedelta

    day = (date.today() + timedelta(days=5)).isoformat()
    await call(client, owner, "PUT", "/meeting", title="Visita", day=day, start="10:00")
    await call(client, owner, "PUT", "/meeting", title="Visita à obra", day=day, start="11:00")
    await call(client, owner, "DELETE", "/meeting")
    await call(client, owner, "PUT", "/stages/2/notes", notes="Confira as medidas.")
    kinds = [kind for kind, _, _ in await events(db_session)]
    # Casa Jardim's seed meeting is the upcoming one: the first PUT changes it.
    assert kinds == ["meeting_changed", "meeting_changed", "meeting_cleared", "note_changed"]


async def test_a_drafts_changes_are_not_recorded(client, db_session, owner, folders):
    await db_session.execute(text(f"UPDATE projects SET status = 'draft' WHERE id = {CASA}"))
    await call(client, owner, "POST", "/progress", action="advance")
    await call(client, owner, "PUT", "/stages/2/notes", notes="Rascunho.")
    assert await events(db_session) == []
