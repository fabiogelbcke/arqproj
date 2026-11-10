"""Product analytics (PostHog): what the server sends, for whom, and that a local
run or a test sends nothing unless asked to."""

import ast
from pathlib import Path

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


async def test_a_password_changed_from_minha_conta_is_recorded(client, db_session, owner, sent):
    from backend.web import attempts

    attempts.reset()
    response = await client.post(
        "/api/me/password",
        json={"current": "a good password", "password": "uma senha nova e boa"},
        headers=owner,
    )
    assert response.status_code == 200, response.text
    (event,) = events(sent, "password_set")
    assert event["distinct_id"] == await staff_id(db_session, "dona@alinea.example")


# -- every event is one of AnalyticsEvent's ----------------------------------------

ROOT = Path(__file__).resolve().parents[2]

# The functions that send an event, and which argument it is. `client.capture` is
# PostHog's own; a function of ours whose parameter is an `AnalyticsEvent` joins
# the list (shares' `_event`, which sends as staff or as a visitor).
SENDERS = {"capture": 1, "capture_visit": 2}

# Where PostHog's client is called directly instead of through `analytics.capture`,
# and why: these events carry their own distinct id, not the request's person.
DIRECT = {
    "backend/analytics.py": "the helpers themselves",
    "backend/transfers.py": "personless: the office's or today's visitor's id",
    "backend/web/maintenance.py": "per office, from Cloud Scheduler: no person",
}


def _runtime_sources() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): path.read_text("utf-8")
        for path in (ROOT / "backend").rglob("*.py")
        if not {"tests", "migrations", "commands"} & set(path.relative_to(ROOT).parts)
    }


def _is_event_type(annotation: ast.expr | None) -> bool:
    return isinstance(annotation, ast.Name) and annotation.id == "AnalyticsEvent"


def _event_params(tree: ast.Module) -> dict[str, tuple[int, str]]:
    """Our functions taking an AnalyticsEvent: name -> (position, parameter)."""
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for index, arg in enumerate(node.args.args):
                if _is_event_type(arg.annotation):
                    found[node.name] = (index, arg.arg)
    return found


def _an_event(value: ast.expr, typed: set[str]) -> bool:
    """`AnalyticsEvent.X`, a choice between two of them, or a parameter that is one."""
    if isinstance(value, ast.IfExp):
        return _an_event(value.body, typed) and _an_event(value.orelse, typed)
    if isinstance(value, ast.Attribute):
        return isinstance(value.value, ast.Name) and value.value.id == "AnalyticsEvent"
    return isinstance(value, ast.Name) and value.id in typed


def event_problems(sources: dict[str, str], direct: dict[str, str]) -> set[str]:
    trees = {name: ast.parse(source) for name, source in sources.items()}
    senders = {name: (index, "event") for name, index in SENDERS.items()}
    for tree in trees.values():
        senders |= _event_params(tree)
    problems = {f"{name}: listed, but no such file" for name in direct if name not in sources}
    for name, tree in trees.items():
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            typed = {a.arg for a in function.args.args if _is_event_type(a.annotation)}
            for call in ast.walk(function):
                if not isinstance(call, ast.Call):
                    continue
                where = f"{name}:{call.lineno}"
                if isinstance(call.func, ast.Attribute) and call.func.attr == "capture":
                    if name not in direct:
                        problems.add(f"{where}: PostHog's client called directly")
                    index, keyword = 0, "event"
                elif isinstance(call.func, ast.Name) and call.func.id in senders:
                    index, keyword = senders[call.func.id]
                else:
                    continue
                given = [k.value for k in call.keywords if k.arg == keyword]
                event = call.args[index] if len(call.args) > index else (given or [None])[0]
                if event is None or not _an_event(event, typed):
                    problems.add(f"{where}: an event that is not an AnalyticsEvent")
    return problems


def test_every_event_the_server_sends_is_an_analytics_event():
    """PostHog's dashboards find events by name: one typed from memory in a new
    route ("stage_complete" for "stage_completion_changed") would go unseen."""
    assert event_problems(_runtime_sources(), DIRECT) == set()


def test_the_event_rule_catches_a_name_typed_in_place():
    """Self-test: a string event, one passed through an untyped parameter, a direct
    client call and a stale allowlist entry are each caught."""
    source = (
        "def a(request):\n"
        "    capture(request, 'stage_moved')\n"
        "def b(request, event: str):\n"
        "    capture(request, event)\n"
        "def c(request, event: AnalyticsEvent):\n"
        "    capture_visit(request, None, event)\n"
        "def d(request):\n"
        "    c(request, 'share_page_viewed')\n"
        "    c(request, AnalyticsEvent.SHARE_PAGE_VIEWED)\n"
        "def e(client):\n"
        "    client.capture(AnalyticsEvent.FILE_TRANSFER)\n"
    )
    assert event_problems({"x.py": source}, {"gone.py": "a file removed since"}) == {
        "gone.py: listed, but no such file",
        "x.py:2: an event that is not an AnalyticsEvent",
        "x.py:4: an event that is not an AnalyticsEvent",
        "x.py:8: an event that is not an AnalyticsEvent",
        "x.py:11: PostHog's client called directly",
    }
