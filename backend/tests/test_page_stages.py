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


def completed(shown):
    return [s["completed"] for s in shown["stages"]]


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


async def test_moving_a_stage_swaps_folders_and_each_keeps_its_completion(client, owner, folders):
    before = await page(client)  # 01 and 02 completed
    assert (await call(client, owner, "POST", "/stages/3/move", direction=-1)).status_code == 204
    after = await page(client)
    assert titles(after)[1:3] == [titles(before)[2], titles(before)[1]]
    assert completed(after)[:3] == [True, False, True]  # Estudo Preliminar, still open, moved up
    assert "02 - Estudo Preliminar" in on_disk(folders)
    assert "03 - Levantamento" in on_disk(folders)


async def test_a_stage_cannot_move_past_the_ends(client, owner, folders):
    response = await call(client, owner, "POST", "/stages/1/move", direction=-1)
    assert (response.status_code, response.json()["error"]) == (422, "invalid_stage")


async def test_reordering_puts_every_stage_in_place_with_its_completion(client, owner, folders):
    before = await page(client)  # 01 and 02 completed
    count = len(before["stages"])
    order = [3, 1, 2, *range(4, count + 1)]
    response = await call(client, owner, "PUT", "/stages/order", order=order)
    assert response.status_code == 204, response.text
    after = await page(client)
    assert titles(after) == [titles(before)[n - 1] for n in order]
    assert completed(after) == [completed(before)[n - 1] for n in order]
    names = on_disk(folders)
    assert {"01 - Estudo Preliminar", "02 - Briefing", "03 - Levantamento"} <= set(names)
    assert "04 - Desenvolvimento" in names  # unmoved stages keep their folders
    assert (folders / "03 - Levantamento" / "Croqui.pdf").exists()  # files move with it


async def test_an_unchanged_order_changes_nothing(client, owner, folders):
    before = await page(client)
    order = list(range(1, len(before["stages"]) + 1))
    assert (await call(client, owner, "PUT", "/stages/order", order=order)).status_code == 204
    assert titles(await page(client)) == titles(before)
    assert on_disk(folders) == sorted(SEEDED)


@pytest.mark.parametrize(
    "order",
    [
        lambda n: list(range(1, n)),  # one left out
        lambda n: [1, 1, *range(3, n + 1)],  # one twice
        lambda n: [*range(1, n + 1), n + 1],  # one that isn't there
    ],
    ids=["missing", "repeated", "unknown"],
)
async def test_an_order_must_name_every_stage_once(client, owner, folders, order):
    before = await page(client)
    count = len(before["stages"])
    response = await call(client, owner, "PUT", "/stages/order", order=order(count))
    assert (response.status_code, response.json()["error"]) == (422, "invalid_stage")
    assert titles(await page(client)) == titles(before)


async def test_a_stale_page_cant_reorder(client, owner, folders):
    stale = (await page(client))["staff"]
    count = len((await page(client))["stages"])
    await call(client, owner, "PATCH", "/stages/1", title="Conversa inicial")
    response = await client.put(
        f"/api/projects/{stale['project_id']}/stages/order",
        json={"row_version": stale["row_version"], "order": [2, 1, *range(3, count + 1)]},
        headers=owner,
    )
    assert (response.status_code, response.json()["error"]) == (409, "project_changed")


async def test_if_drive_fails_while_reordering_nothing_changes(client, owner, folders, monkeypatch):
    real = creation.LocalFolders.rename
    calls = []

    async def third_fails(self, item_id, name):
        calls.append(name)
        if len(calls) == 3:
            raise ConnectError(ConnectProblem.FOLDER_FAILED, "simulated")
        return await real(self, item_id, name)

    monkeypatch.setattr(creation.LocalFolders, "rename", third_fails)
    before = await page(client)
    count = len(before["stages"])
    response = await call(
        client, owner, "PUT", "/stages/order", order=[3, 1, 2, *range(4, count + 1)]
    )
    assert (response.status_code, response.json()) == (503, {"error": "drive_connect_failed"})
    assert titles(await page(client)) == titles(before)
    assert on_disk(folders) == sorted(SEEDED)  # the two renames done were put back


async def test_only_staff_reorder(client, owner, folders):
    staff = (await page(client))["staff"]
    count = len((await page(client))["stages"])
    response = await client.put(
        f"/api/projects/{staff['project_id']}/stages/order",
        json={"row_version": staff["row_version"], "order": [2, 1, *range(3, count + 1)]},
        headers=ALINEA,  # no session's CSRF token
    )
    assert response.status_code in (401, 403)
    assert on_disk(folders) == sorted(SEEDED)


async def test_removing_a_stage_keeps_its_folder_and_renumbers_the_rest(client, owner, folders):
    assert (await call(client, owner, "DELETE", "/stages/2")).status_code == 204
    shown = await page(client)
    assert len(shown["stages"]) == 6
    assert completed(shown)[:2] == [True, False]  # the rest moved up, completion and all
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


# -- completion -----------------------------------------------------------------------


async def test_stages_are_completed_and_reopened_in_any_order(client, owner, folders):
    before = await page(client)  # 01 and 02 completed
    response = await call(client, owner, "PUT", "/stages/5/completion", completed=True)
    assert response.status_code == 204, response.text
    after = await page(client)
    assert completed(after) == [True, True, False, False, True, False, False]
    assert after["last_update"] != before["last_update"]  # the client notices this
    assert after["completed"] is False
    await call(client, owner, "PUT", "/stages/1/completion", completed=False)
    assert completed(await page(client)) == [False, True, False, False, True, False, False]


async def kinds(db_session):
    return (await db_session.execute(text("SELECT kind FROM project_events"))).scalars().all()


async def test_staff_complete_the_project_once_every_stage_is(client, db_session, owner, folders):
    """Completing the last stage leaves the project to staff: they are asked, and
    only "Concluir projeto" completes it and tells the client (Fabio, 23 Oct 2026)."""
    early = await call(client, owner, "PUT", "/completion")
    assert (early.status_code, early.json()["error"]) == (
        422,
        "invalid_status_change",
    )  # open stages
    for position in range(3, 8):
        await call(client, owner, "PUT", f"/stages/{position}/completion", completed=True)
    assert (await page(client))["completed"] is False  # every stage, not yet the project
    assert "project_completed" not in await kinds(db_session)
    response = await call(client, owner, "PUT", "/completion")
    assert response.status_code == 204, response.text
    assert (await page(client))["completed"] is True
    assert "project_completed" in await kinds(db_session)
    again = await call(client, owner, "PUT", "/completion")
    assert (again.status_code, again.json()["error"]) == (422, "invalid_status_change")
    # Reopening a stage makes the project active again.
    await call(client, owner, "PUT", "/stages/2/completion", completed=False)
    shown = await page(client)
    assert (shown["completed"], completed(shown)[1]) == (False, False)


async def complete_all(client, owner):
    for position in range(3, 8):
        await call(client, owner, "PUT", f"/stages/{position}/completion", completed=True)
    await call(client, owner, "PUT", "/completion")
    assert (await page(client))["completed"] is True


async def test_adding_a_stage_to_a_completed_project_makes_it_active_again(client, owner, folders):
    await complete_all(client, owner)
    response = await call(client, owner, "POST", "/stages", title="Visita técnica")
    assert response.status_code == 204, response.text
    shown = await page(client)
    assert (shown["completed"], completed(shown)[-1]) == (False, False)


async def test_removing_the_last_open_stage_leaves_the_project_to_staff(
    client, db_session, owner, folders
):
    for position in range(3, 7):  # all but 07
        await call(client, owner, "PUT", f"/stages/{position}/completion", completed=True)
    assert (await call(client, owner, "DELETE", "/stages/7")).status_code == 204
    assert (await page(client))["completed"] is False  # "Concluir projeto" is theirs to press
    assert "project_completed" not in await kinds(db_session)
    assert (await call(client, owner, "PUT", "/completion")).status_code == 204


async def test_the_previous_releases_progress_still_works_for_one_release(client, owner, folders):
    """A tab still running the previous release during a deploy (A30)."""
    assert (await page(client))["current_position"] == 3  # the first stage still open
    response = await call(client, owner, "POST", "/progress", action="advance")
    assert response.status_code == 204, response.text
    shown = await page(client)
    assert (completed(shown)[:4], shown["current_position"]) == ([True, True, True, False], 4)
    await call(client, owner, "POST", "/progress", action="back")  # the last completed
    assert completed(await page(client))[:4] == [True, True, False, False]
    for _ in range(4):  # 03 to 06
        await call(client, owner, "POST", "/progress", action="advance")
    # "complete" on the last stage: it and the project, as the previous release did.
    response = await call(client, owner, "POST", "/progress", action="complete")
    assert response.status_code == 204, response.text
    shown = await page(client)
    assert (shown["completed"], shown["current_position"]) == (True, 7)
    await call(client, owner, "POST", "/progress", action="reopen")
    shown = await page(client)
    assert (shown["completed"], completed(shown)[-1]) == (False, False)


async def test_completing_a_completed_stage_or_reopening_an_open_one_is_refused(
    client, owner, folders
):
    for position, value in ((1, True), (3, False)):
        response = await call(
            client, owner, "PUT", f"/stages/{position}/completion", completed=value
        )
        assert (response.status_code, response.json()["error"]) == (422, "invalid_status_change")


async def test_completing_a_stage_that_isnt_there_is_not_found(client, owner, folders):
    response = await call(client, owner, "PUT", "/stages/9/completion", completed=True)
    assert response.status_code == 404


async def test_a_stage_whose_folder_is_gone_can_still_be_renamed(client, owner, folders):
    """Staff deleted the folder in Drive by hand: the stage still changes."""
    (folders / "02 - Conceito" / "Croqui.pdf").unlink()
    (folders / "02 - Conceito").rmdir()
    response = await call(client, owner, "PATCH", "/stages/2", title="Medição")
    assert response.status_code == 204, response.text
    assert (await page(client))["stages"][1]["title"] == "Medição"


async def test_if_saving_a_new_stage_fails_its_new_folder_goes_too(
    client, owner, folders, monkeypatch
):
    from sqlalchemy.ext.asyncio import AsyncSession

    real_commit = AsyncSession.commit

    async def fails(self):
        """Fails the save that comes after Drive made the new folder."""
        if (folders / "08 - Detalhamentos").exists():
            raise RuntimeError("database went away")
        await real_commit(self)

    before = on_disk(folders)
    staff = (await page(client))["staff"]
    monkeypatch.setattr(AsyncSession, "commit", fails)
    try:
        response = await client.post(
            f"/api/projects/{staff['project_id']}/stages",
            json={"row_version": staff["row_version"], "builtin_key": "detailing"},
            headers=owner,
        )
        assert response.status_code == 500
    except RuntimeError:
        pass  # the test client may pass the server error on as raised
    monkeypatch.undo()
    assert on_disk(folders) == before  # "08 - Detalhamentos" was made, then trashed


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/stages", {"title": "Nova"}),
        ("PATCH", "/stages/1", {"title": "Outro nome"}),
        ("POST", "/stages/1/move", {"direction": 1}),
        ("DELETE", "/stages/1", {}),
        ("PUT", "/stages/3/completion", {"completed": True}),
        ("PUT", "/completion", {}),
    ],
)
async def test_an_archived_projects_stages_cant_change(
    client, db_session, owner, folders, method, path, body
):
    await db_session.execute(
        text(
            "UPDATE projects SET status = 'archived', archived_from = 'active' WHERE name = "
            "'Casa Jardim' AND tenant_id = (SELECT id FROM tenants WHERE slug = 'alinea')"
        )
    )
    before = await page(client)
    response = await call(client, owner, method, path, **body)
    assert (response.status_code, response.json()["error"]) == (409, "project_archived")
    after = await page(client)
    assert (titles(after), completed(after)) == (titles(before), completed(before))
    assert on_disk(folders) == sorted(SEEDED)
