"""The client's project page (slice 2.3): what it shows, what it never shows,
and the shell the server sends before any script runs."""

import pytest
from sqlalchemy import select, text

from backend.identity.models import Role
from backend.projects.models import ProjectSlug
from backend.tests import test_office
from backend.tests.test_office import ALINEA, NORTE, PNG, sign_in_as, tenant_id

owner = test_office.owner  # fixtures

pytestmark = pytest.mark.anyio

SHELL = "<html><head><!--page-head--></head><body>page</body></html>"


@pytest.fixture
def dist(app, tmp_path):
    """A stand-in for the built `frontend/dist`, so these tests need no Node build."""
    folder = tmp_path / "dist"
    folder.mkdir()
    (folder / "client.html").write_text(SHELL)
    app.state.settings = app.state.settings.model_copy(update={"frontend_dist": str(folder)})
    return folder


async def page(client, slug, host=ALINEA):
    return await client.get(f"/api/pages/{slug}", headers=host)


async def project_id(db, slug, office="alinea"):
    return await db.scalar(
        select(ProjectSlug.project_id).where(
            ProjectSlug.slug == slug, ProjectSlug.tenant_id == await tenant_id(db, office)
        )
    )


# -- what the page shows -------------------------------------------------------------


async def test_a_published_project_shows_its_content_in_the_offices_language(client, owner):
    response = await page(client, "casa-jardim")
    assert response.status_code == 200, response.text
    shown = response.json()
    assert (shown["name"], shown["project_type"], shown["office"]["name"]) == (
        "Casa Jardim",
        "Projeto Arquitetônico",
        "Alinea (dev)",
    )
    assert shown["completed"] is False
    assert [s["completed"] for s in shown["stages"]][:3] == [True, True, False]
    assert [s["title"] for s in shown["stages"]][:3] == [
        "Briefing",
        "Levantamento",
        "Estudo Preliminar",
    ]
    # Architecture's own description of its survey, not the general one.
    assert shown["stages"][1]["about"].startswith("Análise do terreno")
    assert shown["stages"][1]["notes"].startswith("Levantamento concluído")
    details = {d["label"]: d["value"] for d in shown["details"]}
    assert details["Área do terreno"] == 1240.0
    assert details["Início"] == "2026-03-02"
    assert shown["next_meeting"]["title"] == "Apresentação do layout"  # the past one is gone


async def test_a_stage_outside_the_types_list_uses_the_general_description(
    client, db_session, owner
):
    project = await project_id(db_session, "apartamento-atlantico")  # interiors
    await db_session.execute(
        text(
            "INSERT INTO project_stages (tenant_id, project_id, position, builtin_key) "
            "VALUES (:t, :p, 9, 'permit_documents')"
        ),
        {"t": await tenant_id(db_session, "alinea"), "p": project},
    )
    stages = (await page(client, "apartamento-atlantico")).json()["stages"]
    assert stages[-1]["title"] == "Projeto Legal"
    assert stages[-1]["about"].startswith("Documentação para aprovação")
    # The office's own stage, as typed.
    assert (stages[-2]["title"], stages[-2]["about"]) == (
        "Aprovação no condomínio",
        "Envio do projeto à administração.",
    )


async def test_completed_and_archived_projects_still_have_a_page(client, db_session, owner):
    await db_session.execute(
        text("UPDATE projects SET status = 'archived', archived_from = 'active' WHERE id = :p"),
        {"p": await project_id(db_session, "casa-jardim")},
    )
    assert (await page(client, "casa-jardim")).status_code == 200


@pytest.fixture
async def draft(db_session):
    """Casa das Oliveiras as a draft. No project starts as one any more (A35), but
    the status stays in the schema, and a draft must stay hidden from clients."""
    await db_session.execute(
        text("UPDATE projects SET status = 'draft' WHERE id = :p"),
        {"p": await project_id(db_session, "casa-das-oliveiras")},
    )


@pytest.mark.parametrize(
    "slug",
    [
        "casa-das-oliveiras",  # a draft
        "nao-existe",
        "apto-atlantico",  # an old address: the shell redirects; the API never answers
    ],
)
async def test_drafts_unknown_and_old_addresses_are_not_found_alike(client, owner, draft, slug):
    client.cookies.clear()  # a visitor
    response = await page(client, slug)
    assert (response.status_code, response.json()) == (404, {"error": "page_not_found"})


async def test_a_deleted_project_is_not_found(client, db_session, owner):
    await db_session.execute(
        text("UPDATE projects SET deleted_at = now() WHERE id = :p"),
        {"p": await project_id(db_session, "casa-jardim")},
    )
    assert (await page(client, "casa-jardim")).status_code == 404


async def test_a_protected_project_shows_nothing_until_its_password_step(client, owner):
    client.cookies.clear()  # a visitor
    response = await page(client, "refugio-da-mantiqueira")
    assert (response.status_code, response.json()) == (403, {"error": "page_locked"})


async def test_each_office_answers_only_for_its_own_projects(client, owner):
    assert (await page(client, "casa-jardim", NORTE)).json()["name"] == "Casa Jardim (Norte)"
    assert (await page(client, "apartamento-atlantico", NORTE)).status_code == 404


async def test_the_page_needs_no_sign_in_and_reveals_no_internal_ids(client, owner):
    client.cookies.clear()
    shown = (await page(client, "casa-jardim")).text
    for secret in ("folder", "tenant", "creation_key", "password", "Casa Jardim/"):
        assert secret not in shown


# -- Drive disconnected -----------------------------------------------------------


async def set_drive(db, writer_status):
    """Alinea's storage as a Google connection in this state (its folder on record)."""
    await db.execute(
        text(
            "UPDATE storage_connections SET kind = 'google', root_id = 'root1',"
            " reader_identity = 'reader@unio.example', writer_token = NULL,"
            " writer_status = :w WHERE tenant_id = :t"
        ),
        {"w": writer_status, "t": await tenant_id(db, "alinea")},
    )


async def test_a_disconnected_offices_pages_are_offline_for_everyone(client, db_session, owner):
    """Plan section 9: "Desconectar" takes every page offline, files and all,
    and staff get the same answer (their page explains it)."""
    await set_drive(db_session, "none")
    for slug in ("casa-jardim", "refugio-da-mantiqueira"):  # public and protected alike
        response = await page(client, slug)  # as staff
        assert (response.status_code, response.json()) == (503, {"error": "page_unavailable"})
    files = await client.get("/api/pages/casa-jardim/files", headers=ALINEA)
    assert files.status_code == 503
    client.cookies.clear()  # a visitor
    assert (await page(client, "casa-jardim")).status_code == 503
    assert (await page(client, "no-such-page")).status_code == 404  # still not told apart
    # Another office's pages are its own business.
    assert (await page(client, "casa-jardim", NORTE)).status_code == 200


async def test_a_disconnected_offices_link_previews_show_nothing_of_the_project(
    client, db_session, dist, owner
):
    await set_drive(db_session, "none")
    client.cookies.clear()
    shell = await client.get("/casa-jardim", headers=ALINEA)
    assert shell.status_code == 503
    assert "Casa Jardim" not in shell.text and "Alinea (dev)" in shell.text
    assert (await client.get("/no-such-page", headers=ALINEA)).status_code == 404


async def test_an_expired_grant_keeps_the_pages_online(client, db_session, owner):
    await set_drive(db_session, "expired")
    client.cookies.clear()
    assert (await page(client, "casa-jardim")).status_code == 200


# -- the cover and the calendar file -----------------------------------------------


async def test_the_cover_is_public_on_a_readable_page_only(client, db_session, owner):
    staff = owner
    for slug in ("casa-jardim", "refugio-da-mantiqueira"):
        found = await project_id(db_session, slug)
        uploaded = await client.put(
            f"/api/projects/{found}/cover", files={"file": ("c.png", PNG)}, headers=staff
        )
        assert uploaded.status_code == 200, uploaded.text
    client.cookies.clear()
    url = (await page(client, "casa-jardim")).json()["cover_url"]
    shown = await client.get(url, headers=ALINEA)
    assert (shown.status_code, shown.content) == (200, PNG)
    assert shown.headers["x-robots-tag"] == "noindex"
    assert shown.headers["cache-control"].startswith("private")  # never a shared cache
    locked = await client.get("/api/pages/refugio-da-mantiqueira/cover", headers=ALINEA)
    assert locked.status_code == 404


async def test_the_next_meeting_downloads_as_a_calendar_file(client, db_session, owner):
    await db_session.execute(
        text("UPDATE meetings SET location = :l WHERE title = :t"),
        {"l": "Sala 2, térreo; bloco B\rportaria", "t": "Apresentação do layout"},
    )
    response = await client.get("/api/pages/casa-jardim/meeting.ics", headers=ALINEA)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    body = response.text
    assert "SUMMARY:Apresentação do layout · Casa Jardim" in body
    # Escaped as the format requires; no line break (even a lone \r) gets through.
    assert "LOCATION:Sala 2\\, térreo\\; bloco B\\nportaria" in body
    assert "DTSTART:" in body and body.count("BEGIN:VEVENT") == 1
    none = await client.get("/api/pages/apartamento-atlantico/meeting.ics", headers=ALINEA)
    assert none.status_code == 404  # no meeting ahead


# -- the shell -----------------------------------------------------------------------


async def test_the_shell_carries_the_link_preview(client, dist, owner):
    response = await client.get("/casa-jardim", headers=ALINEA)
    assert response.status_code == 200
    document = response.text
    assert "<title>Casa Jardim · Alinea (dev)</title>" in document
    assert '<meta property="og:title" content="Casa Jardim" />' in document
    assert 'og:description" content="Residência em um terreno inclinado' in document
    assert '<meta name="robots" content="noindex" />' in document
    assert response.headers["x-robots-tag"] == "noindex"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


async def test_the_preview_shows_the_cover_when_there_is_one(client, db_session, dist, owner):
    found = await project_id(db_session, "casa-jardim")
    await client.put(f"/api/projects/{found}/cover", files={"file": ("c.png", PNG)}, headers=owner)
    document = (await client.get("/casa-jardim", headers=ALINEA)).text
    assert 'og:image" content="http://alinea.localhost/api/pages/casa-jardim/cover?v=' in document
    assert "preview=true" in document  # the smaller image messaging apps accept


async def test_an_old_address_redirects_to_the_current_one(client, dist, owner):
    response = await client.get("/apto-atlantico?de=whatsapp", headers=ALINEA)
    assert response.status_code == 301
    assert response.headers["location"] == "/apartamento-atlantico?de=whatsapp"
    assert response.headers["cache-control"] == "no-cache"  # a slug may point back later


@pytest.mark.parametrize(
    "typed, address",
    [
        ("/Casa-Jardim?arquivo=x", "/casa-jardim?arquivo=x"),
        ("/APTO-ATLANTICO", "/apartamento-atlantico"),  # an old address, in capitals
        ("/Painel", "/painel"),  # the staff app's own address
    ],
)
async def test_an_address_in_capitals_redirects_to_the_lowercase_one(
    client, dist, owner, typed, address
):
    client.cookies.clear()  # a visitor
    response = await client.get(typed, headers=ALINEA)
    assert response.status_code == 301
    assert response.headers["location"] == address


async def test_the_page_api_answers_only_at_the_lowercase_address(client, dist, owner):
    # The shell redirects first, so the page always asks with the address it shows.
    assert (await client.get("/api/pages/casa-jardim", headers=ALINEA)).status_code == 200
    assert (await client.get("/api/pages/Casa-Jardim", headers=ALINEA)).status_code == 404


@pytest.mark.parametrize("slug", ["casa-das-oliveiras", "nao-existe"])
async def test_drafts_and_unknown_addresses_get_the_shell_with_not_found(
    client, dist, owner, draft, slug
):
    client.cookies.clear()  # a visitor
    response = await client.get(f"/{slug}", headers=ALINEA)
    assert response.status_code == 404
    assert "Casa das Oliveiras" not in response.text  # not even the draft's name


async def test_a_protected_projects_name_stays_out_of_the_preview(client, dist, owner):
    client.cookies.clear()  # a visitor
    document = (await client.get("/refugio-da-mantiqueira", headers=ALINEA)).text
    assert "Mantiqueira" not in document
    assert "<title>Alinea (dev)</title>" in document


async def test_typed_text_cannot_break_out_of_the_preview_tags(client, db_session, dist, owner):
    await db_session.execute(
        text("UPDATE projects SET name = :n, description = :d WHERE id = :p"),
        {
            "n": 'Casa "Lago" <script>alert(1)</script>',
            "d": 'Vista <b>linda</b> & "ampla"',
            "p": await project_id(db_session, "casa-jardim"),
        },
    )
    document = (await client.get("/casa-jardim", headers=ALINEA)).text
    assert "<script>alert" not in document and "<b>" not in document
    assert "Casa &quot;Lago&quot; &lt;script&gt;" in document


async def test_the_apps_own_addresses_are_never_a_page(client, dist, owner):
    """`/{slug}` comes last: the API and the painel keep answering as themselves."""
    assert (await client.get("/api/tenant", headers=ALINEA)).json()["name"] == "Alinea (dev)"
    painel = await client.get("/painel", headers=ALINEA)
    assert "page" not in painel.text  # the staff app's shell (or its build notice)
    assert (await client.get("/api", headers=ALINEA)).text == "Not found"  # reserved


@pytest.mark.parametrize("host", [ALINEA, NORTE])
async def test_the_example_project_is_on_every_offices_address(client, dist, owner, host):
    """Plan section 16: its content is in the client page's bundle, for anyone."""
    client.cookies.clear()  # a visitor, too
    response = await client.get("/tour-projeto", headers=host)
    assert response.status_code == 200
    assert "page" in response.text  # the client page's shell
    # In capitals, the lowercase address, as for any page.
    moved = await client.get("/Tour-Projeto", headers=host, follow_redirects=False)
    assert (moved.status_code, moved.headers["location"]) == (301, "/tour-projeto")


async def test_staff_see_who_gets_the_projects_updates(client, owner):
    """A32, 20 Oct 2026: edit mode says when nobody does; clients never see the list."""
    staff = (await page(client, "casa-jardim")).json()["staff"]
    changed = await client.patch(
        f"/api/projects/{staff['project_id']}",
        json={"row_version": staff["row_version"], "recipients": ["ana@x.com", "joao@x.com"]},
        headers=owner,
    )
    assert changed.status_code == 200
    shown = (await page(client, "casa-jardim")).json()["staff"]["recipients"]
    assert shown == [
        {"email": "ana@x.com", "subscribed": True},
        {"email": "joao@x.com", "subscribed": True},
    ]
    client.cookies.clear()
    assert "ana@x.com" not in (await page(client, "casa-jardim")).text


async def test_staff_see_the_clients_page_plus_what_the_staff_bar_needs(client, owner):
    as_staff = (await page(client, "casa-jardim")).json()
    assert as_staff["staff"]["status"] == "active" and as_staff["staff"]["project_id"]
    client.cookies.clear()
    as_client = (await page(client, "casa-jardim")).json()
    assert as_client["staff"] is None
    assert {**as_staff, "staff": None} == as_client  # nothing else differs


async def test_staff_see_their_drafts_and_protected_pages(client, dist, owner, draft):
    draft = (await page(client, "casa-das-oliveiras")).json()
    assert (draft["name"], draft["staff"]["status"]) == ("Casa das Oliveiras", "draft")
    assert (await page(client, "refugio-da-mantiqueira")).status_code == 200
    assert (await client.get("/casa-das-oliveiras", headers=ALINEA)).status_code == 200


async def test_another_offices_staff_get_no_preview_of_drafts(client, db_session, owner, draft):
    """Signed in at Norte, Alinea's draft is still "not found"."""
    await sign_in_as(client, db_session, "dona@norte.example", Role.OWNER, NORTE, "norte")
    assert (await page(client, "casa-das-oliveiras")).status_code == 404


# A draft left over (A35) can still be published, and an open tab of the previous
# release keeps its button working (A30).
async def test_publishing_opens_the_page_to_clients(client, db_session, owner, draft):
    draft = (await page(client, "casa-das-oliveiras")).json()["staff"]
    published = await client.post(f"/api/projects/{draft['project_id']}/publish", headers=owner)
    assert (published.status_code, published.json()["status"]) == (200, "active")
    again = await client.post(f"/api/projects/{draft['project_id']}/publish", headers=owner)
    assert again.status_code == 200  # twice changes nothing
    client.cookies.clear()
    assert (await page(client, "casa-das-oliveiras")).status_code == 200


async def test_publishing_needs_staff_and_their_csrf_token(client, db_session, owner, draft):
    draft = (await page(client, "casa-das-oliveiras")).json()["staff"]
    response = await client.post(f"/api/projects/{draft['project_id']}/publish", headers=ALINEA)
    assert response.status_code in (401, 403)


async def test_only_drafts_and_live_projects_can_be_published(client, db_session, owner):
    found = await project_id(db_session, "refugio-da-mantiqueira")  # completed
    response = await client.post(f"/api/projects/{found}/publish", headers=owner)
    assert (response.status_code, response.json()["error"]) == (422, "invalid_status_change")


async def test_a_draft_archived_without_being_published_stays_unpublished(
    client, db_session, owner, draft
):
    """Archiving is not a way to publish (plan section 10)."""
    draft = (await page(client, "casa-das-oliveiras")).json()["staff"]
    archived = await client.patch(
        f"/api/projects/{draft['project_id']}",
        json={"row_version": 1, "status": "archived"},
        headers=owner,
    )
    assert archived.status_code == 200, archived.text
    client.cookies.clear()
    assert (await page(client, "casa-das-oliveiras")).status_code == 404


@pytest.mark.parametrize("cookie", ["not-a-session", "expired"])
async def test_a_bad_or_expired_session_gets_the_visitors_answer(
    client, db_session, dist, owner, draft, cookie
):
    from backend.web.auth import COOKIE

    if cookie == "expired":
        await db_session.execute(text("UPDATE sessions SET expires_at = now() - interval '1 day'"))
    else:
        client.cookies.set(COOKIE, cookie)
    assert (await page(client, "casa-das-oliveiras")).status_code == 404
    assert (await page(client, "refugio-da-mantiqueira")).status_code == 403
    assert (await page(client, "casa-jardim")).json()["staff"] is None
    assert (await client.get("/casa-das-oliveiras", headers=ALINEA)).status_code == 404


async def test_what_only_staff_see_is_never_stored_by_a_shared_cache(
    client, db_session, dist, owner, draft
):
    found = await project_id(db_session, "casa-das-oliveiras")
    await db_session.execute(
        text("UPDATE projects SET folder_id = 'Casa das Oliveiras' WHERE id = :p"), {"p": found}
    )
    await client.put(f"/api/projects/{found}/cover", files={"file": ("c.png", PNG)}, headers=owner)
    for path in (
        "/api/pages/casa-das-oliveiras",
        "/casa-das-oliveiras",
        "/api/pages/casa-das-oliveiras/cover",
    ):
        response = await client.get(path, headers=ALINEA)
        assert response.status_code == 200, path
        assert response.headers["cache-control"] == "private, no-store", path
    client.cookies.clear()
    as_visitor = await client.get("/api/pages/casa-das-oliveiras/cover", headers=ALINEA)
    assert as_visitor.status_code == 404


async def test_a_staff_only_meeting_download_is_private(client, db_session, owner, draft):
    found = await project_id(db_session, "casa-das-oliveiras")
    await db_session.execute(
        text(
            "INSERT INTO meetings (tenant_id, project_id, title, starts_at, ends_at) "
            "VALUES (:t, :p, 'Visita', now() + interval '1 day', now() + interval '25 hours')"
        ),
        {"t": await tenant_id(db_session, "alinea"), "p": found},
    )
    response = await client.get("/api/pages/casa-das-oliveiras/meeting.ics", headers=ALINEA)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"


async def test_a_publish_that_loses_a_race_says_so(client, db_session, owner, draft, monkeypatch):
    """Archived by someone else between the check and the change: not "published"."""
    from backend.web import project_settings

    found = await project_id(db_session, "casa-das-oliveiras")
    real = project_settings._project

    async def read_then_archived(db, project_id):
        project = await real(db, project_id)
        await db.execute(
            text("UPDATE projects SET status = 'archived', archived_from = 'draft' WHERE id = :p"),
            {"p": found},
        )
        return project

    monkeypatch.setattr(project_settings, "_project", read_then_archived)
    response = await client.post(f"/api/projects/{found}/publish", headers=owner)
    assert (response.status_code, response.json()["error"]) == (409, "project_changed")
