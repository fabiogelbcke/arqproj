"""Step 2.4: the client's password, and the page's address, from the painel."""

import pytest

from backend.tests import test_office
from backend.tests.test_office import ALINEA
from backend.web import attempts
from backend.web.auth import COOKIE

owner = test_office.owner  # fixtures

pytestmark = pytest.mark.anyio

SEED_PASSWORD = "demo-senha"  # Refúgio da Mantiqueira's, in the fictional seed
PROTECTED = "refugio-da-mantiqueira"


@pytest.fixture(autouse=True)
def fresh_attempts():
    attempts.reset()
    yield
    attempts.reset()


class Roles:
    """Switch the test client between the office's staff and a client's browser
    (which keeps its unlock cookies)."""

    def __init__(self, client):
        self.client = client
        self.session = client.cookies.get(COOKIE)

    def visitor(self):
        self.client.cookies.delete(COOKIE)

    def staff(self):
        self.client.cookies.set(COOKIE, self.session)


async def summary(client, slug):
    listed = (await client.get("/api/projects", headers=ALINEA)).json()
    return next(p for p in listed if p["slug"] == slug)


async def change(client, headers, target, **body):
    """PATCH the project now at address `target`."""
    found = await summary(client, target)
    return await client.patch(
        f"/api/projects/{found['id']}",
        json={"row_version": found["row_version"], **body},
        headers=headers,
    )


async def unlock(client, password, slug=PROTECTED):
    return await client.post(
        f"/api/pages/{slug}/unlock", json={"password": password}, headers=ALINEA
    )


async def page_status(client, slug=PROTECTED):
    return (await client.get(f"/api/pages/{slug}", headers=ALINEA)).status_code


# -- unlocking ------------------------------------------------------------------------


async def test_the_right_password_unlocks_the_page_on_this_device(client, owner):
    Roles(client).visitor()
    assert await page_status(client) == 403
    wrong = await unlock(client, "chute")
    assert wrong.headers["cache-control"] == "private, no-store"
    response = await unlock(client, SEED_PASSWORD)
    assert response.status_code == 204
    assert response.headers["cache-control"] == "private, no-store"
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Max-Age=7776000" in cookie  # 90 days
    page = await client.get(f"/api/pages/{PROTECTED}", headers=ALINEA)
    assert (page.status_code, page.json()["name"]) == (200, "Refúgio da Mantiqueira")
    assert page.json()["staff"] is None
    assert page.headers["cache-control"] == "private, no-store"  # never a shared cache


async def test_a_wrong_password_unlocks_nothing(client, owner):
    Roles(client).visitor()
    response = await unlock(client, "chute")
    assert (response.status_code, response.json()) == (401, {"error": "wrong_page_password"})
    assert await page_status(client) == 403


async def test_five_wrong_tries_make_the_device_wait(client, owner, monkeypatch):
    Roles(client).visitor()
    clock = [1000.0]
    monkeypatch.setattr(attempts.time, "monotonic", lambda: clock[0])
    for _ in range(5):
        assert (await unlock(client, "chute")).status_code == 401
    blocked = await unlock(client, SEED_PASSWORD)  # even the right one waits now
    assert (blocked.status_code, blocked.json()) == (429, {"error": "too_many_attempts"})
    clock[0] += 15 * 60 + 1
    assert (await unlock(client, SEED_PASSWORD)).status_code == 204


async def test_the_wait_starts_at_the_fifth_wrong_try(client, owner, monkeypatch):
    """Five tries spread over 14 minutes still mean 15 minutes from the fifth."""
    Roles(client).visitor()
    clock = [1000.0]
    monkeypatch.setattr(attempts.time, "monotonic", lambda: clock[0])
    for minute in (0, 3, 6, 9, 14):
        clock[0] = 1000.0 + minute * 60
        assert (await unlock(client, "chute")).status_code == 401
    clock[0] = 1000.0 + 16 * 60  # the first try is now over 15 minutes old
    assert (await unlock(client, SEED_PASSWORD)).status_code == 429
    clock[0] = 1000.0 + 29 * 60 + 1  # 15 minutes after the fifth
    assert (await unlock(client, SEED_PASSWORD)).status_code == 204


def test_guesses_sent_all_at_once_still_stop_at_five():
    """Tries are counted when they start, not when their (slow) hash ends: a
    batch sent at once gets five checks, and the sixth waits."""
    attempts.reset()
    admitted = [attempts.admit("p", "device", now=1000.0) for _ in range(8)]
    assert admitted == [True] * 5 + [False] * 3
    for _ in range(5):  # the five finish, all wrong
        attempts.failed("p", "device", now=1001.0)
    assert not attempts.admit("p", "device", now=1002.0)  # now waiting 15 minutes
    assert attempts.admit("p", "device", now=1001.0 + 15 * 60 + 1)


def test_a_right_password_frees_its_reservation():
    attempts.reset()
    assert attempts.admit("p", "device", now=1.0)
    attempts.succeeded("p", "device")
    assert all(attempts.admit("p", "device", now=2.0) for _ in range(5))


async def test_an_unlocked_protected_pages_calendar_file_is_private(client, db_session, owner):
    from sqlalchemy import text

    from backend.tests.test_office import tenant_id

    await db_session.execute(
        text(
            "INSERT INTO meetings (tenant_id, project_id, title, starts_at, ends_at) "
            "SELECT tenant_id, project_id, 'Entrega', now() + interval '1 day', "
            "now() + interval '25 hours' FROM project_slugs WHERE slug = :s AND tenant_id = :t"
        ),
        {"s": PROTECTED, "t": await tenant_id(db_session, "alinea")},
    )
    Roles(client).visitor()
    await unlock(client, SEED_PASSWORD)
    response = await client.get(f"/api/pages/{PROTECTED}/meeting.ics", headers=ALINEA)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"


async def test_an_unlock_for_one_project_opens_no_other(client, db_session, owner):
    roles = Roles(client)
    # A second protected project, with the same password.
    protected = await change(
        client, owner, "casa-jardim", access_mode="password", password=SEED_PASSWORD
    )
    assert protected.status_code == 200
    roles.visitor()
    await unlock(client, SEED_PASSWORD)
    assert await page_status(client) == 200
    assert await page_status(client, "casa-jardim") == 403


async def test_a_tampered_unlock_cookie_opens_nothing(client, owner):
    Roles(client).visitor()
    await unlock(client, SEED_PASSWORD)
    for name in list(client.cookies.keys()):
        if name.startswith("unlock-"):
            client.cookies.set(name, client.cookies.get(name)[:-4] + "AAAA")
    assert await page_status(client) == 403


@pytest.mark.parametrize("slug", ["casa-jardim", "casa-das-oliveiras", "nao-existe"])
async def test_only_a_published_protected_page_takes_a_password(client, owner, slug):
    Roles(client).visitor()
    response = await unlock(client, SEED_PASSWORD, slug)
    assert (response.status_code, response.json()) == (404, {"error": "page_not_found"})


# -- access settings ------------------------------------------------------------------


async def test_a_new_password_locks_out_every_device(client, owner):
    roles = Roles(client)
    roles.visitor()
    await unlock(client, SEED_PASSWORD)
    assert await page_status(client) == 200
    roles.staff()
    changed = await change(client, owner, PROTECTED, access_mode="password", password="nova-senha")
    assert changed.status_code == 200, changed.text
    roles.visitor()
    assert await page_status(client) == 403  # the earlier unlock no longer counts
    assert (await unlock(client, SEED_PASSWORD)).status_code == 401
    assert (await unlock(client, "nova-senha")).status_code == 204


async def test_making_a_page_public_opens_it_and_forgets_the_password(client, owner):
    roles = Roles(client)
    changed = await change(client, owner, PROTECTED, access_mode="public")
    assert (changed.status_code, changed.json()["access_mode"]) == (200, "public")
    roles.visitor()
    assert await page_status(client) == 200
    roles.staff()
    # Back to a password: the old one is gone, so a new one is needed.
    again = await change(client, owner, PROTECTED, access_mode="password")
    assert (again.status_code, again.json()["error"]) == (422, "password_required")


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ({"access_mode": "password"}, "password_required"),  # Casa Jardim has none
        ({"access_mode": "password", "password": "12345"}, "password_too_short"),
    ],
)
async def test_password_access_needs_a_password_of_six_or_more(client, owner, body, error):
    response = await change(client, owner, "casa-jardim", **body)
    assert (response.status_code, response.json()["error"]) == (422, error)


async def test_keeping_the_password_needs_no_retyping(client, owner):
    """Saving the dialog with password access and an empty field keeps it."""
    response = await change(client, owner, PROTECTED, access_mode="password", name="Refúgio")
    assert response.status_code == 200, response.text
    Roles(client).visitor()
    assert (await unlock(client, SEED_PASSWORD)).status_code == 204


# -- the page's address ---------------------------------------------------------------


async def test_a_new_address_keeps_the_old_link_working(client, owner):
    changed = await change(client, owner, "casa-jardim", slug="Casa-Jardim-Lagoa")
    assert (changed.status_code, changed.json()["slug"]) == (200, "casa-jardim-lagoa")
    Roles(client).visitor()
    assert await page_status(client, "casa-jardim-lagoa") == 200
    old = await client.get("/casa-jardim", headers=ALINEA)
    assert (old.status_code, old.headers["location"]) == (301, "/casa-jardim-lagoa")


async def test_an_address_the_project_had_before_can_come_back(client, owner):
    """Apartamento Atlântico was at apto-atlantico before (the seed)."""
    changed = await change(client, owner, "apartamento-atlantico", slug="apto-atlantico")
    assert (changed.status_code, changed.json()["slug"]) == (200, "apto-atlantico")
    old = await client.get("/apartamento-atlantico", headers=ALINEA)
    assert old.headers["location"] == "/apto-atlantico"


async def test_another_projects_address_is_never_given_away(client, owner):
    """Not its current address, and not one it had before (A29)."""
    for slug in ("casa-jardim", "apto-atlantico"):
        response = await change(client, owner, "casa-das-oliveiras", slug=slug)
        assert response.status_code == 409
        assert response.json()["error"] == "slug_taken"
        assert response.json()["conflict_name"] in (
            "Casa Jardim",
            "Apartamento Atlântico — Copacabana",
        )


@pytest.mark.parametrize("slug", ["Casa Jardim", "painel", "-casa", "", "a" * 81])
async def test_a_bad_address_is_refused(client, owner, slug):
    response = await change(client, owner, "casa-jardim", slug=slug)
    assert (response.status_code, response.json()["error"]) == (422, "invalid_slug")


async def test_the_same_address_changes_nothing(client, owner):
    before = await summary(client, "casa-jardim")
    response = await change(client, owner, "casa-jardim", slug="casa-jardim")
    assert response.status_code == 200
    assert response.json()["row_version"] == before["row_version"]


async def test_a_faked_forwarded_address_doesnt_make_a_new_device():
    """The visitor controls the start of X-Forwarded-For; Google's front end adds
    the address it saw at the end (Cloud Run alone)."""
    from types import SimpleNamespace

    settings = SimpleNamespace(deployed=True, forwarded_hops=1)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=settings)),
        headers={"x-forwarded-for": "1.2.3.4, 203.0.113.9"},
        client=None,
    )
    assert attempts.device(request) == "203.0.113.9"
    request.headers = {"x-forwarded-for": "5.6.7.8, 203.0.113.9"}
    assert attempts.device(request) == "203.0.113.9"  # same device, whatever it sends


async def test_behind_the_load_balancer_the_visitor_is_the_second_to_last():
    """A21: the balancer adds the visitor's address, then Cloud Run adds the
    balancer's own; counting the balancer as the visitor would put everyone in
    one bucket, so five tries by anyone would block everyone."""
    from types import SimpleNamespace

    settings = SimpleNamespace(deployed=True, forwarded_hops=2)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=settings)),
        headers={"x-forwarded-for": "1.2.3.4, 203.0.113.9, 35.191.0.1"},
        client=None,
    )
    assert attempts.device(request) == "203.0.113.9"
    request.headers = {"x-forwarded-for": "198.51.100.7, 35.191.0.1"}
    assert attempts.device(request) == "198.51.100.7"  # another visitor, another device
    # Too few entries: never the balancer, whether it's the header's or the socket's.
    request.headers = {"x-forwarded-for": "35.191.0.1"}
    request.client = SimpleNamespace(host="35.191.0.1")
    assert attempts.device(request) == "unknown"


async def test_two_people_giving_the_same_new_address_at_once(client, owner, monkeypatch):
    """The second loses with "address taken", not an error page."""
    from backend.web import project_settings

    real = project_settings._move_address

    async def taken_meanwhile(db, project_id, slug):
        from sqlalchemy import text

        await db.execute(
            text(
                "INSERT INTO project_slugs (project_id, slug, is_current) "
                "SELECT project_id, :s, false FROM project_slugs WHERE slug = 'casa-das-oliveiras'"
            ),
            {"s": slug},
        )
        await real(db, project_id, slug)

    monkeypatch.setattr(project_settings, "_move_address", taken_meanwhile)
    response = await change(client, owner, "casa-jardim", slug="nova-casa")
    assert (response.status_code, response.json()["error"]) == (409, "slug_taken")
