"""The operator dashboard (A38): only on Unio's own address, only for allowlisted
Google accounts, counts and health of every office, no client content."""

import base64
import json
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from backend.commands.seed import seed
from backend.operators.google_signin import GoogleSignIn, Identity, SignInError, challenge
from backend.settings import Environment
from backend.tests.test_office import ALINEA
from backend.web import admin, attempts

pytestmark = pytest.mark.anyio

UNIO = {"host": "localhost"}  # OPERATOR_HOST's default, locally
OPERATOR = "fabio@unio.example"


@pytest.fixture
async def operators(app, db_session):
    await seed(db_session)
    app.state.settings = app.state.settings.model_copy(update={"operator_emails": OPERATOR})


async def sign_in(client, email=OPERATOR) -> dict:
    response = await client.post("/api/admin/dev-session", json={"email": email}, headers=UNIO)
    assert response.status_code == 204
    me = (await client.get("/api/admin/me", headers=UNIO)).json()
    return UNIO | {admin.CSRF_HEADER: me["csrf_token"]}


# -- where and who ---------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/api/admin/me", "/api/admin/offices", "/admin/escritorios"])
async def test_nothing_answers_on_an_offices_address(client, operators, path):
    await sign_in(client)
    response = await client.get(path, headers=ALINEA)
    assert response.status_code == 404


async def test_without_signing_in_nothing_is_shown(client, operators):
    for path in ("/api/admin/me", "/api/admin/offices", "/api/admin/offices/alinea"):
        response = await client.get(path, headers=UNIO)
        assert (response.status_code, response.json()["error"]) == (401, "not_signed_in")


async def test_only_allowlisted_emails_get_in_and_leaving_the_list_ends_access(
    app, client, operators
):
    refused = await client.post(
        "/api/admin/dev-session", json={"email": "outra@unio.example"}, headers=UNIO
    )
    assert refused.status_code == 404
    await sign_in(client, " Fabio@Unio.example ")  # tidied, as Google gives it
    assert (await client.get("/api/admin/me", headers=UNIO)).json()["email"] == OPERATOR
    app.state.settings = app.state.settings.model_copy(update={"operator_emails": ""})
    assert (await client.get("/api/admin/me", headers=UNIO)).status_code == 401


async def test_the_local_sign_in_never_works_deployed(app, client, operators):
    app.state.settings = app.state.settings.model_copy(update={"environment": Environment.STAGING})
    response = await client.post("/api/admin/dev-session", json={"email": OPERATOR}, headers=UNIO)
    assert response.status_code == 404


async def test_an_office_staff_session_is_not_an_operators(client, operators, db_session):
    from backend.identity.models import Role
    from backend.tests.test_office import sign_in_as

    await sign_in_as(client, db_session, OPERATOR, Role.OWNER)  # an owner at Alinea
    assert (await client.get("/api/admin/me", headers=UNIO)).status_code == 401


async def test_signing_out_needs_the_csrf_token_and_ends_the_session(client, operators):
    headers = await sign_in(client)
    refused = await client.post("/api/admin/signout", headers=UNIO)
    assert refused.status_code == 403
    assert (await client.post("/api/admin/signout", headers=headers)).status_code == 204
    assert (await client.get("/api/admin/me", headers=UNIO)).status_code == 401


# -- what it shows ---------------------------------------------------------------------


async def test_every_office_with_its_counts_and_no_client_content(client, operators):
    await sign_in(client)
    found = (await client.get("/api/admin/offices", headers=UNIO)).json()
    by_slug = {office["slug"]: office for office in found}
    assert {"alinea", "norte"} <= by_slug.keys()
    alinea = by_slug["alinea"]
    assert alinea["hosts"][0] == "alinea.localhost"  # the primary first
    assert alinea["projects"]["active"] >= 1 and set(alinea["projects"]) >= {
        "draft",
        "active",
        "completed",
        "archived",
    }
    assert alinea["storage"] == "folder"  # the seed's local folder
    assert alinea["team"] == []  # the team only on the office's own page
    text = json.dumps(found)
    for client_content in ("Casa Jardim", "Família Oliveira", "Croqui", "@exemplo.com"):
        assert client_content not in text


async def test_an_offices_page_adds_its_team(client, operators, db_session):
    from sqlalchemy import text

    from backend.identity import accounts
    from backend.tests.test_office import tenant_id

    t = await tenant_id(db_session, "alinea")
    await db_session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(t)})
    await accounts.create_user(db_session, email="bia@alinea.example", name="Bia")  # invited
    await sign_in(client)
    office = (await client.get("/api/admin/offices/alinea", headers=UNIO)).json()
    bia = next(m for m in office["team"] if m["email"] == "bia@alinea.example")
    assert (bia["status"], bia["role"], bia["last_seen_at"]) == ("invited", "member", None)
    assert office["pending"] >= 1
    missing = await client.get("/api/admin/offices/nenhum", headers=UNIO)
    assert missing.status_code == 404


async def test_the_page_answers_only_on_unios_address(app, client, operators, tmp_path):
    (tmp_path / "admin.html").write_text("<!doctype html><title>Admin</title>")
    (tmp_path / "client.html").write_text("<!doctype html><head><!--page-head--></head>")
    app.state.settings = app.state.settings.model_copy(update={"frontend_dist": str(tmp_path)})
    page = await client.get("/admin/offices/alinea", headers=UNIO)
    assert page.status_code == 200 and "Admin" in page.text
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    # On an office's address it is no dashboard: the project pages' answer.
    elsewhere = await client.get("/admin", headers=ALINEA)
    assert elsewhere.status_code == 404 and "Admin" not in elsewhere.text


async def test_a_project_at_admin_stays_reachable_on_its_office(
    app, client, operators, db_session, tmp_path
):
    """/admin is the dashboard only on Unio's address; an office's project may
    have that address."""
    from sqlalchemy import text

    (tmp_path / "client.html").write_text("<!doctype html><head><!--page-head--></head>")
    app.state.settings = app.state.settings.model_copy(update={"frontend_dist": str(tmp_path)})
    await db_session.execute(
        text("UPDATE project_slugs SET slug = 'admin' WHERE slug = 'casa-jardim'")
    )
    page = await client.get("/admin", headers=ALINEA)
    assert page.status_code == 200 and "Casa Jardim" in page.text


async def test_deleted_projects_are_not_counted(client, operators, db_session):
    from sqlalchemy import text

    await sign_in(client)
    before = {
        o["slug"]: o["projects"]
        for o in (await client.get("/api/admin/offices", headers=UNIO)).json()
    }["alinea"]
    await db_session.execute(
        text(
            "UPDATE projects SET deleted_at = now() WHERE id IN (SELECT ps.project_id FROM "
            "project_slugs ps JOIN tenants t ON t.id = ps.tenant_id "
            "WHERE ps.slug = 'casa-jardim' AND t.slug = 'alinea')"
        )
    )
    after = {
        o["slug"]: o["projects"]
        for o in (await client.get("/api/admin/offices", headers=UNIO)).json()
    }["alinea"]
    assert after["active"] == before["active"] - 1


# -- Google sign-in -------------------------------------------------------------------


async def start(client) -> tuple[dict, str]:
    """Start sign-in: Google's address's parameters, and the flow cookie."""
    response = await client.post("/api/admin/signin", headers=UNIO)
    assert response.status_code == 200
    query = {k: v[0] for k, v in parse_qs(urlsplit(response.json()["url"]).query).items()}
    return query, response.cookies[admin.FLOW_COOKIE]


@pytest.fixture
def google(app, monkeypatch):
    app.state.settings = app.state.settings.model_copy(
        update={"google_oauth_client_id": "client-1", "google_oauth_client_secret": "secret-1"}
    )
    answers = {}
    attempts.reset()

    async def identify(self, http, code, verifier, nonce):
        answers["got"] = (code, verifier, nonce)
        if isinstance(answers.get("identity"), Exception):
            raise answers["identity"]
        return answers.get("identity", Identity(OPERATOR, "Fabio"))

    monkeypatch.setattr(GoogleSignIn, "identify", identify)
    return answers


async def test_google_sign_in_asks_only_who_with_pkce_and_a_nonce(client, operators, google):
    query, _cookie = await start(client)
    assert query["scope"] == "openid email profile"  # nothing in Drive
    assert query["code_challenge_method"] == "S256" and query["nonce"] and query["state"]
    assert query["redirect_uri"] == "http://localhost:5173/api/auth/google/callback"


async def test_google_sign_in_returns_signed_in(client, operators, google):
    query, _cookie = await start(client)
    back = await client.get(
        "/api/auth/google/callback", params={"state": query["state"], "code": "c-1"}, headers=UNIO
    )
    assert (back.status_code, back.headers["location"]) == (302, "/admin")
    code, verifier, nonce = google["got"]
    assert code == "c-1" and challenge(verifier) == query["code_challenge"]
    assert nonce == query["nonce"]
    assert (await client.get("/api/admin/me", headers=UNIO)).json()["email"] == OPERATOR


@pytest.mark.parametrize(
    ("change", "said"),
    [
        ({"state": "forged"}, "expirado"),  # not the state this browser started
        ({"error": "access_denied"}, "cancelado"),
    ],
)
async def test_a_return_that_doesnt_match_signs_nobody_in(client, operators, google, change, said):
    query, _cookie = await start(client)
    params = {"state": query["state"], "code": "c-1"} | change
    back = await client.get("/api/auth/google/callback", params=params, headers=UNIO)
    assert back.headers["location"].startswith(f"/admin?entrar={said}&ref=")
    assert (await client.get("/api/admin/me", headers=UNIO)).status_code == 401


async def test_a_return_in_another_browser_finds_nothing_to_match(client, operators, google):
    query, _cookie = await start(client)
    client.cookies.clear()  # no flow cookie: another browser
    back = await client.get(
        "/api/auth/google/callback", params={"state": query["state"], "code": "c-1"}, headers=UNIO
    )
    assert back.headers["location"].startswith("/admin?entrar=expirado&ref=")


async def test_a_google_account_off_the_list_is_refused(client, operators, google, caplog):
    google["identity"] = Identity("intruso@gmail.com", None)
    query, _cookie = await start(client)
    back = await client.get(
        "/api/auth/google/callback", params={"state": query["state"], "code": "c-1"}, headers=UNIO
    )
    assert back.headers["location"].startswith("/admin?entrar=negado&ref=")
    assert (await client.get("/api/admin/me", headers=UNIO)).status_code == 401
    assert "intruso@gmail.com" in caplog.text


async def test_googles_failure_is_logged_and_the_page_says_only_that_it_failed(
    client, operators, google, caplog
):
    google["identity"] = SignInError("token endpoint 500: secret detail")
    query, _cookie = await start(client)
    back = await client.get(
        "/api/auth/google/callback", params={"state": query["state"], "code": "c-1"}, headers=UNIO
    )
    assert back.headers["location"].startswith("/admin?entrar=falhou&ref=")
    assert "secret detail" in caplog.text


# -- reading Google's ID token ---------------------------------------------------------


def id_token(**claims) -> str:
    body = {
        "iss": "https://accounts.google.com",
        "aud": "client-1",
        "exp": time.time() + 300,
        "nonce": "n-1",
        "email": "Fabio@Unio.example",
        "email_verified": True,
        "name": "Fabio",
    } | claims
    part = base64.urlsafe_b64encode(json.dumps(body).encode()).rstrip(b"=").decode()
    return f"header.{part}.signature"


SIGNIN = GoogleSignIn("client-1", "secret-1", "http://localhost/cb")


def test_a_good_id_token_gives_the_verified_email():
    assert SIGNIN.read(id_token(), "n-1") == Identity("fabio@unio.example", "Fabio")


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://evil.example"},
        {"aud": "another-client"},
        {"exp": time.time() - 1},
        {"nonce": "n-2"},
        {"email_verified": False},
        {"email": ""},
    ],
)
def test_an_id_token_that_isnt_for_us_now_is_refused(claims):
    with pytest.raises(SignInError):
        SIGNIN.read(id_token(**claims), "n-1")


async def test_operator_sign_in_failing_again_and_again_must_wait(client, operators, google):
    google["identity"] = SignInError("invalid_grant")
    for _ in range(attempts.LIMIT):
        query, _cookie = await start(client)
        await client.get(
            "/api/auth/google/callback", params={"state": query["state"], "code": "c"}, headers=UNIO
        )
    query, _cookie = await start(client)
    back = await client.get(
        "/api/auth/google/callback", params={"state": query["state"], "code": "c"}, headers=UNIO
    )
    assert back.headers["location"].startswith("/admin?entrar=tentativas&ref=")
