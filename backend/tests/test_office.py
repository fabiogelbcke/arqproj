"""The office's details and logo (Configurações → Escritório)."""

from urllib.parse import parse_qs

import httpx2
import pytest
from sqlalchemy import select, text

from backend.commands.seed import seed
from backend.identity import accounts
from backend.identity.models import Role
from backend.security import keys
from backend.storage.google import GoogleDriveStorage
from backend.storage.models import ReaderStatus, StorageConnection, StorageKind, WriterStatus
from backend.tenancy.models import Tenant
from backend.web import auth, drive

pytestmark = pytest.mark.anyio

ALINEA = {"host": "alinea.localhost"}
NORTE = {"host": "norte.localhost"}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
SVG = (
    b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
)


async def tenant_id(db, slug):
    return await db.scalar(select(Tenant.id).where(Tenant.slug == slug))


async def sign_in_as(client, db, email, role, host=ALINEA, slug="alinea"):
    t = await tenant_id(db, slug)
    await db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(t)})
    await accounts.create_user(db, email=email, name="Ana", password="a good password", role=role)
    response = await client.post(
        "/api/session", json={"email": email, "password": "a good password"}, headers=host
    )
    return {**host, auth.CSRF_HEADER: response.json()["csrf_token"]}


@pytest.fixture
async def owner(app, client, db_session, tmp_path):
    await seed(db_session)  # alinea uses local folder storage
    app.state.settings = app.state.settings.model_copy(update={"local_storage_root": str(tmp_path)})
    return await sign_in_as(client, db_session, "dona@alinea.example", Role.OWNER)


async def upload(client, headers, content, name="logo.png"):
    return await client.put("/api/office/logo", files={"file": (name, content)}, headers=headers)


async def test_the_name_starts_as_the_registrys_and_can_be_changed(client, owner):
    assert (await client.get("/api/office", headers=ALINEA)).json()["name"] == "Alinea (dev)"
    changed = await client.patch(
        "/api/office",
        json={"name": "  ALÍNEA ARQUITETOS ", "contact_email": "Contato@Alinea.com.br"},
        headers=owner,
    )
    assert changed.status_code == 200
    assert (changed.json()["name"], changed.json()["contact_email"]) == (
        "ALÍNEA ARQUITETOS",
        "contato@alinea.com.br",
    )
    # Everywhere the office's name shows.
    assert (await client.get("/api/tenant", headers=ALINEA)).json()["name"] == "ALÍNEA ARQUITETOS"
    assert (await client.get("/api/me", headers=ALINEA)).json()[
        "tenant_name"
    ] == "ALÍNEA ARQUITETOS"


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ({"name": "   "}, "invalid_office_name"),
        ({"name": "x" * 81}, "invalid_office_name"),
        ({"contact_email": "not-an-email"}, "invalid_email"),
    ],
)
async def test_bad_details_are_refused(client, owner, body, error):
    response = await client.patch("/api/office", json=body, headers=owner)
    assert (response.status_code, response.json()) == (422, {"error": error})


async def test_members_see_the_details_but_cannot_change_them(client, db_session, owner):
    client.cookies.clear()
    member = await sign_in_as(client, db_session, "membro@alinea.example", Role.MEMBER)
    assert (await client.get("/api/office", headers=ALINEA)).json()["can_manage"] is False
    for response in (
        await client.patch("/api/office", json={"name": "X"}, headers=member),
        await upload(client, member, PNG),
    ):
        assert (response.status_code, response.json()) == (403, {"error": "owner_only"})


async def test_another_office_never_sees_these_details(client, db_session, owner):
    await client.patch("/api/office", json={"name": "ALÍNEA ARQUITETOS"}, headers=owner)
    assert (await client.get("/api/tenant", headers=NORTE)).json()["name"] == "Estúdio Norte (dev)"


async def test_a_logo_is_stored_in_the_offices_folder_and_served_safely(client, owner, tmp_path):
    saved = await upload(client, owner, PNG)
    assert saved.status_code == 200
    assert (tmp_path / "_marca" / "logo.png").read_bytes() == PNG
    served = await client.get(saved.json()["logo_url"], headers=ALINEA)
    assert (served.status_code, served.content) == (200, PNG)
    assert served.headers["content-type"] == "image/png"


async def test_an_svg_with_a_script_is_served_so_nothing_in_it_runs(client, owner):
    saved = await upload(client, owner, SVG, "logo.svg")
    served = await client.get(saved.json()["logo_url"], headers=ALINEA)
    assert served.headers["content-type"] == "image/svg+xml"
    assert "sandbox" in served.headers["content-security-policy"]
    assert "default-src 'none'" in served.headers["content-security-policy"]
    assert served.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize(
    ("content", "status", "error"),
    [
        (b"hello, not an image", 415, "logo_wrong_type"),
        (b"%PDF-1.4 renamed.png", 415, "logo_wrong_type"),  # the bytes decide, not the name
        (PNG + b"\x00" * 5 * 1024 * 1024, 413, "logo_too_large"),
    ],
)
async def test_only_small_images_are_accepted_as_a_logo(client, owner, content, status, error):
    response = await upload(client, owner, content)
    assert (response.status_code, response.json()) == (status, {"error": error})


async def test_first_steps_tick_office_details_once_email_and_logo_are_set(client, owner):
    assert (await client.get("/api/onboarding", headers=ALINEA)).json()["office_details"] is False
    await client.patch("/api/office", json={"contact_email": "a@b.com"}, headers=owner)
    assert (await client.get("/api/onboarding", headers=ALINEA)).json()["office_details"] is False
    await upload(client, owner, PNG)
    assert (await client.get("/api/onboarding", headers=ALINEA)).json()["office_details"] is True


# -- on Google Drive ------------------------------------------------------------------


class FakeGoogle:
    def __init__(self):
        self.calls, self.refresh_refused, self.next_id = [], False, 0
        self.token_service_down = False
        self.upload_down = False

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        path, method = request.url.path, request.method
        self.calls.append(f"{method} {path}")
        if path == "/token":
            if self.token_service_down:
                return httpx2.Response(503)
            if self.refresh_refused:
                return httpx2.Response(400, json={"error": "invalid_grant"})
            assert parse_qs(request.content.decode())["refresh_token"] == ["refresh-1"]
            return httpx2.Response(200, json={"access_token": "writer"})
        if method == "POST" and path.startswith("/upload") and self.upload_down:
            return httpx2.Response(503)
        if method == "POST":
            self.next_id += 1
            return httpx2.Response(200, json={"id": f"new{self.next_id}"})
        if method == "PATCH" or method == "GET":
            return httpx2.Response(200, json={"id": "x"})
        return httpx2.Response(500)


@pytest.fixture
async def on_google(app, db_session, owner):
    fake = FakeGoogle()
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(fake))

    async def reader_token():
        return "reader"

    app.state.http = http
    app.state.google = GoogleDriveStorage(reader_token, http)
    app.state.settings = app.state.settings.model_copy(
        update={
            "google_oauth_client_id": "id",
            "google_oauth_client_secret": "secret",
            "drive_reader_identity": "reader@x.iam",
        }
    )
    t = await tenant_id(db_session, "alinea")
    connection = await db_session.scalar(
        select(StorageConnection).where(StorageConnection.tenant_id == t)
    )
    connection.kind = StorageKind.GOOGLE
    connection.root_id = "root1"
    connection.reader_identity = "reader@x.iam"
    connection.writer_token = keys.encrypt(
        app.state.settings.app_secret, drive.TOKEN_PURPOSE, "refresh-1"
    )
    connection.writer_status = WriterStatus.CONNECTED
    connection.reader_status = ReaderStatus.OK
    await db_session.flush()
    return fake, connection


async def test_on_drive_the_logo_goes_into_a_brand_folder_and_replaces_the_old(
    client, owner, on_google
):
    fake, _ = on_google
    first = await upload(client, owner, PNG)
    assert first.status_code == 200, first.text
    assert "POST /drive/v3/files" in fake.calls  # the _marca folder
    assert "POST /upload/drive/v3/files" in fake.calls
    trashed_before = fake.calls.count("PATCH /drive/v3/files/new2")
    await upload(client, owner, PNG)
    assert fake.calls.count("PATCH /drive/v3/files/new2") == trashed_before + 1  # old logo


async def test_a_refused_grant_marks_the_connection_expired(client, db_session, owner, on_google):
    fake, connection = on_google
    fake.refresh_refused = True
    response = await upload(client, owner, PNG)
    assert (response.status_code, response.json()) == (409, {"error": "drive_expired"})
    await db_session.refresh(connection)
    assert connection.writer_status is WriterStatus.EXPIRED


async def test_a_passing_google_failure_does_not_disconnect_the_office(
    client, db_session, owner, on_google
):
    fake, connection = on_google
    fake.token_service_down = True
    response = await upload(client, owner, PNG)
    assert (response.status_code, response.json()) == (503, {"error": "drive_connect_failed"})
    await db_session.refresh(connection)
    assert connection.writer_status is WriterStatus.CONNECTED  # still connected


async def test_a_passing_drive_failure_during_upload_says_try_again(client, owner, on_google):
    fake, _ = on_google
    fake.upload_down = True
    response = await upload(client, owner, PNG)
    assert (response.status_code, response.json()) == (503, {"error": "drive_connect_failed"})


async def test_no_upload_while_the_portal_cannot_read_the_folder(
    client, db_session, owner, on_google
):
    fake, connection = on_google
    connection.reader_status = ReaderStatus.NO_ACCESS
    await db_session.flush()
    response = await upload(client, owner, PNG)
    assert (response.status_code, response.json()) == (409, {"error": "drive_unreadable"})
    assert not any("upload" in c for c in fake.calls)


def test_each_logo_change_gets_a_new_address():
    """Two changes within the same second must not share an address, or browsers
    keep showing the first logo for the cache's five minutes."""
    from datetime import UTC, datetime, timedelta

    from backend.office.models import LogoType, OfficeProfile
    from backend.web.office import _out

    staff = auth.CurrentStaff(None, "a@b.c", "A", Role.OWNER, None, "csrf")
    when = datetime(2026, 10, 15, 12, 0, 0, 100_000, tzinfo=UTC)
    urls = set()
    for moment in (when, when + timedelta(milliseconds=300)):
        profile = OfficeProfile(
            display_name="A", logo_file_id="f", logo_type=LogoType.PNG, updated_at=moment
        )
        urls.add(_out(None, profile, staff).logo_url)
    assert len(urls) == 2


async def test_without_a_connection_the_logo_waits_for_drive(client, db_session, owner):
    t = await tenant_id(db_session, "alinea")
    await db_session.execute(text("DELETE FROM storage_connections WHERE tenant_id = :t"), {"t": t})
    response = await upload(client, owner, PNG)
    assert (response.status_code, response.json()) == (409, {"error": "drive_not_connected"})
