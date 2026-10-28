"""Product analytics (PostHog): what the server sends, for whom, and that a local
run or a test sends nothing unless asked to."""

import pytest
from posthog import Posthog
from sqlalchemy import text

from backend.analytics import device_kind, visitor_id
from backend.identity.models import Role
from backend.settings import Settings
from backend.tests import test_office, test_page_access, test_shares
from backend.tests.test_office import ALINEA, sign_in_as, tenant_id
from backend.tests.test_page_access import PROTECTED, SEED_PASSWORD, Roles, unlock
from backend.tests.test_shares import made, shared
from backend.tests.test_transfers import PHONE, fake_request
from backend.web import attempts, subscribe

owner = test_office.owner  # fixtures
files = test_shares.files
fresh_attempts = test_page_access.fresh_attempts

pytestmark = pytest.mark.anyio


@pytest.fixture
def sent(app):
    """A real PostHog client whose messages are kept here instead of sent."""
    messages: list[dict] = []
    client = Posthog("phc_test", host="http://posthog.invalid")
    client._enqueue = lambda msg, *args, **kwargs: messages.append(msg)  # noqa: SLF001
    app.state.posthog = client
    yield messages
    client.disabled = True  # nothing left to send to the invalid host
    client.shutdown()


async def staff_id(db, email) -> str:
    return str(await db.scalar(text("SELECT id FROM users WHERE email = :e"), {"e": email}))


def events(messages: list[dict], name: str) -> list[dict]:
    return [m for m in messages if m.get("event") == name]


def test_a_local_run_never_reads_the_old_apps_env_file(tmp_path, monkeypatch):
    """The `.env` at the repository root is the old app's, with a real PostHog
    token: reading it would send every local run's and test's clicks to PostHog."""
    (tmp_path / ".env").write_text(
        "POSTHOG_PROJECT_TOKEN=phc_real\nPOSTHOG_HOST=https://us.i.posthog.com\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("POSTHOG_PROJECT_TOKEN", raising=False)
    monkeypatch.delenv("POSTHOG_HOST", raising=False)
    assert Settings().posthog_project_token is None


async def test_signing_in_sends_the_id_role_and_office_never_the_email_or_name(
    app, client, db_session, owner, sent
):
    sent.clear()  # the owner fixture's own sign-in
    await sign_in_as(client, db_session, "ana@alinea.example", Role.MEMBER)
    office = await tenant_id(db_session, "alinea")
    user = await staff_id(db_session, "ana@alinea.example")
    [signed_in] = events(sent, "user_signed_in")
    assert signed_in["distinct_id"] == user
    assert signed_in["properties"]["tenant"] == "alinea"
    assert signed_in["properties"]["$groups"] == {"tenant": str(office)}
    [person] = events(sent, "$set")
    assert person["$set"]["role"] == "member"
    assert not {"email", "name"} & set(person["$set"])
    [group] = events(sent, "$groupidentify")
    assert group["properties"]["$group_key"] == str(office)
    everything = repr(sent)
    assert "ana@alinea.example" not in everything and "'Ana'" not in everything


async def test_a_staff_members_actions_are_theirs_and_a_clients_are_nobodys(
    app,
    client,
    db_session,
    owner,
    files,
    sent,
):
    staff = await staff_id(db_session, "dona@alinea.example")
    await made(client, ["Planta.pdf"], headers=owner)
    roles = Roles(client)
    roles.visitor()
    await made(client, ["Planta.pdf"])
    by_staff, by_client = events(sent, "share_link_created")
    assert by_staff["distinct_id"] == staff
    assert by_client["properties"]["$process_person_profile"] is False  # personless
    assert by_client["distinct_id"].startswith("visitor:")  # today's anonymous visitor
    assert by_client["properties"]["viewer"] == "visitor"  # not counted as staff use
    assert by_client["properties"]["tenant"] == "alinea"  # still counted for the office
    assert "viewer" not in by_staff["properties"]


async def test_without_posthog_configured_nothing_is_sent_and_pages_work(app, client, owner):
    assert getattr(app.state, "posthog", None) is None
    assert (await client.get("/api/pages/casa-jardim", headers=ALINEA)).status_code == 200


async def test_staff_get_the_browsers_key_only_where_the_server_has_one(app, client, owner):
    """One image serves staging and production: the browser's PostHog key comes
    from the server at run time, and only for signed-in staff."""
    me = await client.get("/api/me", headers=ALINEA)
    assert me.json()["analytics"] is None  # no key here: the browser stays off
    app.state.settings = app.state.settings.model_copy(
        update={"posthog_project_token": "phc_test", "posthog_host": "https://us.i.posthog.com"}
    )
    analytics = (await client.get("/api/me", headers=ALINEA)).json()["analytics"]
    assert (analytics["token"], analytics["host"]) == ("phc_test", "https://us.i.posthog.com")
    assert set(analytics) == {"token", "host", "user_id", "tenant_id"}  # no email or name


async def test_a_server_error_reaches_posthog_with_its_person_and_office(
    app, client, db_session, owner, sent, monkeypatch
):
    """Before the request-ID layer turns it into the page's "Erro interno" answer."""

    async def broken(*args, **kwargs):
        raise RuntimeError("something broke")

    monkeypatch.setattr("backend.web.pages._page", broken)
    response = await client.get("/api/pages/casa-jardim", headers=ALINEA)
    assert response.status_code == 500  # the support code's answer, as before
    [error] = events(sent, "$exception")
    assert error["distinct_id"] == await staff_id(db_session, "dona@alinea.example")
    assert error["properties"]["tenant"] == "alinea"
    assert "something broke" in repr(error["properties"]["$exception_list"])


# -- visitors: counted, never identified (A39, 28 Oct 2026) -----------------------------


def personless(event: dict) -> None:
    """A visitor's event: today's anonymous id, no person, still the office's."""
    assert event["distinct_id"].startswith("visitor:")
    assert event["properties"]["$process_person_profile"] is False
    assert event["properties"]["tenant"] == "alinea"


def test_a_visitors_id_changes_every_day_and_names_no_one():
    from datetime import UTC, datetime, timedelta

    today = datetime(2026, 10, 28, 15, tzinfo=UTC)
    request = fake_request(None)
    first = visitor_id(request, today)
    assert visitor_id(request, today + timedelta(hours=8)) == first  # the same day
    assert visitor_id(request, today + timedelta(days=1)) != first  # not followed past it
    assert visitor_id(fake_request(None, user_agent="Firefox"), today) != first  # another browser
    other_app = fake_request(None)
    other_app.app.state.settings.app_secret = "t" * 32
    assert visitor_id(other_app, today) != first  # keyed: not recomputable without the secret
    assert "203.0.113.5" not in first


@pytest.mark.parametrize(
    ("user_agent", "kind"),
    [
        (PHONE, "phone"),
        ("Mozilla/5.0 (Linux; Android 14; Pixel 8) Chrome/130.0 Mobile Safari/537.36", "phone"),
        ("Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X) Mobile/15E148 Safari/604.1", "tablet"),
        ("Mozilla/5.0 (Linux; Android 14; SM-X710) Chrome/130.0 Safari/537.36", "tablet"),
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) Safari/605.1.15", "computer"),
        ("", "computer"),
    ],
)
def test_the_device_kind_comes_from_the_browser(user_agent, kind):
    assert device_kind(user_agent) == kind


async def test_unlocking_a_page_counts_tries_never_the_password(
    client, owner, sent, fresh_attempts
):
    Roles(client).visitor()
    await unlock(client, "senha-errada")
    await unlock(client, SEED_PASSWORD)
    wrong, right = events(sent, "page_unlock_tried")
    personless(wrong)
    assert (wrong["properties"]["unlocked"], right["properties"]["unlocked"]) == (False, True)
    assert wrong["distinct_id"] == right["distinct_id"]  # one visitor, the same day
    assert SEED_PASSWORD not in repr(sent) and "senha-errada" not in repr(sent)
    assert PROTECTED not in repr(wrong)  # which project is the office's business


async def test_a_client_subscribing_is_counted_without_their_address(
    client, owner, sent, monkeypatch
):
    class Quiet:
        async def send(self, email):
            return "id"

    monkeypatch.setattr(subscribe, "sender_for", lambda settings, http: Quiet())
    attempts.reset()
    Roles(client).visitor()
    response = await client.post(
        "/api/pages/casa-jardim/subscribe", json={"email": "cliente@example.com"}, headers=ALINEA
    )
    assert response.status_code == 204, response.text
    [subscribed] = events(sent, "client_email_subscribed")
    personless(subscribed)
    assert "cliente@example.com" not in repr(sent)


async def test_a_share_page_opened_is_counted_as_a_visit(client, owner, files, sent):
    link = await made(client, ["Planta.pdf"], headers=owner)
    Roles(client).visitor()
    assert (await shared(client, link)).status_code == 200
    [viewed] = events(sent, "share_page_viewed")
    personless(viewed)
    assert viewed["properties"]["file_count"] == 1
    assert "Planta" not in repr(viewed)


async def test_visitors_browsers_get_a_cookieless_setup_only_where_there_is_a_key(
    app, client, owner
):
    assert (await client.get("/api/tenant", headers=ALINEA)).json()["analytics"] is None
    app.state.settings = app.state.settings.model_copy(
        update={"posthog_project_token": "phc_test", "posthog_host": "https://us.i.posthog.com"}
    )
    office = (await client.get("/api/tenant", headers=ALINEA)).json()
    assert office["slug"] == "alinea"
    assert set(office["analytics"]) == {"token", "host", "tenant_id"}  # no person


async def test_staff_actions_on_the_page_are_the_staff_members(client, db_session, owner, sent):
    sent.clear()
    assert (await client.post("/api/me/tour-seen", headers=owner)).status_code == 204
    [seen] = events(sent, "page_tour_seen")
    assert seen["distinct_id"] == await staff_id(db_session, "dona@alinea.example")
    assert seen["properties"]["tenant"] == "alinea"
