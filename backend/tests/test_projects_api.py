"""The painel's project list and creating a project (step P2)."""

from datetime import UTC, datetime, timedelta

import httpx2
import pytest
from sqlalchemy import func, select, text

from backend.identity.models import Role
from backend.projects import creation
from backend.projects.enums import ProjectStatus
from backend.projects.models import Meeting, Project, ProjectSlug, ProjectStage
from backend.storage.models import ReaderStatus
from backend.tests import test_office
from backend.tests.test_office import ALINEA, NORTE, FakeGoogle, sign_in_as, tenant_id

owner = test_office.owner  # fixtures
on_google = test_office.on_google

pytestmark = pytest.mark.anyio


def body(**changes):
    return {
        "name": "Casa do Lago",
        "client_name": "Família Souza",
        "template": "standard",
        "slug": "casa-do-lago",
        "creation_key": "key-0123456789abcdef",
    } | changes


async def create(client, headers, **changes):
    return await client.post("/api/projects", json=body(**changes), headers=headers)


async def project_count(db, slug="alinea"):
    t = await tenant_id(db, slug)
    await db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(t)})
    return await db.scalar(select(func.count()).select_from(Project))


# -- creating ---------------------------------------------------------------------


async def test_a_new_project_is_a_draft_with_its_templates_stages_and_folders(
    client, db_session, owner, tmp_path
):
    response = await create(client, owner)
    assert response.status_code == 201, response.text
    created = response.json()
    assert (created["status"], created["slug"], created["stage_count"]) == (
        "draft",
        "casa-do-lago",
        7,
    )
    assert created["project_type"] == "architecture"  # the template's default
    assert created["current_stage_title"] == "Proposta"

    folders = sorted(p.name for p in (tmp_path / "Casa do Lago").iterdir())
    assert len(folders) == 7 and folders[0] == "01 - Proposta"
    stages = list(
        await db_session.scalars(
            select(ProjectStage)
            .where(ProjectStage.project_id == created["id"])
            .order_by(ProjectStage.position)
        )
    )
    assert [s.folder_id for s in stages][0] == "Casa do Lago/01 - Proposta"

    listed = (await client.get("/api/projects", headers=ALINEA)).json()
    assert created["id"] in {p["id"] for p in listed}


async def test_folder_names_follow_the_offices_language(client, db_session, owner, tmp_path):
    await db_session.execute(text("UPDATE tenants SET locale = 'en' WHERE slug = 'alinea'"))
    response = await create(client, owner)
    assert response.status_code == 201, response.text
    assert (tmp_path / "Casa do Lago" / "01 - Proposal").is_dir()


async def test_a_template_without_stages_makes_just_the_project_folder(client, owner, tmp_path):
    response = await create(client, owner, template="empty")
    assert (response.json()["stage_count"], response.json()["current_position"]) == (0, None)
    assert list((tmp_path / "Casa do Lago").iterdir()) == []


async def test_sending_the_same_creation_twice_makes_one_project(
    client, db_session, owner, tmp_path
):
    before = await project_count(db_session)
    first = await create(client, owner)
    again = await create(client, owner)
    assert again.status_code == 201 and again.json()["id"] == first.json()["id"]
    assert await project_count(db_session) == before + 1
    assert [p.name for p in tmp_path.iterdir()] == ["Casa do Lago"]  # no "(2)"


async def test_a_name_that_is_already_a_folder_gets_its_own(client, owner, tmp_path):
    (tmp_path / "Casa do Lago").mkdir()
    response = await create(client, owner)
    assert response.status_code == 201
    assert (tmp_path / "Casa do Lago (2)" / "01 - Proposta").is_dir()


@pytest.mark.parametrize("slug", ["casa-jardim", "apto-atlantico"])  # current and former
async def test_an_address_in_use_names_the_project_that_has_it(
    client, db_session, owner, tmp_path, slug
):
    before = await project_count(db_session)
    response = await create(client, owner, slug=slug)
    assert response.status_code == 409
    assert response.json()["error"] == "slug_taken"
    assert response.json()["conflict_name"] in ("Casa Jardim", "Apartamento Atlântico — Copacabana")
    assert await project_count(db_session) == before
    assert list(tmp_path.iterdir()) == []  # checked before any folder is made


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"name": "   "}, "invalid_project_name"),
        ({"name": "x" * 121}, "invalid_project_name"),
        ({"client_name": " "}, "invalid_client_name"),
        ({"client_name": "x" * 49}, "invalid_client_name"),
        ({"template": "no-such-template"}, "unknown_template"),
        ({"slug": "Casa do Lago"}, "invalid_slug"),
        ({"slug": "-casa"}, "invalid_slug"),
        ({"slug": "painel"}, "invalid_slug"),
        ({"slug": ""}, "invalid_slug"),
    ],
)
async def test_bad_details_are_refused_before_anything_is_made(
    client, owner, tmp_path, changes, error
):
    response = await create(client, owner, **changes)
    assert (response.status_code, response.json()["error"]) == (422, error)
    assert list(tmp_path.iterdir()) == []


async def test_the_address_is_tidied_before_checking(client, owner):
    response = await create(client, owner, slug="  Casa-Do-Lago ")
    assert response.json()["slug"] == "casa-do-lago"


async def test_members_can_create_projects(client, db_session, owner):
    member = await sign_in_as(client, db_session, "membro@alinea.example", Role.MEMBER)
    assert (await create(client, member)).status_code == 201


async def test_creating_needs_a_signed_in_request_with_its_csrf_token(client, owner):
    assert (await create(client, ALINEA)).status_code in (401, 403)


async def test_without_storage_nothing_can_be_created(client, db_session, owner):
    t = await tenant_id(db_session, "alinea")
    await db_session.execute(text("DELETE FROM storage_connections WHERE tenant_id = :t"), {"t": t})
    response = await create(client, owner)
    assert (response.status_code, response.json()["error"]) == (409, "drive_not_connected")


async def test_a_database_failure_removes_the_folders_already_made(
    client, db_session, owner, tmp_path, monkeypatch
):
    """All or nothing: here the address is taken between the check and the save."""
    real = creation._validate

    async def check_misses_the_clash(db, new):
        return await real(db, creation.NewProject(**{**new.__dict__, "slug": "ainda-livre"}))

    monkeypatch.setattr(creation, "_validate", check_misses_the_clash)
    before = await project_count(db_session)
    response = await create(client, owner, slug="casa-jardim")
    assert (response.status_code, response.json()["error"]) == (409, "slug_taken")
    assert list(tmp_path.iterdir()) == []
    assert await project_count(db_session) == before


async def test_the_check_above_would_catch_folders_left_behind(
    client, db_session, owner, tmp_path, monkeypatch
):
    """Self-test: with cleanup switched off, the failure leaves a folder."""

    async def keep(self, item_id):
        return None

    monkeypatch.setattr(creation.LocalFolders, "trash", keep)
    with pytest.raises(AssertionError):
        await test_a_database_failure_removes_the_folders_already_made(
            client, db_session, owner, tmp_path, monkeypatch
        )


# -- on Google Drive ------------------------------------------------------------------


async def test_on_drive_folders_go_inside_the_offices_folder(client, owner, on_google):
    fake, _ = on_google
    response = await create(client, owner)
    assert response.status_code == 201, response.text
    assert fake.calls.count("POST /drive/v3/files") == 1 + 7  # project + stages


class FailsOnThirdFolder(FakeGoogle):
    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        if request.method == "POST" and request.url.path == "/drive/v3/files":
            if self.next_id == 2:
                self.calls.append("POST /drive/v3/files (failed)")
                return httpx2.Response(503)
        return super().__call__(request)


async def test_a_drive_failure_trashes_what_was_made_and_says_try_again(
    app,
    client,
    db_session,
    owner,
    on_google,
):
    fake, _ = on_google
    failing = FailsOnThirdFolder()
    app.state.http = httpx2.AsyncClient(transport=httpx2.MockTransport(failing))
    before = await project_count(db_session)
    response = await create(client, owner)
    assert (response.status_code, response.json()) == (503, {"error": "drive_connect_failed"})
    # The project folder, holding the stage folder made before the failure.
    assert failing.calls[-1] == "PATCH /drive/v3/files/new1"
    assert await project_count(db_session) == before


async def test_on_drive_nothing_is_made_while_the_portal_cannot_read_the_folder(
    client,
    db_session,
    owner,
    on_google,
):
    fake, connection = on_google
    connection.reader_status = ReaderStatus.NO_ACCESS
    await db_session.flush()
    response = await create(client, owner)
    assert (response.status_code, response.json()["error"]) == (409, "drive_unreadable")
    assert "POST /drive/v3/files" not in fake.calls


async def test_an_expired_grant_asks_to_reconnect(client, owner, on_google):
    fake, _ = on_google
    fake.refresh_refused = True
    response = await create(client, owner)
    assert (response.status_code, response.json()["error"]) == (409, "drive_expired")


# -- the list -------------------------------------------------------------------------


async def test_the_list_has_what_the_cards_show(client, owner):
    listed = {p["slug"]: p for p in (await client.get("/api/projects", headers=ALINEA)).json()}
    assert set(listed) == {
        "casa-jardim",
        "apartamento-atlantico",
        "casa-das-oliveiras",
        "refugio-da-mantiqueira",
    }
    casa = listed["casa-jardim"]
    assert (casa["stage_count"], casa["current_position"]) == (7, 3)
    assert (
        casa["current_stage_title"] == "Estudos Preliminares / Anteprojeto"
    )  # translated built-in
    assert casa["project_type_label"] == "Projeto Arquitetônico"
    assert casa["next_meeting"]["title"] == "Apresentação do layout"  # the past one is skipped
    apartment = listed["apartamento-atlantico"]
    assert apartment["stage_count"] == 7  # six built in + the office's own


async def test_an_office_written_current_stage_shows_as_typed(client, db_session, owner):
    await db_session.execute(
        text(
            "UPDATE projects SET current_position = 7 WHERE id = "
            "(SELECT project_id FROM project_slugs WHERE slug = 'apartamento-atlantico')"
        )
    )
    listed = {p["slug"]: p for p in (await client.get("/api/projects", headers=ALINEA)).json()}
    assert listed["apartamento-atlantico"]["current_stage_title"] == "Aprovação no condomínio"


async def test_the_next_meeting_is_the_soonest_upcoming_one(client, db_session, owner):
    project_id = await db_session.scalar(
        select(ProjectSlug.project_id).where(
            ProjectSlug.slug == "casa-jardim",
            ProjectSlug.tenant_id == await tenant_id(db_session, "alinea"),
        )
    )
    soon = datetime.now(UTC) + timedelta(days=1)
    db_session.add(
        Meeting(
            tenant_id=await tenant_id(db_session, "alinea"),
            project_id=project_id,
            title="Visita à obra",
            starts_at=soon,
            ends_at=soon + timedelta(hours=1),
        )
    )
    await db_session.flush()
    listed = {p["slug"]: p for p in (await client.get("/api/projects", headers=ALINEA)).json()}
    assert listed["casa-jardim"]["next_meeting"]["title"] == "Visita à obra"


async def test_deleted_and_archived_projects_are_not_listed(client, db_session, owner):
    await db_session.execute(
        text(
            "UPDATE projects SET deleted_at = now() WHERE id = "
            "(SELECT project_id FROM project_slugs WHERE slug = 'casa-jardim' AND tenant_id = "
            "(SELECT id FROM tenants WHERE slug = 'alinea'))"
        )
    )
    await db_session.execute(
        text(
            f"UPDATE projects SET status = '{ProjectStatus.ARCHIVED.value}' WHERE id = "
            "(SELECT project_id FROM project_slugs WHERE slug = 'casa-das-oliveiras')"
        )
    )
    slugs = {p["slug"] for p in (await client.get("/api/projects", headers=ALINEA)).json()}
    assert slugs == {"apartamento-atlantico", "refugio-da-mantiqueira"}


async def test_each_office_lists_only_its_own_projects(client, db_session, owner):
    await sign_in_as(client, db_session, "dona@norte.example", Role.OWNER, NORTE, "norte")
    names = {p["name"] for p in (await client.get("/api/projects", headers=NORTE)).json()}
    assert names == {"Casa Jardim (Norte)"}


async def test_the_list_needs_sign_in(client, owner):
    client.cookies.clear()
    assert (await client.get("/api/projects", headers=ALINEA)).status_code == 401


async def test_templates_come_in_order_with_their_stage_counts(client, owner):
    templates = (await client.get("/api/templates", headers=ALINEA)).json()
    assert [(t["key"], t["stage_count"]) for t in templates] == [
        ("standard", 7),
        ("interiors", 6),
        ("empty", 0),
    ]
    assert all(t["label"] for t in templates)
