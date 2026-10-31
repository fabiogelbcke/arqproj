"""The office's portfolio: edited in the painel, behind the `portfolio` feature
(A40), and shown at its own address's root once published."""

import pytest
from sqlalchemy import text

from backend.identity.models import Role
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
    root = await client.get("/", headers=ALINEA)
    assert root.status_code == 200 and "UNIO" in root.text


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
    assert "script-src" not in root.headers["content-security-policy"]  # nothing runs

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
