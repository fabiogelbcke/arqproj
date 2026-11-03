"""The bundled stock cover photos: a new project's first cover, and the photos
staff can choose instead of uploading one (plan section 10)."""

import json

import pytest
from PIL import Image

from backend.projects import cover_photos
from backend.projects.cover_photos import PHOTOS_DIR, PhotoSize, cover_photo, cover_photo_names
from backend.tests import test_office
from backend.tests.test_office import ALINEA, PNG
from backend.tests.test_project_settings import change, project, upload
from backend.tests.test_projects_api import create
from backend.web import covers

owner = test_office.owner  # fixtures
on_google = test_office.on_google

pytestmark = pytest.mark.anyio


def full(name):
    return cover_photo(name, PhotoSize.FULL).read_bytes()


@pytest.fixture
def picks(monkeypatch):
    """The random pick, as a list the test fills: each creation takes the next."""
    names = []
    monkeypatch.setattr(covers, "random_cover_photo", lambda: names.pop(0))
    return names


async def listed(client):
    return {p["slug"]: p for p in (await client.get("/api/projects", headers=ALINEA)).json()}


# -- a new project's cover ------------------------------------------------------------


async def test_a_new_project_starts_with_a_stock_photo_as_its_real_cover(
    client, owner, tmp_path, picks
):
    picks.append("capa-42")
    response = await create(client, owner)
    assert response.status_code == 201, response.text
    url = response.json()["cover_url"]
    assert url is not None
    assert (tmp_path / "Casa do Lago" / "_capa" / "capa.jpg").read_bytes() == full("capa-42")
    shown = await client.get(url, headers=ALINEA)
    assert (shown.status_code, shown.headers["content-type"]) == (200, "image/jpeg")


async def test_the_pick_is_one_of_the_bundled_photos():
    assert {cover_photos.random_cover_photo() for _ in range(50)} <= set(cover_photo_names())


async def test_a_resent_creation_keeps_the_cover_it_was_given(client, owner, tmp_path, picks):
    picks.extend(["capa-03", "capa-60"])
    first = (await create(client, owner)).json()
    again = await create(client, owner)
    assert again.status_code == 201 and again.json()["cover_url"] == first["cover_url"]
    assert (tmp_path / "Casa do Lago" / "_capa" / "capa.jpg").read_bytes() == full("capa-03")
    assert picks == ["capa-60"]  # never picked a second time


async def test_a_failed_cover_still_creates_the_project_without_one(
    client, owner, tmp_path, monkeypatch
):
    def missing(name):
        raise OSError("the photo could not be read")

    monkeypatch.setattr(covers, "stock_photo_bytes", missing)
    response = await create(client, owner)
    assert response.status_code == 201, response.text
    assert response.json()["cover_url"] is None
    assert (await listed(client))["casa-do-lago"]["cover_url"] is None
    assert (tmp_path / "Casa do Lago" / "01 - Briefing").is_dir()


async def test_on_drive_the_cover_goes_into_the_new_projects_capa_folder(client, owner, on_google):
    fake, _ = on_google
    response = await create(client, owner)
    assert response.status_code == 201, response.text
    assert response.json()["cover_url"] is not None
    assert fake.calls.count("POST /upload/drive/v3/files") == 1


async def test_on_drive_a_failed_upload_still_creates_the_project(client, owner, on_google):
    fake, _ = on_google
    fake.upload_down = True
    response = await create(client, owner)
    assert response.status_code == 201, response.text
    assert response.json()["cover_url"] is None
    assert response.json()["stage_count"] == 7


async def test_a_removed_default_cover_stays_removed(client, owner, tmp_path):
    created = (await create(client, owner)).json()
    removed = await client.delete(f"/api/projects/{created['id']}/cover", headers=owner)
    assert removed.json()["cover_url"] is None
    assert (await listed(client))["casa-do-lago"]["cover_url"] is None
    assert list((tmp_path / "Casa do Lago" / "_capa").iterdir()) == []


async def test_a_resent_creation_after_removing_the_cover_picks_none(client, owner, tmp_path):
    created = (await create(client, owner)).json()
    await client.delete(f"/api/projects/{created['id']}/cover", headers=owner)
    again = await create(client, owner)
    assert again.status_code == 201 and again.json()["cover_url"] is None


# -- choosing a stock photo -----------------------------------------------------------


async def choose(client, headers, found, name):
    return await client.put(
        f"/api/projects/{found['id']}/cover/stock", json={"name": name}, headers=headers
    )


async def test_a_stock_photo_can_replace_an_uploaded_cover(client, owner, tmp_path):
    found = await project(client)
    uploaded = (await upload(client, owner, found, PNG)).json()
    response = await choose(client, owner, found, "capa-56")
    assert response.status_code == 200, response.text
    assert response.json()["cover_url"] != uploaded["cover_url"]
    capa = tmp_path / "Casa Jardim" / "_capa"
    assert [p.name for p in capa.iterdir()] == ["capa.jpg"]  # the upload is gone
    assert (capa / "capa.jpg").read_bytes() == full("capa-56")


async def test_each_new_cover_gets_a_new_address_even_under_the_same_file_name(
    client, owner, tmp_path
):
    """Locally both are `_capa/capa.jpg`: the address must still change, or the
    browser keeps showing the old photo from its cache."""
    found = await project(client)
    first = (await choose(client, owner, found, "capa-01")).json()["cover_url"]
    second = (await choose(client, owner, found, "capa-02")).json()["cover_url"]
    assert first != second


async def test_a_project_without_a_cover_can_take_a_stock_photo(client, owner, tmp_path):
    response = await choose(client, owner, await project(client), "capa-01")
    assert response.status_code == 200 and response.json()["cover_url"] is not None


@pytest.mark.parametrize("name", ["capa-999", "../full/capa-01", "capa-01.jpg", ""])
async def test_only_a_bundled_photo_can_be_chosen(client, owner, tmp_path, name):
    found = await project(client)
    response = await choose(client, owner, found, name)
    assert (response.status_code, response.json()["error"]) == (404, "cover_photo_not_found")
    assert (await project(client))["cover_url"] is None
    assert not (tmp_path / "Casa Jardim").exists()


async def test_an_archived_project_takes_no_stock_photo(client, owner, tmp_path):
    archived = (await change(client, owner, await project(client), status="archived")).json()
    response = await choose(client, owner, archived, "capa-01")
    assert (response.status_code, response.json()["error"]) == (409, "project_archived")


async def test_choosing_needs_the_csrf_token(client, owner):
    found = await project(client)
    response = await choose(client, {**ALINEA}, found, "capa-01")
    assert response.status_code == 403


# -- the photos for the picker --------------------------------------------------------


async def test_staff_get_every_photo_for_the_picker(client, owner):
    response = await client.get("/api/cover-photos", headers=ALINEA)
    assert response.status_code == 200
    photos = response.json()
    assert [p["name"] for p in photos] == list(cover_photo_names())
    small = await client.get(photos[0]["small_url"], headers=ALINEA)
    assert (small.status_code, small.headers["content-type"]) == (200, "image/jpeg")
    assert small.content == cover_photo(photos[0]["name"], PhotoSize.SMALL).read_bytes()


@pytest.mark.parametrize(
    ("path", "status"),
    [("capa-999/small", 404), ("capa-01/huge", 422), ("..%2Ffull%2Fcapa-01/small", 404)],
)
async def test_only_bundled_photos_are_served(client, owner, path, status):
    assert (await client.get(f"/api/cover-photos/{path}", headers=ALINEA)).status_code == status


async def test_the_photos_are_for_signed_in_staff(client, owner):
    client.cookies.clear()
    assert (await client.get("/api/cover-photos", headers=ALINEA)).status_code == 401
    assert (await client.get("/api/cover-photos/capa-01/small", headers=ALINEA)).status_code == 401


# -- the bundled set ------------------------------------------------------------------


def photo_set_problems(photos_dir) -> list[str]:
    """Every photo comes in both sizes, as a 3:2 JPEG, with its source recorded;
    every recorded source is a photo."""
    problems = []
    licensed = {e["file"]: e for e in json.loads((photos_dir / "LICENSES.json").read_text())}
    sizes = {size: {p.name for p in (photos_dir / size).glob("*.jpg")} for size in PhotoSize}
    every = set().union(*sizes.values()) | set(licensed)
    for name in sorted(every):
        for size in PhotoSize:
            if name not in sizes[size]:
                problems.append(f"{name}: no {size} size")
                continue
            with Image.open(photos_dir / size / name) as image:
                width, height = image.size
                if image.format != "JPEG" or abs(width / height - 1.5) > 0.01:
                    problems.append(f"{name}: {size} is {image.format} {width}x{height}")
        entry = licensed.get(name)
        if entry is None or not entry.get("license") or not entry.get("source"):
            problems.append(f"{name}: no source or license recorded")
    return problems


def test_every_bundled_photo_is_licensed_and_in_both_sizes():
    assert photo_set_problems(PHOTOS_DIR) == []
    assert len(cover_photo_names()) >= 10


def test_the_check_above_catches_a_photo_without_a_license(tmp_path):
    """Self-test: a copy of the set with one photo's record removed, and one
    photo missing its small size, fails the check."""
    for size in PhotoSize:
        (tmp_path / size).mkdir()
        for name in ["capa-01.jpg", "capa-02.jpg"]:
            if not (size is PhotoSize.SMALL and name == "capa-02.jpg"):
                (tmp_path / size / name).write_bytes((PHOTOS_DIR / size / name).read_bytes())
    entries = json.loads((PHOTOS_DIR / "LICENSES.json").read_text())
    kept = [e for e in entries if e["file"] == "capa-02.jpg"]
    (tmp_path / "LICENSES.json").write_text(json.dumps(kept))
    assert photo_set_problems(tmp_path) == [
        "capa-01.jpg: no source or license recorded",
        "capa-02.jpg: no small size",
    ]
