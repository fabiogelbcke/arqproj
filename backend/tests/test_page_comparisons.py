"""Before-and-after comparisons on the project page (A46): listed from names,
uploaded as a pair, and changed as one."""

import os

import pytest
from sqlalchemy import text

from backend.identity.models import Role
from backend.projects import creation
from backend.tests import test_office, test_page_uploads
from backend.tests.test_office import ALINEA, sign_in_as
from backend.tests.test_page_uploads import send, staff_of

owner = test_office.owner  # fixtures
folders = test_page_uploads.folders

pytestmark = pytest.mark.anyio

JPEG = b"\xff\xd8\xff\xe0 jpeg"


async def switch(db, on: bool):
    """The `before_after` feature (A40), for Alinea."""
    change = (
        "array_append(features, 'before_after')" if on else "array_remove(features, 'before_after')"
    )
    await db.execute(text(f"UPDATE tenants SET features = {change} WHERE slug = 'alinea'"))


@pytest.fixture(autouse=True)
async def switched_on(owner, db_session):
    """Comparisons are a feature switched on per office: on for these tests."""
    await switch(db_session, on=True)


def put(folder, *names):
    for name in names:
        (folder / name).write_bytes(JPEG)


async def cards(client, position=1, headers=ALINEA):
    stages = (await client.get("/api/pages/casa-jardim/files", headers=headers)).json()["stages"]
    return [f for g in stages[position - 1]["groups"] for f in g["files"]]


async def card(client, title, position=1):
    return next(f for f in await cards(client, position) if f["name"] == title)


async def start(client, headers, stage=1, **changes):
    staff = await staff_of(client)
    body = {
        "row_version": staff["row_version"],
        "title": "Cozinha",
        "before": {"name": "IMG_0001.JPG", "size": len(JPEG), "mime_type": "image/jpeg"},
        "after": {"name": "render final.png", "size": len(JPEG), "mime_type": "image/png"},
    } | changes
    return await client.post(
        f"/api/projects/{staff['project_id']}/stages/{stage}/comparisons",
        json=body,
        headers=headers,
    )


async def upload(client, headers, **changes):
    opened = await start(client, headers, **changes)
    assert opened.status_code == 200, opened.text
    for side in ("before_url", "after_url"):
        sent = await client.put(opened.json()[side], content=JPEG, headers={"host": ALINEA["host"]})
        assert sent.status_code == 201
    return opened


# -- On the page -----------------------------------------------------------------------


async def test_two_images_named_for_a_comparison_show_as_one_card(client, owner, folders):
    put(folders / "01 - Briefing", "Cozinha (antes).jpg", "Cozinha (depois - Obra).jpg")
    found = await cards(client)
    assert sorted(f["name"] for f in found) == ["Cozinha", "Programa.pdf"]
    comparison = next(f for f in found if f["name"] == "Cozinha")["comparison"]
    assert comparison["before_name"] == "Cozinha (antes).jpg"
    assert comparison["after_name"] == "Cozinha (depois - Obra).jpg"
    assert (comparison["before_label"], comparison["after_label"]) == (None, "Obra")
    assert comparison["after"]["kind"] == "image"


async def test_the_card_is_dated_by_its_newer_side(client, owner, folders):
    stage = folders / "01 - Briefing"
    put(stage, "Cozinha (antes).jpg", "Cozinha (depois).jpg")
    os.utime(stage / "Cozinha (antes).jpg", (1_700_000_000, 1_700_000_000))
    found = await card(client, "Cozinha")
    assert found["modified_at"] == found["comparison"]["after"]["modified_at"]
    assert found["modified_at"] > "2024"


async def test_both_sides_open_by_their_keys(client, owner, folders):
    put(folders / "01 - Briefing", "Cozinha (antes).jpg", "Cozinha (depois).jpg")
    found = await card(client, "Cozinha")
    for key in (found["key"], found["comparison"]["after"]["key"]):
        opened = await client.get(f"/api/pages/casa-jardim/files/{key}?inline=1", headers=ALINEA)
        assert (opened.status_code, opened.content) == (200, JPEG)


async def test_a_lone_side_shows_as_a_plain_file(client, owner, folders):
    put(folders / "01 - Briefing", "Cozinha (antes).jpg")
    found = await card(client, "Cozinha (antes).jpg")
    assert found["comparison"] is None


async def test_a_new_comparison_is_one_entry_in_the_updates(app, client, owner, folders):
    from backend.tests.test_maintenance_scan import run

    await run(app)  # notes what's there
    await upload(client, owner)
    await run(app)
    updates = (await client.get("/api/pages/casa-jardim/files", headers=ALINEA)).json()["updates"]
    assert [(u["kind"], u["name"], u["comparison"]) for u in updates] == [
        ("file_published", "Cozinha", True)
    ]


async def test_two_comparisons_of_one_title_in_two_sections_are_two_updates(
    app, client, owner, folders
):
    from backend.tests.test_maintenance_scan import run

    await run(app)  # notes what's there
    (folders / "01 - Briefing" / "Renders").mkdir()
    await upload(client, owner)
    await upload(client, owner, folder="Renders")
    await run(app)
    updates = (await client.get("/api/pages/casa-jardim/files", headers=ALINEA)).json()["updates"]
    assert [(u["name"], u["comparison"]) for u in updates] == [("Cozinha", True)] * 2


# -- "Comparação antes e depois" --------------------------------------------------------


async def test_both_images_go_up_named_so_the_page_pairs_them(client, owner, folders):
    await upload(client, owner, before_label=" Projeto ")
    stage = folders / "01 - Briefing"
    assert (stage / "Cozinha (antes - Projeto).jpg").read_bytes() == JPEG
    assert (stage / "Cozinha (depois).png").exists()
    found = await card(client, "Cozinha")
    assert found["comparison"]["before_label"] == "Projeto"


async def test_members_upload_comparisons_too(client, db_session, owner, folders):
    member = await sign_in_as(client, db_session, "membro@alinea.example", Role.MEMBER)
    assert (await start(client, member)).status_code == 200


async def test_a_comparison_goes_into_a_section(client, owner, folders):
    (folders / "01 - Briefing" / "Renders").mkdir()
    await upload(client, owner, folder="Renders")
    assert (folders / "01 - Briefing" / "Renders" / "Cozinha (antes).jpg").exists()


async def test_an_english_office_writes_english_markers(client, db_session, owner, folders):
    from sqlalchemy import text

    await db_session.execute(text("UPDATE tenants SET locale = 'en' WHERE slug = 'alinea'"))
    await upload(client, owner)
    assert (folders / "01 - Briefing" / "Cozinha (before).jpg").exists()
    assert (folders / "01 - Briefing" / "Cozinha (after).png").exists()


@pytest.mark.parametrize(
    ("changes", "status", "error"),
    [
        ({"title": "  "}, 422, "comparison_title_invalid"),
        ({"title": "_Rascunho"}, 422, "comparison_title_invalid"),
        ({"title": "x" * 121}, 422, "comparison_title_invalid"),
        (
            {"after": {"name": "Planta.pdf", "size": 3, "mime_type": "application/pdf"}},
            422,
            "comparison_not_image",
        ),
        (
            {"before": {"name": "a.heic", "size": 3, "mime_type": "image/heic"}},
            422,
            "comparison_not_image",
        ),
        (
            {"before": {"name": "a.jpg", "size": 101 * 1024 * 1024, "mime_type": "image/jpeg"}},
            422,
            "file_too_large",
        ),
        ({"row_version": -1}, 409, "project_changed"),
        ({"folder": "Não existe"}, 404, "folder_not_found"),
    ],
)
async def test_a_comparison_that_cant_go_is_refused_before_anything_is_sent(
    client, owner, folders, changes, status, error
):
    response = await start(client, owner, **changes)
    assert (response.status_code, response.json()["error"]) == (status, error)


@pytest.mark.parametrize(
    "changes",
    [
        {"before_label": "Projeto v2"},
        {"after_label": "Render V3"},
        {"title": "Sala", "after_label": "(v4"},
    ],
)
async def test_a_name_that_wouldnt_read_back_as_its_comparison_is_refused(
    client, owner, folders, changes
):
    """A label ending like a version would be read as one (A25), taking the
    marker's bracket with it: the two images would show apart."""
    response = await start(client, owner, **changes)
    assert (response.status_code, response.json()["error"]) == (422, "comparison_label_invalid")


async def test_editing_to_a_label_that_wouldnt_read_back_renames_nothing(client, owner, folders):
    put(folders / "01 - Briefing", "Cozinha (antes).jpg", "Cozinha (depois).jpg")
    key = (await card(client, "Cozinha"))["key"]
    response = await act(client, owner, "edit", key, title="Cozinha", after_label="Obra v2")
    assert (response.status_code, response.json()["error"]) == (422, "comparison_label_invalid")
    assert (folders / "01 - Briefing" / "Cozinha (depois).jpg").exists()


@pytest.mark.parametrize("there", ["Cozinha (antes).jpg", "cozinha (depois - Obra).png"])
async def test_a_title_already_compared_in_the_folder_is_refused(client, owner, folders, there):
    """A third side would leave every one of them unpaired."""
    put(folders / "01 - Briefing", there)
    response = await start(client, owner)
    assert (response.status_code, response.json()["error"]) == (409, "comparison_exists")


async def test_a_comparison_whose_after_broke_off_is_finished_with_the_after_alone(
    client, owner, folders
):
    """The first try's "before" went up; the retry sends only the "after"."""
    opened = await start(client, owner)
    await client.put(opened.json()["before_url"], content=JPEG, headers={"host": ALINEA["host"]})
    for again in ({}, {"before": None}):  # both again, or the side already there
        refused = await start(client, owner, **({"after": None} if again else {}))
        assert (refused.status_code, refused.json()["error"]) == (409, "comparison_exists")
    finished = await start(client, owner, before=None)
    assert finished.status_code == 200, finished.text
    assert finished.json()["before_url"] is None
    sent = await client.put(
        finished.json()["after_url"], content=JPEG, headers={"host": ALINEA["host"]}
    )
    assert sent.status_code == 201
    assert (await card(client, "Cozinha"))["comparison"]["after_name"] == "Cozinha (depois).png"


async def test_one_side_alone_is_refused_where_the_other_isnt_there(client, owner, folders):
    response = await start(client, owner, before=None)
    assert (response.status_code, response.json()["error"]) == (409, "comparison_exists")
    neither = await start(client, owner, before=None, after=None)
    assert neither.status_code == 422


async def test_the_same_title_in_another_section_is_fine(client, owner, folders):
    put(folders / "01 - Briefing", "Cozinha (antes).jpg", "Cozinha (depois).jpg")
    (folders / "01 - Briefing" / "Renders").mkdir()
    assert (await start(client, owner, folder="Renders")).status_code == 200


async def test_only_staff_upload_comparisons(client, owner, folders):
    response = await start(client, ALINEA)
    assert response.status_code in (401, 403)


async def test_a_new_version_of_one_side_keeps_the_comparison(client, owner, folders):
    from backend.tests.test_page_uploads import start as start_upload

    await upload(client, owner)
    after = (await card(client, "Cozinha"))["comparison"]["after"]
    opened = await start_upload(
        client, owner, name="outro.png", size=len(JPEG), version_of=after["key"]
    )
    assert opened.status_code == 200, opened.text
    await send(client, opened, JPEG)
    assert (folders / "01 - Briefing" / "Cozinha (depois) v2.png").exists()
    assert (await card(client, "Cozinha"))["comparison"]["after"]["version"] == 2


# -- Changing one ------------------------------------------------------------------------


async def act(client, headers, action, key, **body):
    return await client.post(
        f"/api/pages/casa-jardim/comparisons/{key}/{action}", json=body or None, headers=headers
    )


async def test_editing_renames_every_version_of_both_sides(client, owner, folders):
    stage = folders / "01 - Briefing"
    put(stage, "Cozinha (antes).jpg", "Cozinha (antes) v2.jpg", "Cozinha (depois).jpg")
    key = (await card(client, "Cozinha"))["key"]
    response = await act(
        client, owner, "edit", key, title="Copa", before_label="Projeto", after_label=""
    )
    assert response.status_code == 204, response.text
    assert sorted(p.name for p in stage.iterdir() if p.suffix == ".jpg") == [
        "Copa (antes - Projeto) v2.jpg",
        "Copa (antes - Projeto).jpg",
        "Copa (depois).jpg",
    ]
    found = await card(client, "Copa")
    assert (found["version"], found["comparison"]["before_label"]) == (2, "Projeto")


async def test_editing_to_a_title_compared_beside_it_is_refused(client, owner, folders):
    put(
        folders / "01 - Briefing", "Cozinha (antes).jpg", "Cozinha (depois).jpg", "Copa (antes).jpg"
    )
    key = (await card(client, "Cozinha"))["key"]
    response = await act(client, owner, "edit", key, title="copa")
    assert (response.status_code, response.json()["error"]) == (409, "comparison_exists")


async def test_editing_only_its_labels_keeps_its_title(client, owner, folders):
    put(folders / "01 - Briefing", "Cozinha (antes).jpg", "Cozinha (depois).jpg")
    key = (await card(client, "Cozinha"))["key"]
    assert (
        await act(client, owner, "edit", key, title="Cozinha", after_label="Obra")
    ).status_code == 204
    assert (folders / "01 - Briefing" / "Cozinha (depois - Obra).jpg").exists()


async def test_hiding_hides_every_version_of_both_sides(client, owner, folders):
    stage = folders / "01 - Briefing"
    put(stage, "Cozinha (antes).jpg", "Cozinha (antes) v2.jpg", "Cozinha (depois).jpg")
    key = (await card(client, "Cozinha"))["key"]
    assert (await act(client, owner, "hide", key)).status_code == 204
    assert [f["name"] for f in await cards(client)] == ["Programa.pdf"]  # no older version shows
    assert (stage / "_Cozinha (antes).jpg").exists()  # still in Drive


async def test_moving_takes_both_sides_to_the_other_stage(client, owner, folders):
    put(folders / "01 - Briefing", "Cozinha (antes).jpg", "Cozinha (depois).jpg")
    key = (await card(client, "Cozinha"))["key"]
    row_version = (await staff_of(client))["row_version"]
    response = await act(client, owner, "move", key, position=2, row_version=row_version)
    assert response.status_code == 204, response.text
    assert [f["name"] for f in await cards(client, 2)] == ["Cozinha"]
    assert [f["name"] for f in await cards(client, 1)] == ["Programa.pdf"]


async def test_moving_where_that_title_is_compared_is_refused(client, owner, folders):
    put(folders / "01 - Briefing", "Cozinha (antes).jpg", "Cozinha (depois).jpg")
    put(folders / "02 - Conceito", "Cozinha (antes).jpg")
    key = (await card(client, "Cozinha"))["key"]
    row_version = (await staff_of(client))["row_version"]
    response = await act(client, owner, "move", key, position=2, row_version=row_version)
    assert (response.status_code, response.json()["error"]) == (409, "comparison_exists")
    assert (folders / "01 - Briefing" / "Cozinha (depois).jpg").exists()


async def test_one_side_put_straight_into_drive_stops_any_change(
    client, owner, folders, monkeypatch
):
    """drive.file: nothing is changed unless the app may change both sides, so a
    comparison is never left half renamed."""
    stage = folders / "01 - Briefing"
    put(stage, "Cozinha (antes).jpg", "Cozinha (depois).jpg")
    ours = creation.LocalFolders.can_rename

    async def after_not_ours(self, item_id):
        return "depois" not in item_id and await ours(self, item_id)

    monkeypatch.setattr(creation.LocalFolders, "can_rename", after_not_ours)
    key = (await card(client, "Cozinha"))["key"]
    response = await act(client, owner, "hide", key)
    assert (response.status_code, response.json()["error"]) == (409, "comparison_not_ours")
    assert (stage / "Cozinha (antes).jpg").exists()


async def test_a_key_that_isnt_a_comparisons_card_is_not_found(client, owner, folders):
    put(folders / "01 - Briefing", "Cozinha (antes).jpg", "Cozinha (depois).jpg")
    plain = (await card(client, "Programa.pdf"))["key"]
    after = (await card(client, "Cozinha"))["comparison"]["after"]["key"]
    for key in (plain, after):
        response = await act(client, owner, "hide", key)
        assert (response.status_code, response.json()["error"]) == (404, "file_not_found")


async def test_switched_off_the_two_images_are_plain_files(client, db_session, owner, folders):
    put(folders / "01 - Briefing", "Cozinha (antes).jpg", "Cozinha (depois).jpg")
    await switch(db_session, on=False)
    found = await cards(client)
    assert sorted(f["name"] for f in found) == [
        "Cozinha (antes).jpg",
        "Cozinha (depois).jpg",
        "Programa.pdf",
    ]
    assert all(f["comparison"] is None for f in found)
    await switch(db_session, on=True)
    assert sorted(f["name"] for f in await cards(client)) == ["Cozinha", "Programa.pdf"]


@pytest.mark.parametrize("action", ["edit", "hide", "move"])
async def test_switched_off_a_comparison_cant_be_changed(
    client, db_session, owner, folders, action
):
    put(folders / "01 - Briefing", "Cozinha (antes).jpg", "Cozinha (depois).jpg")
    key = (await card(client, "Cozinha"))["key"]
    await switch(db_session, on=False)
    staff = await staff_of(client)
    body = {"title": "Copa", "position": 2, "row_version": staff["row_version"]}
    response = await act(client, owner, action, key, **body)
    assert (response.status_code, response.json()["error"]) == (409, "feature_off")
    assert (folders / "01 - Briefing" / "Cozinha (antes).jpg").exists()


async def test_switched_off_no_comparison_is_uploaded(client, db_session, owner, folders):
    await switch(db_session, on=False)
    response = await start(client, owner)
    assert (response.status_code, response.json()["error"]) == (409, "feature_off")
    assert sorted(p.name for p in (folders / "01 - Briefing").iterdir()) == ["Programa.pdf"]


@pytest.mark.parametrize("action", ["edit", "hide", "move"])
async def test_only_staff_change_comparisons(client, owner, folders, action):
    put(folders / "01 - Briefing", "Cozinha (antes).jpg", "Cozinha (depois).jpg")
    key = (await card(client, "Cozinha"))["key"]
    body = {"title": "Copa", "position": 2, "row_version": 0}
    response = await act(client, ALINEA, action, key, **body)
    assert response.status_code in (401, 403)
    assert (folders / "01 - Briefing" / "Cozinha (antes).jpg").exists()
