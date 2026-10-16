"""Edit mode, part 2: stages (with their folders kept in step) and progress."""

import pytest
from sqlalchemy import text

from backend.projects import creation
from backend.storage.google_connect import ConnectError, ConnectProblem
from backend.tests import test_office
from backend.tests.test_office import ALINEA

owner = test_office.owner  # fixtures

pytestmark = pytest.mark.anyio

SLUG = "casa-jardim"
# The seed binds Casa Jardim's first five stages to these folders.
SEEDED = [
    "01 - Briefing",
    "02 - Conceito",
    "03 - Anteprojeto",
    "04 - Desenvolvimento",
    "05 - Projeto Executivo",
]


@pytest.fixture
def folders(tmp_path):
    for name in SEEDED:
        (tmp_path / "Casa Jardim" / name).mkdir(parents=True)
    (tmp_path / "Casa Jardim" / "02 - Conceito" / "Croqui.pdf").write_bytes(b"%PDF")
    return tmp_path / "Casa Jardim"


def on_disk(folders):
    return sorted(p.name for p in folders.iterdir())


async def page(client):
    return (await client.get(f"/api/pages/{SLUG}", headers=ALINEA)).json()


async def call(client, headers, method, path, **body):
    staff = (await page(client))["staff"]
    url = f"/api/projects/{staff['project_id']}{path}"
    if method == "DELETE":
        return await client.delete(f"{url}?row_version={staff['row_version']}", headers=headers)
    return await client.request(
        method, url, json={"row_version": staff["row_version"], **body}, headers=headers
    )


def titles(shown):
    return [s["title"] for s in shown["stages"]]


# -- stages ---------------------------------------------------------------------------


async def test_adding_a_built_in_stage_creates_its_folder(client, owner, folders):
    response = await call(client, owner, "POST", "/stages", builtin_key="detailing")
    assert response.status_code == 204, response.text
    assert titles(await page(client))[-1] == "Detalhamentos"
    assert "08 - Detalhamentos" in on_disk(folders)


async def test_a_built_in_stage_already_there_or_unknown_is_refused(client, owner, folders):
    for key in ("briefing", "proposal"):
        response = await call(client, owner, "POST", "/stages", builtin_key=key)
        assert (response.status_code, response.json()["error"]) == (422, "invalid_stage")


async def test_the_offices_own_stage_is_added_as_typed(client, owner, folders):
    await call(client, owner, "POST", "/stages", title="Aprovação na prefeitura")
    shown = await page(client)
    assert (shown["stages"][-1]["title"], shown["stages"][-1]["about"]) == (
        "Aprovação na prefeitura",
        None,
    )
    assert "08 - Aprovação na prefeitura" in on_disk(folders)


async def test_renaming_renames_the_folder_and_keeps_the_description(client, owner, folders):
    before = (await page(client))["stages"][1]
    response = await call(client, owner, "PATCH", "/stages/2", title="Medição")
    assert response.status_code == 204, response.text
    after = (await page(client))["stages"][1]
    assert (after["title"], after["about"]) == ("Medição", before["about"])
    assert "02 - Medição" in on_disk(folders) and "02 - Conceito" not in on_disk(folders)
    assert (folders / "02 - Medição" / "Croqui.pdf").exists()  # files move with it


async def test_moving_a_stage_swaps_folders_and_the_current_stage_stays_the_same(
    client, owner, folders
):
    before = await page(client)  # current: 3 (Estudo Preliminar)
    assert (await call(client, owner, "POST", "/stages/3/move", direction=-1)).status_code == 204
    after = await page(client)
    assert titles(after)[1:3] == [titles(before)[2], titles(before)[1]]
    assert after["current_position"] == 2  # still Estudo Preliminar
    assert "02 - Estudo Preliminar" in on_disk(folders)
    assert "03 - Levantamento" in on_disk(folders)


async def test_a_stage_cannot_move_past_the_ends(client, owner, folders):
    response = await call(client, owner, "POST", "/stages/1/move", direction=-1)
    assert (response.status_code, response.json()["error"]) == (422, "invalid_stage")


async def test_removing_a_stage_keeps_its_folder_and_renumbers_the_rest(client, owner, folders):
    assert (await call(client, owner, "DELETE", "/stages/2")).status_code == 204
    shown = await page(client)
    assert len(shown["stages"]) == 6
    assert shown["current_position"] == 2  # the current stage moved up with the rest
    names = on_disk(folders)
    assert "02 - Conceito" in names  # the removed stage's folder and files stay
    assert (folders / "02 - Conceito" / "Croqui.pdf").exists()
    assert "02 - Estudo Preliminar" in names  # was 03


async def test_if_drive_fails_nothing_changes_and_names_are_put_back(
    client, db_session, owner, folders, monkeypatch, caplog
):
    real = creation.LocalFolders.rename
    calls = []

    async def second_fails(self, item_id, name):
        calls.append(name)
        if len(calls) == 2:
            raise ConnectError(ConnectProblem.FOLDER_FAILED, "simulated")
        return await real(self, item_id, name)

    monkeypatch.setattr(creation.LocalFolders, "rename", second_fails)
    before = await page(client)
    response = await call(client, owner, "POST", "/stages/3/move", direction=-1)
    assert (response.status_code, response.json()) == (503, {"error": "drive_connect_failed"})
    assert titles(await page(client)) == titles(before)
    assert on_disk(folders) == sorted(SEEDED)  # the first rename was put back
    # The detail goes to the log with the office and the operation, for support.
    logged = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    tenant = await db_session.scalar(text("SELECT id FROM tenants WHERE slug = 'alinea'"))
    assert any(
        "move stage" in m
        and "simulated" in m
        and str(tenant) in m
        and before["staff"]["project_id"] in m
        for m in logged
    )


async def test_a_stale_page_cant_change_stages(client, owner, folders):
    stale = (await page(client))["staff"]
    await call(client, owner, "PATCH", "/stages/1", title="Conversa inicial")
    response = await client.post(
        f"/api/projects/{stale['project_id']}/stages/2/move",
        json={"row_version": stale["row_version"], "direction": 1},
        headers=owner,
    )
    assert (response.status_code, response.json()["error"]) == (409, "project_changed")


# -- progress -------------------------------------------------------------------------


async def test_advancing_and_going_back_move_the_current_stage(client, owner, folders):
    before = await page(client)
    assert (await call(client, owner, "POST", "/progress", action="advance")).status_code == 204
    after = await page(client)
    assert after["current_position"] == before["current_position"] + 1
    assert after["last_update"] != before["last_update"]  # the client notices this
    await call(client, owner, "POST", "/progress", action="back")
    assert (await page(client))["current_position"] == before["current_position"]


async def test_completing_and_reopening(client, owner, folders):
    await call(client, owner, "POST", "/progress", action="complete")
    assert (await page(client))["completed"] is True
    again = await call(client, owner, "POST", "/progress", action="complete")
    assert again.status_code == 422
    await call(client, owner, "POST", "/progress", action="reopen")
    assert (await page(client))["completed"] is False


async def test_no_advancing_past_the_last_stage(client, owner, folders):
    for _ in range(4):  # 3 -> 7
        await call(client, owner, "POST", "/progress", action="advance")
    response = await call(client, owner, "POST", "/progress", action="advance")
    assert (response.status_code, response.json()["error"]) == (422, "invalid_status_change")


async def test_a_stage_whose_folder_is_gone_can_still_be_renamed(client, owner, folders):
    """Staff deleted the folder in Drive by hand: the stage still changes."""
    (folders / "02 - Conceito" / "Croqui.pdf").unlink()
    (folders / "02 - Conceito").rmdir()
    response = await call(client, owner, "PATCH", "/stages/2", title="Medição")
    assert response.status_code == 204, response.text
    assert (await page(client))["stages"][1]["title"] == "Medição"
