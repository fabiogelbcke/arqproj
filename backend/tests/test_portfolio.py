"""The office's portfolio: edited in the painel, behind the `portfolio` feature
(A40), and shown at its own address's root once published."""

import re
import uuid
from datetime import date

import pytest
from sqlalchemy import text

from backend.identity.models import Role
from backend.portfolio.links import profile
from backend.portfolio.models import SocialNetwork
from backend.tests import test_office
from backend.tests.test_office import ALINEA, NORTE, PNG, sign_in_as

office_owner = test_office.owner  # fixtures

pytestmark = pytest.mark.anyio

JPEG = b"\xff\xd8\xff" + b"\x01" * 64
UNIO = {"host": "localhost"}


def png(width: int, height: int) -> bytes:
    """A real image, so the server can read its size (JPEG above is a stub it can't)."""
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, "PNG")
    return buffer.getvalue()


async def switch_on(db, slug="alinea"):
    await db.execute(
        text("UPDATE tenants SET features = features || '{portfolio}' WHERE slug = :s"),
        {"s": slug},
    )


@pytest.fixture
async def staff(office_owner, db_session):
    """Alinea's owner, with the portfolio switched on for the office."""
    await switch_on(db_session)
    return office_owner


async def project_id(client, slug="casa-jardim"):
    projects = (await client.get("/api/projects", headers=ALINEA)).json()
    return next(p["id"] for p in projects if p["slug"] == slug)


async def add(client, headers, **body):
    answer = await client.post(
        "/api/portfolio/entries",
        json={"title": "Casa Jardim", "place": "", "description": ""} | body,
        headers=headers,
    )
    assert answer.status_code == 200, answer.text
    return answer.json()["entries"][-1]


async def photo(client, headers, entry, content=JPEG, name="foto.jpg"):
    return await client.post(
        f"/api/portfolio/entries/{entry['id']}/photos",
        files={"file": (name, content)},
        headers=headers,
    )


async def publish(client, headers, published=True):
    answer = await client.patch("/api/portfolio", json={"published": published}, headers=headers)
    assert answer.status_code == 200, answer.text


async def test_without_the_feature_the_portfolio_is_refused_and_the_root_stays_unios(
    client, office_owner
):
    answer = await client.get("/api/portfolio", headers=ALINEA)
    assert (answer.status_code, answer.json()["error"]) == (409, "feature_off")
    # The public photo and video routes too: the switch covers the whole router.
    for public in ("photos/" + str(uuid.uuid4()), "videos/" + str(uuid.uuid4()) + "/poster"):
        refused = await client.get(f"/api/portfolio/{public}", headers=ALINEA)
        assert refused.status_code == 409, public
    root = await client.get("/", headers=ALINEA)
    assert root.status_code == 200 and "UNIO" in root.text


async def test_unios_home_on_an_office_address_is_not_kept_by_the_browser(client, staff):
    """Published, or previewed after signing in, the portfolio shows at once: the
    home shown there until then was never cached (on Unio's own address it is)."""
    client.cookies.clear()
    before = await client.get("/", headers=ALINEA)
    assert before.status_code == 200 and "UNIO" in before.text
    assert before.headers["cache-control"] == "no-cache"
    unios = await client.get("/", headers={"host": "localhost"})  # Unio's own address
    assert unios.status_code == 200 and "UNIO" in unios.text
    assert unios.headers["cache-control"] == "public, max-age=3600"


async def test_a_type_the_operator_added_is_shown_by_its_own_name(client, staff, db_session):
    """The built-in types have a short public label ("Arquitetura", not the
    painel's "Projeto Arquitetônico"); a type added from the operator dashboard
    (A44) has only its own name, shown as given, where the dashboard ordered it."""
    await db_session.execute(
        text("INSERT INTO project_types (key, position, labels) VALUES ('cenografia', 0, :labels)"),
        {"labels": '{"pt-BR": "Cenografia & Eventos", "en": "Set design"}'},
    )
    await db_session.commit()
    for title, kind in (("Casa Jardim", "architecture"), ("Palco", "cenografia")):
        entry = await add(client, staff, title=title, project_type=kind)
        await photo(client, staff, entry)
    await publish(client, staff)
    client.cookies.clear()

    page = (await client.get("/", headers=ALINEA)).text
    menu = page.split('class="types"')[1].split("</nav>")[0]
    assert "Cenografia &amp; Eventos</a>" in menu and "Arquitetura</a>" in menu
    assert "Projeto Arquitetônico" not in page
    assert menu.index("Cenografia") < menu.index("Arquitetura")  # position 0 comes first


async def test_an_archived_project_can_be_drawn_on_though_the_painel_lists_it_no_more(
    client, db_session, staff
):
    """Finished work is what a portfolio shows, and finished projects get archived."""
    casa = await project_id(client)
    await db_session.execute(
        text("UPDATE projects SET status = 'archived', archived_from = 'completed' WHERE id = :p"),
        {"p": casa},
    )
    await db_session.commit()
    listed = [p["id"] for p in (await client.get("/api/projects", headers=ALINEA)).json()]
    assert casa not in listed
    with_archived = await client.get("/api/projects?archived=true", headers=ALINEA)
    assert casa in [p["id"] for p in with_archived.json()]
    drawn = await add(client, staff, project_id=casa)
    assert (drawn["project_name"], drawn["status"]) == ("Casa Jardim", "completed")


async def test_a_failed_video_send_is_logged_with_its_context_and_answers_with_the_code(
    client, staff, caplog
):
    """The bytes never pass through the app: the painel reports a send that failed."""
    entry = await add(client, staff, title="Casa")
    response = await client.post(
        f"/api/portfolio/entries/{entry['id']}/videos/uploads/failed",
        json={"name": "obra.mp4", "size": 9, "status": 403, "detail": "storageQuotaExceeded"},
        headers=staff,
    )
    assert (response.status_code, response.json()) == (502, {"error": "upload_failed"})
    assert response.headers["x-request-id"]  # the code the log line carries too
    logged = [r for r in caplog.records if "sending failed" in r.getMessage()]
    assert logged and logged[0].levelname == "ERROR"
    message = logged[0].getMessage()
    assert entry["id"] in message and "storageQuotaExceeded" in message


async def test_only_staff_read_and_change_the_portfolio(client, staff):
    client.cookies.clear()
    assert (await client.get("/api/portfolio", headers=ALINEA)).status_code == 401
    answer = await client.post("/api/portfolio/entries", json={"title": "Casa"}, headers=ALINEA)
    assert answer.status_code == 401


async def test_a_work_from_a_project_keeps_its_photos_as_copies_in_order(client, staff, tmp_path):
    project = await project_id(client)
    entry = await add(client, staff, project_id=project, place="Porto Alegre, RS", year=2024)
    assert entry["project_name"] == "Casa Jardim"
    for content in (JPEG, PNG):
        assert (await photo(client, staff, entry, content)).status_code == 200
    portfolio = (await client.get("/api/portfolio", headers=ALINEA)).json()
    photos = portfolio["entries"][0]["photos"]
    assert len(photos) == 2
    stored = sorted(path.read_bytes() for path in (tmp_path / "_portfolio").iterdir())
    assert stored == sorted([JPEG, PNG])

    # The second first: it becomes the cover.
    order = [photos[1]["id"], photos[0]["id"]]
    changed = await client.patch(
        f"/api/portfolio/entries/{entry['id']}", json={"photos": order}, headers=staff
    )
    assert [p["id"] for p in changed.json()["entries"][0]["photos"]] == order
    # An order missing a photo (one added elsewhere meanwhile) is refused.
    stale = await client.patch(
        f"/api/portfolio/entries/{entry['id']}", json={"photos": order[:1]}, headers=staff
    )
    assert stale.status_code == 409


async def test_works_are_reordered_only_as_a_whole_list(client, staff):
    first = await add(client, staff, title="Casa Jardim")
    second = await add(client, staff, title="Loja Centro")
    answer = await client.put(
        "/api/portfolio/order", json={"entries": [second["id"], first["id"]]}, headers=staff
    )
    assert [e["title"] for e in answer.json()["entries"]] == ["Loja Centro", "Casa Jardim"]
    partial = await client.put(
        "/api/portfolio/order", json={"entries": [second["id"]]}, headers=staff
    )
    assert partial.status_code == 409


async def test_only_images_are_accepted_as_photos(client, staff):
    entry = await add(client, staff)
    answer = await photo(client, staff, entry, b"%PDF-1.7", "planta.pdf")
    assert (answer.status_code, answer.json()["error"]) == (415, "cover_wrong_type")


async def test_a_full_portfolio_takes_no_more(client, staff, monkeypatch):
    from backend.web import portfolio

    monkeypatch.setattr(portfolio, "ENTRIES_MAX", 1)
    monkeypatch.setattr(portfolio, "PHOTOS_MAX", 1)
    entry = await add(client, staff)
    more = await client.post("/api/portfolio/entries", json={"title": "Outra"}, headers=staff)
    assert (more.status_code, more.json()["error"]) == (409, "portfolio_full")
    assert (await photo(client, staff, entry)).status_code == 200
    second = await photo(client, staff, entry)
    assert (second.status_code, second.json()["error"]) == (409, "portfolio_full")


async def test_removing_a_work_takes_its_photos_from_storage(client, staff, tmp_path):
    entry = await add(client, staff)
    await photo(client, staff, entry)
    answer = await client.delete(f"/api/portfolio/entries/{entry['id']}", headers=staff)
    assert answer.json()["entries"] == []
    assert list((tmp_path / "_portfolio").iterdir()) == []


async def test_photos_are_public_only_once_published(client, staff):
    entry = await add(client, staff)
    url = (await photo(client, staff, entry)).json()["entries"][0]["photos"][0]["url"]
    assert (await client.get(url, headers=ALINEA)).status_code == 200  # staff, before
    client.cookies.clear()
    assert (await client.get(url, headers=ALINEA)).status_code == 404
    assert "UNIO" in (await client.get("/", headers=ALINEA)).text  # not published yet


async def test_published_the_offices_address_shows_the_portfolio_and_unios_keeps_its_home(
    client, staff
):
    entry = await add(
        client,
        staff,
        title="Casa <Jardim>",
        place="Porto Alegre, RS",
        year=2024,
        description="Primeiro parágrafo.\n\nSegundo & último.",
    )
    url = (await photo(client, staff, entry)).json()["entries"][0]["photos"][0]["url"]
    await add(client, staff, title="Sem fotos ainda")
    await client.patch("/api/portfolio", json={"intro": "Arquitetura residencial."}, headers=staff)
    await publish(client, staff)
    client.cookies.clear()

    root = await client.get("/", headers=ALINEA)
    assert root.status_code == 200
    assert "Arquitetura residencial." in root.text
    assert "Casa &lt;Jardim&gt;" in root.text and "<Jardim>" not in root.text
    assert "Porto Alegre, RS · 2024" in root.text
    assert "Sem fotos ainda" not in root.text  # a work without photos isn't shown
    assert root.headers["cache-control"] == "public, max-age=60"
    # Only our own script runs (the carousel's arrows), served from this address.
    assert "script-src 'self';" in root.headers["content-security-policy"]
    # The stylesheet and script are cached for an hour, so the page names them by
    # their content: a change to either is seen as soon as the page is.
    style, script = (
        re.search(rf"/brand/portfolio\.{ext}\?v=[0-9a-f]{{12}}", root.text) for ext in ("css", "js")
    )
    assert style and script, root.text[:1200]
    served = await client.get(script.group(0), headers=ALINEA)
    assert served.status_code == 200 and "carousel" in served.text and "lightbox" in served.text
    assert (await client.get(style.group(0), headers=ALINEA)).status_code == 200
    from backend.web import portfolio_page

    assert portfolio_page._asset_url("portfolio.js", True) != portfolio_page._asset_url(
        "portfolio.css", True
    )

    served = await client.get(url, headers=ALINEA)
    assert (served.status_code, served.content) == (200, JPEG)
    assert served.headers["cache-control"].startswith("public")

    work = await client.get(f"/?projeto={entry['id']}", headers=ALINEA)
    assert "<p>Primeiro parágrafo.</p><p>Segundo &amp; último.</p>" in work.text
    assert f"{url}?size=full" in work.text
    # Nonsense in the address shows the list, not an error.
    assert (await client.get("/?projeto=nada", headers=ALINEA)).status_code == 200

    assert "Arquitetura residencial." not in (await client.get("/", headers=UNIO)).text


async def test_staff_preview_an_unpublished_portfolio_and_visitors_dont(client, staff):
    entry = await add(client, staff, title="Casa Jardim")
    await photo(client, staff, entry)
    preview = await client.get("/?previa=1", headers=ALINEA)
    assert "Casa Jardim" in preview.text
    assert preview.headers["x-robots-tag"] == "noindex"
    assert preview.headers["cache-control"] == "private, no-store"
    client.cookies.clear()
    assert "Casa Jardim" not in (await client.get("/?previa=1", headers=ALINEA)).text
    client.cookies.set("portal_session", "not-a-session")
    assert "Casa Jardim" not in (await client.get("/?previa=1", headers=ALINEA)).text


async def test_a_work_draws_only_on_the_offices_own_projects(client, db_session, staff):
    elsewhere = await project_id(client)
    await switch_on(db_session, "norte")
    norte = await sign_in_as(
        client, db_session, "dono@norte.example", Role.OWNER, host=NORTE, slug="norte"
    )
    answer = await client.post(
        "/api/portfolio/entries", json={"title": "Casa", "project_id": elsewhere}, headers=norte
    )
    assert (answer.status_code, answer.json()["error"]) == (404, "project_not_found")


async def test_one_offices_works_are_out_of_anothers_reach(client, db_session, staff):
    entry = await add(client, staff)
    await switch_on(db_session, "norte")
    norte = await sign_in_as(
        client, db_session, "dono@norte.example", Role.OWNER, host=NORTE, slug="norte"
    )
    assert (await client.get("/api/portfolio", headers=NORTE)).json()["entries"] == []
    answer = await client.patch(
        f"/api/portfolio/entries/{entry['id']}", json={"title": "Minha"}, headers=norte
    )
    assert answer.status_code == 404
    assert (
        await client.delete(f"/api/portfolio/entries/{entry['id']}", headers=norte)
    ).status_code == 404


async def test_an_alias_of_the_offices_address_moves_to_it_first(client, staff):
    entry = await add(client, staff)
    await photo(client, staff, entry)
    await publish(client, staff)
    moved = await client.get("/?projeto=x", headers={"host": "www.alinea.localhost"})
    assert moved.status_code == 301
    assert moved.headers["location"].startswith("http://alinea.localhost")
    assert moved.headers["location"].endswith("/?projeto=x")


async def test_an_unconfirmed_account_gets_no_preview(client, db_session, staff):
    entry = await add(client, staff, title="Casa Jardim")
    await photo(client, staff, entry)
    await db_session.execute(
        text("UPDATE users SET email_confirmed_at = NULL WHERE email = 'dona@alinea.example'")
    )
    assert "Casa Jardim" not in (await client.get("/?previa=1", headers=ALINEA)).text


async def test_removing_succeeds_even_when_storage_cant_take_the_files(client, staff, monkeypatch):
    from backend.web import portfolio
    from backend.web.errors import ApiError, ErrorCode

    entry = await add(client, staff)
    url = (await photo(client, staff, entry)).json()["entries"][0]["photos"][0]["url"]

    async def unreadable(request, db):
        raise ApiError(409, ErrorCode.DRIVE_UNREADABLE)

    monkeypatch.setattr(portfolio, "storage_connection", unreadable)
    removed = await client.delete(f"/api/portfolio/photos/{url.rsplit('/', 1)[1]}", headers=staff)
    assert removed.status_code == 200 and removed.json()["entries"][0]["photos"] == []
    gone = await client.delete(f"/api/portfolio/entries/{entry['id']}", headers=staff)
    assert gone.status_code == 200 and gone.json()["entries"] == []


async def test_a_work_takes_its_projects_type_unless_given_one(client, staff):
    project = await project_id(client)
    drawn = await add(client, staff, project_id=project)
    assert drawn["project_type"] == "architecture"  # Casa Jardim's
    chosen = await add(client, staff, project_id=project, project_type="interiors")
    assert chosen["project_type"] == "interiors"
    assert (await add(client, staff, title="Loja"))["project_type"] is None

    url = f"/api/portfolio/entries/{drawn['id']}"
    changed = await client.patch(url, json={"project_type": "landscaping"}, headers=staff)
    assert changed.json()["entries"][0]["project_type"] == "landscaping"
    kept = await client.patch(url, json={"title": "Casa"}, headers=staff)
    assert kept.json()["entries"][0]["project_type"] == "landscaping"
    cleared = await client.patch(url, json={"project_type": None}, headers=staff)
    assert cleared.json()["entries"][0]["project_type"] is None

    unknown = await client.patch(url, json={"project_type": "castle"}, headers=staff)
    assert unknown.status_code == 422
    added = await client.post(
        "/api/portfolio/entries", json={"title": "X", "project_type": "castle"}, headers=staff
    )
    assert added.status_code == 422


async def test_the_menu_shows_the_works_of_one_type(client, staff):
    for title, kind in (("Casa Jardim", "architecture"), ("Apto Mar", "interiors"), ("Loja", None)):
        entry = await add(client, staff, title=title, project_type=kind)
        await photo(client, staff, entry)
    await publish(client, staff)
    client.cookies.clear()

    every = (await client.get("/", headers=ALINEA)).text
    assert 'class="carousel"' in every and every.count('class="slide"') == 3
    assert '<a href="/?tipo=interiors#projetos">Interiores</a>' in every
    assert "Paisagismo" not in every  # no work of that type: not in the menu
    assert '<a href="/#projetos" aria-current="page">Todos</a>' in every

    def grid(page: str) -> dict[str, bool]:
        """Each work in the grid, by title, with whether it is shown."""
        cards = page.split('class="works"')[1].split("</ul>")[0].split("<li")[1:]
        title = lambda card: card.split('class="title">')[1].split("<")[0]  # noqa: E731
        return {title(card): " hidden" not in card for card in cards}

    assert grid(every) == {"Casa Jardim": True, "Apto Mar": True, "Loja": True}
    one = (await client.get("/?tipo=interiors", headers=ALINEA)).text
    # Every work is in the page, the others hidden: the menu switches in place.
    assert grid(one) == {"Casa Jardim": False, "Apto Mar": True, "Loja": False}
    assert 'aria-current="page">Interiores' in one
    assert one.count('class="slide"') == 3  # the carousel shows them all still
    nonsense = (await client.get("/?tipo=castle", headers=ALINEA)).text
    assert all(grid(nonsense).values())


async def test_a_photos_pixel_size_is_recorded_when_the_file_can_be_read(client, staff, db_session):
    entry = await add(client, staff)
    sent = await photo(client, staff, entry, content=png(300, 500), name="post.png")
    assert sent.status_code == 200, sent.text
    assert (await photo(client, staff, entry)).status_code == 200  # the stub: stored, unsized
    sizes = await db_session.execute(
        text("SELECT width, height FROM portfolio_photos ORDER BY position")
    )
    assert sizes.all() == [(300, 500), (None, None)]


async def test_an_upright_cover_stands_whole_on_a_blurred_copy_instead_of_cropped(client, staff):
    """A story or a post as a cover of the "gallery" format: the carousel and the
    hero show it whole, over a blurred copy of itself; a landscape cover fills them."""
    story = await add(client, staff, title="Story")
    await photo(client, staff, story, content=png(90, 160), name="story.png")
    wide = await add(client, staff, title="Casa")
    await photo(client, staff, wide, content=png(160, 90), name="casa.png")
    await publish(client, staff)
    client.cookies.clear()

    home = (await client.get("/", headers=ALINEA)).text
    slides = home.split('<li class="slide')[1:]
    assert slides[0].startswith(' tall"') and slides[0].count('class="backdrop"') == 1
    assert slides[1].startswith('"') and "backdrop" not in slides[1]
    upright = (await client.get(f"/?projeto={story['id']}", headers=ALINEA)).text
    assert '<header class="hero tall">' in upright and upright.count('class="backdrop"') == 1
    landscape = (await client.get(f"/?projeto={wide['id']}", headers=ALINEA)).text
    assert '<header class="hero">' in landscape and "backdrop" not in landscape


async def test_the_mosaic_format_shows_every_image_in_its_own_shape(client, staff):
    """For material made for the networks: no carousel, hero or frame; a mosaic of
    covers, and a work as a grid of its images under its title. Each image's
    size is in its tag, so the page keeps its shape while loading."""
    changed = await client.patch("/api/portfolio", json={"format": "mosaic"}, headers=staff)
    assert (changed.status_code, changed.json()["format"]) == (200, "mosaic"), changed.text
    assert (await client.get("/api/portfolio", headers=staff)).json()["format"] == "mosaic"
    nonsense = await client.patch("/api/portfolio", json={"format": "grid"}, headers=staff)
    assert nonsense.status_code == 422
    post = await add(client, staff, title="Post", project_type="architecture")
    await photo(client, staff, post, content=png(1080, 1350), name="post.png")
    await photo(client, staff, post, content=png(1080, 1080), name="square.png")
    other = await add(client, staff, title="Loja", project_type="interiors")
    await photo(client, staff, other, content=png(1080, 1920), name="story.png")
    await publish(client, staff)
    client.cookies.clear()

    home = (await client.get("/", headers=ALINEA)).text
    assert 'class="carousel"' not in home and 'class="works"' not in home
    mosaic = home.split('class="mosaic"')[1].split("</ul>")[0]
    assert mosaic.count("<li ") == 2 and 'width="1080" height="1350"' in mosaic
    assert 'class="frame"' not in mosaic  # no fixed frame: the image's own shape
    assert '<a href="/?tipo=interiors#projetos">Interiores</a>' in home  # the menu stays

    work = (await client.get(f"/?projeto={post['id']}", headers=ALINEA)).text
    assert 'class="hero' not in work and '<header class="post-head wrap">' in work
    assert "<h1>Post</h1>" in work
    posts = work.split('class="mosaic posts"')[1].split("</ul>")[0]  # the mosaic's grid
    assert posts.count("<li>") == 2  # the cover among them, not above
    assert 'width="1080" height="1350"' in posts and 'width="1080" height="1080"' in posts
    assert 'class="lightbox"' in work  # each still opens large


async def test_with_a_single_type_there_is_no_menu(client, staff):
    entry = await add(client, staff, project_type="architecture")
    await photo(client, staff, entry)
    await publish(client, staff)
    assert 'class="types"' not in (await client.get("/", headers=ALINEA)).text


async def test_a_works_page_leads_to_the_next_one(client, staff):
    first = await add(client, staff, title="Casa Jardim", project_type="architecture")
    second = await add(client, staff, title="Loja Centro — Matriz")
    for entry in (first, second):
        await photo(client, staff, entry)
    await publish(client, staff)
    page = (await client.get(f"/?projeto={first['id']}", headers=ALINEA)).text
    # The type, title, place and year over the cover; the other facts below it.
    hero = page.split('<header class="hero">')[1].split("</header>")[0]
    assert '<p class="label">Arquitetura</p><h1>Casa Jardim</h1>' in hero
    assert f'class="following" href="/?projeto={second["id"]}"' in page
    last = (await client.get(f"/?projeto={second['id']}", headers=ALINEA)).text
    assert f'class="following" href="/?projeto={first["id"]}"' in last  # back to the first
    # A title never breaks onto a new line before its dash.
    assert "<h1>Loja Centro\u00a0— Matriz</h1>" in last
    assert 'class="about solo"' not in page and 'class="about' not in last  # no facts, no text


async def _project_facts(db_session, *, status, completed=None, delivery=None):
    """Casa Jardim with its client, address, built area and lead architect."""
    await db_session.execute(
        text(
            "INSERT INTO project_details "
            "(tenant_id, project_id, key, value_type, position, value_text, value_number) "
            "SELECT tenant_id, id, d.key, d.kind, d.position, d.word, d.number FROM projects, "
            "(VALUES ('client', 'text', 91, 'Família Teixeira', NULL::numeric), "
            "('location', 'text', 92, 'Rua das Acácias, 120', NULL), "
            "('built_area', 'area', 93, NULL, 212.5), "
            "('responsible', 'text', 94, 'Laura Mendes', NULL)) "
            "AS d(key, kind, position, word, number) WHERE projects.name = 'Casa Jardim' "
            "ON CONFLICT (project_id, key) DO UPDATE SET value_text = EXCLUDED.value_text, "
            "value_number = EXCLUDED.value_number"
        )
    )
    if delivery:
        await db_session.execute(
            text(
                "INSERT INTO project_details "
                "(tenant_id, project_id, key, value_type, position, value_date) "
                "SELECT tenant_id, id, 'expected_delivery', 'date', 95, :d FROM projects "
                "WHERE name = 'Casa Jardim'"
            ),
            {"d": delivery},
        )
    await db_session.execute(
        text("UPDATE projects SET status = :s WHERE name = 'Casa Jardim'"), {"s": status}
    )
    await db_session.execute(
        text(
            "UPDATE project_stages SET completed_at = :c FROM projects "
            "WHERE projects.id = project_stages.project_id AND projects.name = 'Casa Jardim'"
        ),
        {"c": completed},
    )


async def test_a_work_drawn_from_a_project_starts_with_its_facts_never_its_client_or_address(
    client, db_session, staff
):
    await _project_facts(db_session, status="completed", completed=date(2025, 3, 10))
    drawn = await add(client, staff, project_id=await project_id(client))
    assert (drawn["status"], drawn["year"], drawn["place"]) == ("completed", 2025, "")
    # The project's details in its order, labelled as its page shows them; the
    # seeded project has a few more (its site area, its start) than the fixture adds.
    lines = {line["key"]: line for line in drawn["details"]}
    assert "client" not in lines and "location" not in lines
    assert lines["built_area"] == {
        "key": "built_area",
        "label": "Área construída",
        "type": "area",
        "value": "212.5",
    }
    assert lines["responsible"]["value"] == "Laura Mendes"
    assert list(lines) == [line["key"] for line in drawn["details"]]  # one of each
    await photo(client, staff, drawn)
    await publish(client, staff)
    page = (await client.get(f"/?projeto={drawn['id']}", headers=ALINEA)).text
    assert "<dt>Área construída</dt><dd>212,5 m²</dd>" in page
    assert "<dt>Responsável</dt><dd>Laura Mendes</dd>" in page
    assert "<dt>Situação</dt><dd>Concluído</dd>" in page
    assert "Família Teixeira" not in page and "Acácias" not in page


async def test_with_project_members_the_team_is_the_members_not_a_typed_responsible(
    client, db_session, staff
):
    """A41: a "Responsável" typed before the office had members is stale and the
    client page shows the members instead; so does a work drawn from the project."""
    await _project_facts(db_session, status="completed", completed=date(2025, 3, 10))
    await db_session.execute(
        text("UPDATE tenants SET features = features || '{project_members}' WHERE slug = 'alinea'")
    )
    await db_session.execute(
        text(
            "INSERT INTO project_members (tenant_id, project_id, user_id) "
            "SELECT p.tenant_id, p.id, u.id FROM projects p "
            "JOIN users u ON u.tenant_id = p.tenant_id WHERE p.name = 'Casa Jardim'"
        )
    )
    await db_session.commit()
    drawn = await add(client, staff, project_id=await project_id(client))
    team = next(line for line in drawn["details"] if line["key"] == "responsible")
    assert team["value"] == "Ana"  # the office's one member, not "Laura Mendes"
    assert "Laura Mendes" not in str(drawn["details"])


async def test_a_work_in_progress_takes_its_expected_year_unless_given_one(
    client, db_session, staff
):
    await _project_facts(db_session, status="active", delivery=date(2027, 6, 1))
    project = await project_id(client)
    drawn = await add(client, staff, project_id=project)
    assert (drawn["status"], drawn["year"]) == ("in_progress", 2027)
    assert (await add(client, staff, project_id=project, year=2026))["year"] == 2026
    blank = await add(client, staff, title="Loja")
    assert (blank["details"], blank["status"]) == ([], None)


async def test_a_works_sheet_and_photos_show_on_its_page(client, staff):
    """The sheet: built-in details (typed: an area as typed with a comma, a date)
    and the office's own labels, in the order sent, then where the work stands."""
    entry = await add(client, staff, title="Casa Jardim")
    for _ in range(3):
        await photo(client, staff, entry)
    url = f"/api/portfolio/entries/{entry['id']}"
    changed = await client.patch(
        url,
        json={
            "details": [
                {"label": " Fotografia ", "value": "Estúdio Luz"},
                {"key": "built_area", "value": "1250,5"},
                {"key": "start_date", "value": "2024-03-02"},
                {
                    "key": "responsible",
                    "value": "Laura Mendes, Pedro Alves, Ana Costa e Marina Carvalho",
                },
            ],
            "status": "in_progress",
            "credits": "Estúdio Luz",
        },
        headers=staff,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["entries"][0]["details"] == [
        {"key": None, "label": "Fotografia", "type": "text", "value": "Estúdio Luz"},
        {"key": "built_area", "label": "Área construída", "type": "area", "value": "1250.5"},
        {"key": "start_date", "label": "Início", "type": "date", "value": "2024-03-02"},
        {
            "key": "responsible",
            "label": "Responsável",
            "type": "text",
            "value": "Laura Mendes, Pedro Alves, Ana Costa e Marina Carvalho",
        },
    ]
    await publish(client, staff)

    answer = await client.get(f"/?projeto={entry['id']}", headers=ALINEA)
    page = answer.text
    facts = page.split('<dl class="facts">')[1].split("</dl>")[0]
    assert facts == (
        "<div><dt>Fotografia</dt><dd>Estúdio Luz</dd></div>"
        "<div><dt>Área construída</dt><dd>1.250,5 m²</dd></div>"
        "<div><dt>Início</dt><dd>02/03/2024</dd></div>"
        "<div><dt>Responsável</dt>"
        "<dd>Laura Mendes, Pedro Alves, Ana Costa e Marina Carvalho</dd></div>"
        "<div><dt>Situação</dt><dd>Em andamento</dd></div>"
    )
    assert "frame-src" not in answer.headers["content-security-policy"]  # nothing embedded
    assert "Fotos: Estúdio Luz" in page
    # Every photo, the cover too, opens large; the others are shown small.
    assert page.count('class="zoom"') == 2 and 'class="cover zoom"' in page
    assert page.count("?size=card") >= 2 and 'class="lightbox"' in page

    cleared = await client.patch(url, json={"details": [], "status": None}, headers=staff)
    assert (cleared.json()["entries"][0]["details"], cleared.json()["entries"][0]["status"]) == (
        [],
        None,
    )
    bare = (await client.get(f"/?projeto={entry['id']}", headers=ALINEA)).text
    assert '<dl class="facts">' not in bare


async def test_a_line_of_the_sheet_must_be_a_known_detail_or_carry_its_own_name(client, staff):
    entry = await add(client, staff, title="Casa Jardim")
    url = f"/api/portfolio/entries/{entry['id']}"
    for lines in (
        [{"key": "castle", "value": "x"}],  # no such detail
        [{"key": "client", "value": "Família Teixeira"}],  # never the client
        [{"key": "built_area", "value": "1"}, {"key": "built_area", "value": "2"}],  # one of each
        [{"key": "built_area", "value": "grande"}],  # not an area
        [{"key": "start_date", "value": "março"}],  # not a date
        [{"value": "Estúdio Luz"}],  # an own line without its name
        [{"label": "  ", "value": "Estúdio Luz"}],
        [{"label": "Fotografia", "value": "  "}],  # nor without a value
        [{"key": "built_area", "label": "Área", "value": "1"}],  # not both
        [
            {"label": "Fotografia", "value": "x" * 201}
        ],  # a text has room for a team's names, no more
    ):
        refused = await client.patch(url, json={"details": lines}, headers=staff)
        assert refused.status_code == 422, (lines, refused.text)
    assert (await client.get("/api/portfolio", headers=staff)).json()["entries"][0]["details"] == []


@pytest.mark.parametrize(
    ("network", "value", "address"),
    [
        (SocialNetwork.INSTAGRAM, "@alinea.arq", "https://www.instagram.com/alinea.arq"),
        (
            SocialNetwork.INSTAGRAM,
            "instagram.com/alinea.arq/",
            "https://www.instagram.com/alinea.arq",
        ),
        (SocialNetwork.YOUTUBE, "@alinea", "https://www.youtube.com/@alinea"),
        (SocialNetwork.TIKTOK, "@alinea", "https://www.tiktok.com/@alinea"),
        (
            SocialNetwork.PINTEREST,
            "https://br.pinterest.com/alinea/",
            "https://www.pinterest.com/alinea",
        ),
        (
            SocialNetwork.LINKEDIN,
            "linkedin.com/company/alinea",
            "https://www.linkedin.com/company/alinea",
        ),
        (SocialNetwork.LINKEDIN, "@alinea", None),  # LinkedIn has no handles
        (SocialNetwork.FACEBOOK, "https://evil.example/alinea", None),
        (SocialNetwork.FACEBOOK, "https://facebook.com.evil.example/alinea", None),
        (SocialNetwork.INSTAGRAM, "https://www.instagram.com/", None),
        (SocialNetwork.INSTAGRAM, 'https://instagram.com/a"onmouseover="x', None),
    ],
)
def test_a_profile_is_an_address_on_its_own_network(network, value, address):
    assert profile(network, value) == address


async def test_the_offices_networks_show_at_the_top_and_in_the_footer(client, staff):
    """Each network by its mark beside the page's sections at the top, and with
    its name in the footer, in the footer's order."""
    entry = await add(client, staff)
    await photo(client, staff, entry)
    saved = await client.patch(
        "/api/portfolio",
        json={
            "links": {
                "linkedin": "linkedin.com/company/alinea",
                "instagram": "@alinea",
                "vimeo": "",
            }
        },
        headers=staff,
    )
    # In the footer's order, empty ones dropped.
    assert list(saved.json()["links"].items()) == [
        ("instagram", "https://www.instagram.com/alinea"),
        ("linkedin", "https://www.linkedin.com/company/alinea"),
    ]
    await publish(client, staff)
    page = (await client.get("/", headers=ALINEA)).text
    top = page.split('<div class="follow">')[1].split("</div>")[0]
    assert top.count("<a ") == 2 and top.count("<svg ") == 2 and "Instagram</span>" not in top
    assert (
        '<a href="https://www.instagram.com/alinea" rel="noopener" aria-label="Instagram">'
        "<svg" in top
    )
    assert top.index("instagram.com") < top.index("linkedin.com")
    nets = page.split('<p class="nets">')[1].split("</p>")[0]
    assert nets.count("<svg ") == 2 and "<span>Instagram</span></a>" in nets
    assert "<span>LinkedIn</span></a>" in nets

    wrong = await client.patch(
        "/api/portfolio", json={"links": {"facebook": "https://evil.example/x"}}, headers=staff
    )
    assert (wrong.status_code, wrong.json()["error"]) == (422, "portfolio_link_invalid")
    unknown = await client.patch(
        "/api/portfolio", json={"links": {"myspace": "@alinea"}}, headers=staff
    )
    assert unknown.status_code == 422
    kept = (await client.get("/api/portfolio", headers=staff)).json()["links"]
    assert list(kept) == ["instagram", "linkedin"]  # a refused change keeps them all

    await client.patch("/api/portfolio", json={"links": {}}, headers=staff)
    without = (await client.get("/", headers=ALINEA)).text  # no networks: no marks, no block
    assert '<div class="follow">' not in without and '<p class="nets">' not in without


MP4 = b"\x00\x00\x00\x18ftypmp42" + bytes(range(256)) * 4


async def send_video(client, headers, entry, content=MP4, mime_type="video/mp4"):
    """As the painel does: open the upload, send the bytes there, then register."""
    opened = await client.post(
        f"/api/portfolio/entries/{entry['id']}/videos/uploads",
        json={"size": len(content), "mime_type": mime_type},
        headers=headers,
    )
    assert opened.status_code == 200, opened.text
    upload = opened.json()
    sent = await client.put(upload["upload_url"], content=content, headers=ALINEA)
    assert sent.status_code == 201, sent.text
    return await register_video(client, headers, entry, upload["name"])


async def register_video(client, headers, entry, name):
    return await client.post(
        f"/api/portfolio/entries/{entry['id']}/videos",
        data={"name": name},
        files={"poster": ("capa.jpg", JPEG)},
        headers=headers,
    )


async def test_a_video_goes_to_storage_and_plays_from_any_point(client, staff, tmp_path):
    entry = await add(client, staff)
    await photo(client, staff, entry)
    answer = await send_video(client, staff, entry)
    assert answer.status_code == 200, answer.text
    (video,) = answer.json()["entries"][0]["videos"]
    stored = [path.name for path in (tmp_path / "_portfolio").iterdir()]
    assert any(name.endswith(".mp4") for name in stored)
    assert any(name.endswith("-capa.jpg") for name in stored)

    # Not public before the portfolio is.
    visitor = {"host": "alinea.localhost"}
    client.cookies, kept = type(client.cookies)(), client.cookies
    assert (await client.get(video["url"], headers=visitor)).status_code == 404
    client.cookies = kept
    await publish(client, staff)
    client.cookies.clear()

    page = await client.get(f"/?projeto={entry['id']}", headers=ALINEA)
    # A thumbnail among the photos, which opens the video in the viewer: no
    # video plays on the page itself.
    assert f'<a class="zoom film" href="{video["url"]}"' in page.text
    assert f'<img src="{video["poster_url"]}?size=card"' in page.text
    assert page.text.count("<video") == 1 and '<dialog class="lightbox"' in page.text
    assert "media-src 'self'" in page.headers["content-security-policy"]

    whole = await client.get(video["url"], headers=ALINEA)
    assert (whole.status_code, whole.content) == (200, MP4)
    assert whole.headers["content-type"] == "video/mp4"
    assert whole.headers["accept-ranges"] == "bytes"
    # A player asks for parts: seeking, or Safari before it plays at all.
    part = await client.get(video["url"], headers={**ALINEA, "range": "bytes=8-15"})
    assert (part.status_code, part.content) == (206, MP4[8:16])
    assert part.headers["content-range"] == f"bytes 8-15/{len(MP4)}"
    past = await client.get(video["url"], headers={**ALINEA, "range": f"bytes={len(MP4)}-"})
    assert past.status_code == 416
    for size in ("", "?size=card"):
        poster = await client.get(video["poster_url"] + size, headers=ALINEA)
        assert (poster.status_code, poster.content) == (200, JPEG)
    assert (await client.get(video["poster_url"] + "?size=huge", headers=ALINEA)).status_code == 404


async def test_only_a_video_sent_for_the_portfolio_is_registered(client, staff, tmp_path):
    entry = await add(client, staff)
    # Never sent: nothing of that name arrived.
    missing = await register_video(client, staff, entry, f"video-{'0' * 32}.mp4")
    assert (missing.status_code, missing.json()["error"]) == (409, "upload_failed")
    # Any other file of the office (a project's plan) is never one: it would turn public.
    (tmp_path / "_portfolio").mkdir(exist_ok=True)
    (tmp_path / "_portfolio" / "Planta.mp4").write_bytes(MP4)
    other = await register_video(client, staff, entry, "Planta.mp4")
    assert other.status_code == 422
    assert (await client.get("/api/portfolio", headers=staff)).json()["entries"][0]["videos"] == []


@pytest.mark.parametrize(
    ("size", "mime_type", "status"),
    [(1000, "video/quicktime", 415), (200 * 1024 * 1024 + 1, "video/mp4", 413)],
)
async def test_only_mp4_and_webm_videos_up_to_200_mb_are_taken(
    client, staff, size, mime_type, status
):
    entry = await add(client, staff)
    answer = await client.post(
        f"/api/portfolio/entries/{entry['id']}/videos/uploads",
        json={"size": size, "mime_type": mime_type},
        headers=staff,
    )
    assert (answer.status_code, answer.json()["error"]) == (status, "portfolio_video_refused")


async def test_videos_are_reordered_and_removed_with_their_files(client, staff, tmp_path):
    entry = await add(client, staff)
    await send_video(client, staff, entry)
    answer = await send_video(client, staff, entry, MP4[::-1])
    first, second = answer.json()["entries"][0]["videos"]
    url = f"/api/portfolio/entries/{entry['id']}"
    moved = await client.patch(url, json={"videos": [second["id"], first["id"]]}, headers=staff)
    assert [v["id"] for v in moved.json()["entries"][0]["videos"]] == [second["id"], first["id"]]

    removed = await client.delete(f"/api/portfolio/videos/{first['id']}", headers=staff)
    assert [v["id"] for v in removed.json()["entries"][0]["videos"]] == [second["id"]]
    assert len(list((tmp_path / "_portfolio").iterdir())) == 2  # the other video and its poster
    await client.delete(f"/api/portfolio/entries/{entry['id']}", headers=staff)
    assert list((tmp_path / "_portfolio").iterdir()) == []
