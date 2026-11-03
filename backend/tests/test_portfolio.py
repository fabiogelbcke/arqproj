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

    grid = lambda page: page.split('class="works"')[1]  # noqa: E731
    one = (await client.get("/?tipo=interiors", headers=ALINEA)).text
    assert "Apto Mar" in grid(one) and "Casa Jardim" not in grid(one) and "Loja" not in grid(one)
    assert 'aria-current="page">Interiores' in one
    assert one.count('class="slide"') == 3  # the carousel shows them all still
    nonsense = (await client.get("/?tipo=castle", headers=ALINEA)).text
    assert all(title in grid(nonsense) for title in ("Casa Jardim", "Apto Mar", "Loja"))


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
    assert (drawn["area"], drawn["status"], drawn["year"], drawn["team"], drawn["place"]) == (
        "212.50",
        "completed",
        2025,
        "Laura Mendes",
        "",
    )
    await photo(client, staff, drawn)
    await publish(client, staff)
    page = (await client.get(f"/?projeto={drawn['id']}", headers=ALINEA)).text
    assert "<dt>Área</dt><dd>212,5 m²</dd>" in page
    assert "<dt>Situação</dt><dd>Concluído</dd>" in page
    assert "<dt>Equipe</dt><dd>Laura Mendes</dd>" in page
    assert "Família Teixeira" not in page and "Acácias" not in page


async def test_a_work_in_progress_takes_its_expected_year_unless_given_one(
    client, db_session, staff
):
    await _project_facts(db_session, status="active", delivery=date(2027, 6, 1))
    project = await project_id(client)
    drawn = await add(client, staff, project_id=project)
    assert (drawn["status"], drawn["year"]) == ("in_progress", 2027)
    assert (await add(client, staff, project_id=project, year=2026))["year"] == 2026
    blank = await add(client, staff, title="Loja")
    assert (blank["area"], blank["status"], blank["team"]) == (None, None, "")


async def test_a_works_facts_and_photos_show_on_its_page(client, staff):
    entry = await add(client, staff, title="Casa Jardim")
    for _ in range(3):
        await photo(client, staff, entry)
    url = f"/api/portfolio/entries/{entry['id']}"
    changed = await client.patch(
        url,
        json={
            "area": 1250.5,
            "status": "in_progress",
            "team": "Laura Mendes e Pedro Alves",
            "credits": "Estúdio Luz",
        },
        headers=staff,
    )
    assert changed.status_code == 200, changed.text
    await publish(client, staff)

    answer = await client.get(f"/?projeto={entry['id']}", headers=ALINEA)
    page = answer.text
    assert "<dd>1.250,5 m²</dd>" in page and "<dd>Em andamento</dd>" in page
    assert "frame-src" not in answer.headers["content-security-policy"]  # nothing embedded
    assert "Fotos: Estúdio Luz" in page
    # Every photo, the cover too, opens large; the others are shown small.
    assert page.count('class="zoom"') == 2 and 'class="cover zoom"' in page
    assert page.count("?size=card") >= 2 and 'class="lightbox"' in page

    cleared = await client.patch(url, json={"area": None, "status": None}, headers=staff)
    assert (cleared.json()["entries"][0]["area"], cleared.json()["entries"][0]["status"]) == (
        None,
        None,
    )


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


async def test_the_offices_networks_show_in_the_footer(client, staff):
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
    assert '<a href="https://www.instagram.com/alinea" rel="noopener">Instagram</a>' in page

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
