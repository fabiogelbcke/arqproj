"""Connecting an office's Google Drive, against an imitation of Google."""

from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest
from sqlalchemy import select, text

from backend.commands.seed import seed
from backend.identity import accounts
from backend.identity.models import Role
from backend.security import keys
from backend.storage.google import GoogleDriveStorage
from backend.storage.models import StorageConnection, StorageKind, WriterStatus
from backend.tenancy.models import Tenant
from backend.web import auth, drive

pytestmark = pytest.mark.anyio

ALINEA = {"host": "alinea.localhost"}
SHARED = {"host": "127.0.0.1:5173"}  # the return address registered with Google
READER = "portal-reader@example.iam.gserviceaccount.com"
REFRESH = "1//refresh-token-from-google"


class FakeGoogle:
    """Google's token endpoint and the Drive calls the connection makes."""

    def __init__(self):
        self.calls: list[str] = []
        self.share_fails = False
        self.share_drops_connection = False
        self.writer_check_fails = False
        self.writer_reaches = set()  # folders the office's grant can still open
        self.quota = {"limit": str(15 * 2**30), "usage": str(12 * 2**30)}  # 15 GB, 12 used
        self.about_fails = False

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        path, method = request.url.path, request.method
        self.calls.append(f"{method} {request.url.host}{path}")
        if path == "/token":
            form = parse_qs(request.content.decode())
            if form.get("code") == ["bad"]:
                return httpx2.Response(400, json={"error": "invalid_grant"})
            return httpx2.Response(200, json={"access_token": "writer", "refresh_token": REFRESH})
        if path == "/revoke":
            return httpx2.Response(200)
        auth_header = request.headers.get("Authorization")
        if path == "/drive/v3/about":
            if "storageQuota" in request.url.params.get("fields", ""):
                if self.about_fails:
                    return httpx2.Response(503, json={"error": {"message": "backendError"}})
                return httpx2.Response(200, json={"storageQuota": self.quota})
            return httpx2.Response(200, json={"user": {"emailAddress": "escritorio@gmail.com"}})
        if path == "/drive/v3/files" and method == "POST":
            self.writer_reaches.add("root1")
            return httpx2.Response(200, json={"id": "root1"})
        if path.endswith("/permissions"):
            if self.share_drops_connection:
                raise httpx2.ConnectError("connection reset")
            if self.share_fails:
                return httpx2.Response(403, json={"error": {"message": "appNotAuthorizedToChild"}})
            return httpx2.Response(200, json={"id": "perm"})
        if method == "PATCH":
            return httpx2.Response(200, json={})
        if path.startswith("/drive/v3/files/") and auth_header == "Bearer writer":
            if self.writer_check_fails:
                return httpx2.Response(503, json={})
            folder = path.rsplit("/", 1)[1]
            if folder in self.writer_reaches:
                return httpx2.Response(200, json={"id": folder})
            return httpx2.Response(404, json={})
        # The reader identity (the server's own token).
        if path.startswith("/drive/v3/files/"):
            return httpx2.Response(
                200,
                json={
                    "id": "root1",
                    "name": "Portal Clientes",
                    "mimeType": "application/vnd.google-apps.folder",
                    "modifiedTime": "2026-10-15T12:00:00Z",
                },
            )
        if path == "/drive/v3/files":
            return httpx2.Response(200, json={"files": []})
        return httpx2.Response(500, json={"unexpected": path})


@pytest.fixture
def google(app):
    fake = FakeGoogle()
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(fake))

    async def server_token():
        return "reader"

    app.state.http = http
    app.state.google = GoogleDriveStorage(server_token, http)
    app.state.settings = app.state.settings.model_copy(
        update={
            "google_oauth_client_id": "client-id",
            "google_oauth_client_secret": "client-secret",
            "drive_reader_identity": READER,
        }
    )
    return fake


async def add_staff(db, email, role):
    tenant_id = await db.scalar(select(Tenant.id).where(Tenant.slug == "alinea"))
    await db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})
    # The seed gives local offices folder storage; these tests start unconnected.
    await db.execute(text("DELETE FROM storage_connections WHERE tenant_id = :t"), {"t": tenant_id})
    await accounts.create_user(db, email=email, name="Ana", password="a good password", role=role)


@pytest.fixture
async def owner(client, db_session):
    await seed(db_session)
    await add_staff(db_session, "dona@alinea.example", Role.OWNER)
    response = await client.post(
        "/api/session",
        json={"email": "dona@alinea.example", "password": "a good password"},
        headers=ALINEA,
    )
    return {**ALINEA, auth.CSRF_HEADER: response.json()["csrf_token"]}


async def start(client, headers):
    response = await client.post("/api/drive/connect", headers=headers)
    assert response.status_code == 200, response.text
    query = parse_qs(urlsplit(response.json()["url"]).query)
    assert query["scope"] == ["https://www.googleapis.com/auth/drive.file"]
    assert query["redirect_uri"] == ["http://127.0.0.1:5173/api/drive/callback"]
    return query["state"][0]


async def come_back(client, state, code="good-code"):
    """Google's return to the shared address, then the forward to the office."""
    first = await client.get(f"/api/drive/callback?code={code}&state={state}", headers=SHARED)
    assert first.status_code == 302
    target = urlsplit(first.headers["location"])
    assert target.netloc == "alinea.localhost"
    return await client.get(f"{target.path}?{target.query}", headers=ALINEA)


async def connection(db):
    """Alinea's connection (this test session sees every office's rows)."""
    alinea = select(Tenant.id).where(Tenant.slug == "alinea").scalar_subquery()
    return await db.scalar(select(StorageConnection).where(StorageConnection.tenant_id == alinea))


async def test_connecting_creates_a_shared_folder_and_keeps_the_grant_encrypted(
    client, db_session, owner, google
):
    state = await start(client, owner)
    done = await come_back(client, state)
    assert done.headers["location"] == "/painel/configuracoes/drive?resultado=conectado"

    saved = await connection(db_session)
    assert (saved.kind, saved.root_id, saved.writer_status, saved.account_email) == (
        StorageKind.GOOGLE,
        "root1",
        WriterStatus.CONNECTED,
        "escritorio@gmail.com",
    )
    assert saved.reader_status.value == "ok"
    assert REFRESH not in saved.writer_token  # stored encrypted
    secret = client._transport.app.state.settings.app_secret
    assert keys.decrypt(secret, drive.TOKEN_PURPOSE, saved.writer_token) == REFRESH
    # Shared with the reader right after creating it, before anything else.
    drive_calls = [c for c in google.calls if "/drive/v3/" in c]
    assert drive_calls[0].endswith("/drive/v3/files") and drive_calls[1].endswith("/permissions")

    status = (await client.get("/api/drive", headers=ALINEA)).json()
    assert status["writer_status"] == "connected" and status["can_manage"]
    assert status["folder_url"].endswith("/root1")


async def test_a_folder_that_cannot_be_shared_is_trashed_and_not_used(
    client, db_session, owner, google
):
    google.share_fails = True
    done = await come_back(client, await start(client, owner))
    assert "erro=drive_share_failed" in done.headers["location"]
    assert any(c.startswith("PATCH") for c in google.calls)  # the new folder went to the trash
    assert await connection(db_session) is None


async def test_a_network_failure_while_sharing_is_handled_the_same_way(
    client, db_session, owner, google
):
    google.share_drops_connection = True
    done = await come_back(client, await start(client, owner))
    assert "erro=drive_share_failed" in done.headers["location"]
    assert any(c.startswith("PATCH") for c in google.calls)  # no orphan folder left
    assert await connection(db_session) is None


async def test_a_failure_carries_the_support_code_to_the_screen(client, owner, google):
    google.share_fails = True
    done = await come_back(client, await start(client, owner))
    reference = parse_qs(urlsplit(done.headers["location"]).query)["ref"][0]
    assert reference == done.headers["x-request-id"]  # the ID the log line carries


async def test_after_disconnecting_the_app_reads_nothing_either(
    app, client, db_session, owner, google
):
    """Section 9: disconnecting stops both paths; the folder stays for a reconnect."""
    from backend.storage.base import StorageError
    from backend.storage.connections import storage_for

    await come_back(client, await start(client, owner))
    saved = await connection(db_session)
    assert storage_for(saved, app.state.settings, app.state.google)  # reads while connected
    await client.delete("/api/drive", headers=owner)
    await db_session.refresh(saved)
    with pytest.raises(StorageError):
        storage_for(saved, app.state.settings, app.state.google)
    assert (await client.get("/api/onboarding", headers=ALINEA)).json()[
        "storage_connected"
    ] is False


async def test_a_refused_sign_in_code_connects_nothing(client, db_session, owner, google):
    done = await come_back(client, await start(client, owner), code="bad")
    assert "erro=drive_connect_failed" in done.headers["location"]
    assert await connection(db_session) is None


async def test_cancelling_at_google_says_so(client, owner, google):
    state = await start(client, owner)
    first = await client.get(
        f"/api/drive/callback?error=access_denied&state={state}", headers=SHARED
    )
    target = urlsplit(first.headers["location"])
    done = await client.get(f"{target.path}?{target.query}", headers=ALINEA)
    assert "erro=drive_denied" in done.headers["location"]


async def test_a_tampered_return_goes_nowhere(client, owner, google):
    state = await start(client, owner)
    forged = state[:-3] + ("AAA" if not state.endswith("AAA") else "BBB")
    shared = await client.get(f"/api/drive/callback?code=x&state={forged}", headers=SHARED)
    assert shared.status_code == 404
    office = await client.get(f"/api/drive/callback?code=x&state={forged}", headers=ALINEA)
    assert "erro=drive_link_invalid" in office.headers["location"]


async def test_the_shared_address_only_forwards_to_the_office_that_started(
    app, client, owner, google
):
    """A validly signed note naming an address not registered to that office."""
    payload = {
        "origin": "http://evil.example",
        "tenant": "00000000-0000-0000-0000-000000000000",
        "nonce": "n",
    }
    state = keys.sign(app.state.settings.app_secret, drive.STATE_PURPOSE, payload, 60)
    response = await client.get(f"/api/drive/callback?code=x&state={state}", headers=SHARED)
    assert response.status_code == 404


async def test_a_return_without_the_starting_browsers_cookie_is_refused(
    client, db_session, owner, google
):
    state = await start(client, owner)
    client.cookies.delete(drive.NONCE_COOKIE)
    first = await client.get(f"/api/drive/callback?code=good&state={state}", headers=SHARED)
    target = urlsplit(first.headers["location"])
    done = await client.get(f"{target.path}?{target.query}", headers=ALINEA)
    assert "erro=drive_link_invalid" in done.headers["location"]
    assert await connection(db_session) is None


async def test_members_see_the_connection_but_cannot_change_it(client, db_session, owner, google):
    await add_staff(db_session, "membro@alinea.example", Role.MEMBER)
    client.cookies.clear()
    signed = await client.post(
        "/api/session",
        json={"email": "membro@alinea.example", "password": "a good password"},
        headers=ALINEA,
    )
    member = {**ALINEA, auth.CSRF_HEADER: signed.json()["csrf_token"]}
    assert (await client.get("/api/drive", headers=ALINEA)).json()["can_manage"] is False
    for call in (
        client.post("/api/drive/connect", headers=member),
        client.delete("/api/drive", headers=member),
    ):
        response = await call
        assert (response.status_code, response.json()) == (403, {"error": "owner_only"})


async def test_disconnecting_forgets_the_grant_and_keeps_the_folder(
    client, db_session, owner, google
):
    await come_back(client, await start(client, owner))
    response = await client.delete("/api/drive", headers=owner)
    assert response.status_code == 204
    saved = await connection(db_session)
    await db_session.refresh(saved)
    assert (saved.writer_token, saved.writer_status, saved.root_id) == (
        None,
        WriterStatus.NONE,
        "root1",
    )
    assert any(c.endswith("/revoke") for c in google.calls)


async def test_reconnecting_keeps_the_same_folder(client, db_session, owner, google):
    await come_back(client, await start(client, owner))
    await client.delete("/api/drive", headers=owner)
    created = sum(c == "POST www.googleapis.com/drive/v3/files" for c in google.calls)
    await come_back(client, await start(client, owner))
    assert sum(c == "POST www.googleapis.com/drive/v3/files" for c in google.calls) == created
    assert (await connection(db_session)).root_id == "root1"


@pytest.mark.parametrize(
    ("google_says", "error"),
    [("other_account", "drive_other_account"), ("unavailable", "drive_connect_failed")],
)
async def test_reconnecting_never_replaces_the_offices_folder(
    client, db_session, owner, google, google_says, error
):
    """Its projects' files are in it: another account or a passing error changes
    nothing (plan section 9)."""
    await come_back(client, await start(client, owner))
    await client.delete("/api/drive", headers=owner)
    if google_says == "other_account":
        google.writer_reaches.clear()  # this grant cannot see the folder
    else:
        google.writer_check_fails = True
    created = sum(c == "POST www.googleapis.com/drive/v3/files" for c in google.calls)
    done = await come_back(client, await start(client, owner))
    assert f"erro={error}" in done.headers["location"]
    assert sum(c == "POST www.googleapis.com/drive/v3/files" for c in google.calls) == created
    saved = await connection(db_session)
    await db_session.refresh(saved)
    assert (saved.root_id, saved.writer_status) == ("root1", WriterStatus.NONE)


async def test_setup_is_not_done_while_the_reader_cannot_read(client, db_session, owner, google):
    await come_back(client, await start(client, owner))
    saved = await connection(db_session)
    await db_session.execute(
        text("UPDATE storage_connections SET reader_status = 'no_access' WHERE id = :i"),
        {"i": saved.id},
    )
    steps = (await client.get("/api/onboarding", headers=ALINEA)).json()
    assert steps["storage_connected"] is False


async def test_without_a_google_app_this_deployment_says_so(app, client, owner):
    app.state.settings = app.state.settings.model_copy(update={"google_oauth_client_id": None})
    response = await client.post("/api/drive/connect", headers=owner)
    assert (response.status_code, response.json()) == (503, {"error": "drive_not_configured"})


async def test_first_steps_follow_the_real_state(client, db_session, owner, google):
    before = (await client.get("/api/onboarding", headers=ALINEA)).json()
    assert before == {
        "storage_connected": False,
        "office_details": False,
        "has_project": True,  # the seed's projects
    }
    await come_back(client, await start(client, owner))
    after = (await client.get("/api/onboarding", headers=ALINEA)).json()
    assert after["storage_connected"] is True


async def test_the_accounts_space_is_asked_of_google(client, owner, google):
    await come_back(client, await start(client, owner))
    space = (await client.get("/api/drive/space", headers=ALINEA)).json()
    assert space == {"used": 12 * 2**30, "total": 15 * 2**30}


async def test_pooled_workspace_storage_has_no_total(client, owner, google):
    await come_back(client, await start(client, owner))
    google.quota = {"usage": "5000"}  # Google sets no limit
    assert (await client.get("/api/drive/space", headers=ALINEA)).json() == {
        "used": 5000,
        "total": None,
    }


async def test_space_unknown_says_try_later_and_logs_why(client, owner, google, caplog):
    await come_back(client, await start(client, owner))
    google.about_fails = True
    response = await client.get("/api/drive/space", headers=ALINEA)
    assert (response.status_code, response.json()["error"]) == (503, "drive_connect_failed")
    assert "backendError" in caplog.text and "tenant=alinea" in caplog.text


async def test_no_space_to_show_without_a_connection(client, owner, google):
    response = await client.get("/api/drive/space", headers=ALINEA)
    assert (response.status_code, response.json()["error"]) == (409, "drive_not_connected")
