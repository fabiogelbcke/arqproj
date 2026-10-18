"""A project's settings in the painel (step P3, A24): name, client, archiving,
and the cover photo."""

import pytest
from sqlalchemy import text

from backend.identity.models import Role
from backend.storage.models import ReaderStatus
from backend.tests import test_office
from backend.tests.test_office import ALINEA, NORTE, PNG, SVG, sign_in_as
from backend.tests.test_projects_api import FailsOnThirdFolder

owner = test_office.owner  # fixtures
on_google = test_office.on_google

pytestmark = pytest.mark.anyio

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


async def listed(client, host=ALINEA):
    return {p["slug"]: p for p in (await client.get("/api/projects", headers=host)).json()}


async def project(client, slug="casa-jardim"):
    return (await listed(client))[slug]


async def change(client, headers, found, **body):
    return await client.patch(
        f"/api/projects/{found['id']}",
        json={"row_version": found["row_version"], **body},
        headers=headers,
    )


# -- name, client, archiving --------------------------------------------------------


async def test_a_client_name_from_before_the_30_limit_can_be_kept_not_lengthened(
    client, db_session, owner
):
    """The Projeto dialog sends every field: a project saved with a longer client
    name must still save its other settings."""
    long = "Família Albuquerque de Oliveira Neto"  # 36 characters
    await db_session.execute(
        text("UPDATE projects SET client_name = :c WHERE name = 'Casa Jardim'"), {"c": long}
    )
    found = await project(client)
    kept = await change(client, owner, found, client_name=long, name="Casa Jardim II")
    assert kept.status_code == 200, kept.text
    changed = await change(client, owner, kept.json(), client_name=long + "!")
    assert (changed.status_code, changed.json()["error"]) == (422, "invalid_client_name")


async def test_name_and_client_can_be_changed(client, owner):
    found = await project(client)
    response = await change(client, owner, found, name=" Casa Jardim II ", client_name="Família R.")
    assert response.status_code == 200, response.text
    assert (response.json()["name"], response.json()["client_name"]) == (
        "Casa Jardim II",
        "Família R.",
    )
    assert response.json()["row_version"] == found["row_version"] + 1
    assert (await project(client))["name"] == "Casa Jardim II"


async def test_a_change_made_meanwhile_by_someone_else_is_not_overwritten(client, owner):
    """Two people open the dialog; the second save is refused, not silently applied."""
    seen_by_both = await project(client)
    assert (await change(client, owner, seen_by_both, name="Primeira")).status_code == 200
    second = await change(client, owner, seen_by_both, name="Segunda")
    assert (second.status_code, second.json()) == (409, {"error": "project_changed"})
    assert (await project(client))["name"] == "Primeira"


async def test_a_name_another_project_has_is_refused_but_its_own_is_fine(client, owner):
    found = await project(client)
    taken = await change(client, owner, found, name="casa das oliveiras")
    assert taken.status_code == 409
    assert taken.json() == {"error": "project_name_taken", "conflict_name": "Casa das Oliveiras"}
    own = await change(client, owner, found, name="CASA JARDIM")
    assert own.status_code == 200


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ({"name": "  "}, "invalid_project_name"),
        ({"client_name": "x" * 31}, "invalid_client_name"),  # 30 for now
    ],
)
async def test_bad_values_are_refused(client, owner, body, error):
    response = await change(client, owner, await project(client), **body)
    assert (response.status_code, response.json()["error"]) == (422, error)


async def test_archiving_hides_the_project_and_undo_brings_it_back(client, owner):
    found = await project(client)
    archived = await change(client, owner, found, status="archived")
    assert archived.status_code == 200 and archived.json()["status"] == "archived"
    assert "casa-jardim" not in await listed(client)

    restored = await client.patch(
        f"/api/projects/{found['id']}",
        json={"row_version": archived.json()["row_version"], "status": "active"},
        headers=owner,
    )
    assert restored.status_code == 200
    assert (await project(client))["status"] == "active"


async def as_draft(db_session):
    """No project starts as a draft any more (A35); the status stays in the schema."""
    await db_session.execute(
        text("UPDATE projects SET status = 'draft' WHERE name = 'Casa das Oliveiras'")
    )


async def test_undoing_an_archive_returns_only_to_what_it_was(client, db_session, owner):
    """Not a back door to publishing: an archived draft comes back a draft."""
    await as_draft(db_session)
    draft = await project(client, "casa-das-oliveiras")
    archived = (await change(client, owner, draft, status="archived")).json()
    published = await change(client, owner, archived, status="active")
    assert (published.status_code, published.json()["error"]) == (422, "invalid_status_change")
    back = await change(client, owner, archived, status="draft")
    assert back.status_code == 200 and back.json()["status"] == "draft"


async def test_publishing_and_completing_are_not_settings(client, db_session, owner):
    """Only archiving and undoing it here (A24)."""
    await as_draft(db_session)
    draft = await project(client, "casa-das-oliveiras")
    response = await change(client, owner, draft, status="active")
    assert (response.status_code, response.json()["error"]) == (422, "invalid_status_change")
    active = await project(client)
    response = await change(client, owner, active, status="completed")
    assert response.status_code == 422


async def test_members_can_change_settings(client, db_session, owner):
    member = await sign_in_as(client, db_session, "membro@alinea.example", Role.MEMBER)
    assert (await change(client, member, await project(client), name="Outra")).status_code == 200


async def test_another_offices_project_is_not_found(client, db_session, owner):
    alinea_project = await project(client)
    norte_headers = await sign_in_as(
        client, db_session, "dona@norte.example", Role.OWNER, NORTE, "norte"
    )
    response = await change(client, norte_headers, alinea_project, name="Invasão")
    assert (response.status_code, response.json()["error"]) == (404, "project_not_found")


async def test_changes_need_the_csrf_token(client, owner):
    response = await change(client, ALINEA, await project(client), name="Sem token")
    assert response.status_code in (401, 403)


# -- the cover ----------------------------------------------------------------------


async def upload(client, headers, found, content, name="capa.png"):
    return await client.put(
        f"/api/projects/{found['id']}/cover", files={"file": (name, content)}, headers=headers
    )


async def test_a_cover_is_stored_in_the_projects_folder_and_shown(client, owner, tmp_path):
    found = await project(client)
    response = await upload(client, owner, found, PNG)
    assert response.status_code == 200, response.text
    assert (tmp_path / "Casa Jardim" / "_capa" / "capa.png").read_bytes() == PNG
    url = response.json()["cover_url"]
    assert (await project(client))["cover_url"] == url

    shown = await client.get(url, headers=ALINEA)
    assert (shown.status_code, shown.content) == (200, PNG)
    assert shown.headers["content-type"] == "image/png"
    assert shown.headers["x-content-type-options"] == "nosniff"


async def test_a_new_cover_replaces_the_old_one(client, owner, tmp_path):
    found = await project(client)
    first = (await upload(client, owner, found, PNG)).json()
    second = (await upload(client, owner, found, JPEG, "foto.jpg")).json()
    assert second["cover_url"] != first["cover_url"]
    assert [p.name for p in (tmp_path / "Casa Jardim" / "_capa").iterdir()] == ["capa.jpg"]


async def test_a_cover_change_does_not_conflict_with_an_open_settings_dialog(client, owner):
    """The card's photo button and the dialog are independent: changing the
    photo must not make the dialog's next save look outdated."""
    found = await project(client)
    await upload(client, owner, found, PNG)
    assert (await change(client, owner, found, name="Ainda vale")).status_code == 200


async def test_removing_the_cover_goes_back_to_the_placeholder(client, owner, tmp_path):
    found = await project(client)
    url = (await upload(client, owner, found, PNG)).json()["cover_url"]
    removed = await client.delete(f"/api/projects/{found['id']}/cover", headers=owner)
    assert removed.status_code == 200 and removed.json()["cover_url"] is None
    assert list((tmp_path / "Casa Jardim" / "_capa").iterdir()) == []
    assert (await client.get(url, headers=ALINEA)).status_code == 404


@pytest.mark.parametrize(
    ("content", "status", "error"),
    [
        (SVG, 415, "cover_wrong_type"),  # can carry scripts; never a cover
        (b"%PDF-1.7 not an image", 415, "cover_wrong_type"),
        (PNG + b"\x00" * (10 * 1024 * 1024), 413, "cover_too_large"),
    ],
)
async def test_only_photos_up_to_10_mb_are_covers(client, owner, tmp_path, content, status, error):
    response = await upload(client, owner, await project(client), content)
    assert (response.status_code, response.json()["error"]) == (status, error)
    assert not (tmp_path / "Casa Jardim").exists()


async def test_an_archived_project_takes_no_new_cover(client, owner, tmp_path):
    archived = (await change(client, owner, await project(client), status="archived")).json()
    response = await upload(client, owner, archived, PNG)
    assert (response.status_code, response.json()["error"]) == (409, "project_archived")
    assert not (tmp_path / "Casa Jardim").exists()


async def test_a_project_without_a_folder_cannot_take_a_cover(client, owner):
    response = await upload(client, owner, await project(client, "casa-das-oliveiras"), PNG)
    assert (response.status_code, response.json()["error"]) == (409, "project_has_no_folder")


async def test_covers_are_for_signed_in_staff_for_now(client, owner):
    found = await project(client)
    url = (await upload(client, owner, found, PNG)).json()["cover_url"]
    client.cookies.clear()
    assert (await client.get(url, headers=ALINEA)).status_code == 401


async def test_another_offices_cover_is_not_found(client, db_session, owner):
    found = await project(client)
    url = (await upload(client, owner, found, PNG)).json()["cover_url"]
    await sign_in_as(client, db_session, "dona@norte.example", Role.OWNER, NORTE, "norte")
    assert (await client.get(url, headers=NORTE)).status_code == 404


# -- the cover on Google Drive ------------------------------------------------------


async def test_on_drive_the_cover_goes_into_a_capa_folder_and_replaces_the_old(
    client, owner, on_google
):
    fake, _ = on_google
    found = await project(client)
    first = await upload(client, owner, found, PNG)
    assert first.status_code == 200, first.text
    assert "POST /drive/v3/files" in fake.calls  # the _capa folder
    assert "POST /upload/drive/v3/files" in fake.calls
    await upload(client, owner, found, PNG)
    assert "PATCH /drive/v3/files/new2" in fake.calls  # the first photo, trashed


async def test_on_drive_a_failure_says_try_again(app, client, owner, on_google):
    import httpx2

    app.state.http = httpx2.AsyncClient(transport=httpx2.MockTransport(FailsOnThirdFolder()))
    fake = app.state.http._transport.handler
    fake.next_id = 2  # the next folder creation fails
    response = await upload(client, owner, await project(client), PNG)
    assert (response.status_code, response.json()) == (503, {"error": "drive_connect_failed"})
    assert (await project(client))["cover_url"] is None


async def test_no_cover_while_the_portal_cannot_read_the_folder(
    client, db_session, owner, on_google
):
    fake, connection = on_google
    connection.reader_status = ReaderStatus.NO_ACCESS
    await db_session.flush()
    response = await upload(client, owner, await project(client), PNG)
    assert (response.status_code, response.json()["error"]) == (409, "drive_unreadable")
    assert not any("upload" in c for c in fake.calls)


async def test_deleted_projects_have_no_settings(client, db_session, owner):
    found = await project(client)
    await db_session.execute(
        text("UPDATE projects SET deleted_at = now() WHERE id = :id"), {"id": found["id"]}
    )
    response = await change(client, owner, found, name="Fantasma")
    assert (response.status_code, response.json()["error"]) == (404, "project_not_found")
