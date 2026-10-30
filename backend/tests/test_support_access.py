"""Support access (A43): an operator enters an office as its owner or a member,
as Suporte Unio, for an hour, audited; the account has no other way in and
stays out of the office's team, counts and analytics."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from backend.app import drop_support
from backend.identity import support
from backend.identity.models import Role
from backend.tests import test_admin, test_analytics, test_operator_actions
from backend.tests.test_office import ALINEA, NORTE
from backend.web import auth

operators = test_admin.operators  # fixtures
actions_enabled = test_operator_actions.actions_enabled
sent = test_analytics.sent
UNIO = test_admin.UNIO
pytestmark = pytest.mark.anyio


async def entry_url(client, role="owner", slug="alinea") -> str:
    headers = await test_admin.sign_in(client)
    response = await client.post(
        f"/api/admin/offices/{slug}/actions", json={"action": f"support_{role}"}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["support_url"]


def token_of(url: str) -> str:
    return url.split("#token=", 1)[1]


async def enter(client, url, host=ALINEA):
    return await client.post("/api/support-session", json={"token": token_of(url)}, headers=host)


async def office_headers(client, url) -> dict:
    entered = await enter(client, url)
    assert entered.status_code == 200, entered.text
    return ALINEA | {auth.CSRF_HEADER: entered.json()["csrf_token"]}


async def test_an_operator_enters_as_owner_for_an_hour_audited(client, actions_enabled, db_session):
    url = await entry_url(client)
    assert url.startswith("http://alinea.localhost:") and "/painel/suporte#token=" in url
    entered = await enter(client, url)
    assert entered.status_code == 200, entered.text
    me = (await client.get("/api/me", headers=ALINEA)).json()
    assert (me["name"], me["role"]) == ("Suporte Unio", "owner")
    assert me["page_tour_seen"]  # the project page's tour is the office's people's
    until = datetime.fromisoformat(me["support_until"])
    assert timedelta(minutes=59) < until - datetime.now(UTC) <= timedelta(hours=1)
    assert me["analytics"] is None
    [audited] = (
        await db_session.execute(
            text("SELECT actor, action, target_slug FROM operator_audit_events")
        )
    ).all()
    assert tuple(audited) == (test_admin.OPERATOR, "support:owner", "alinea")


async def test_an_entry_link_works_once_and_only_on_its_own_office(client, actions_enabled):
    url = await entry_url(client)
    assert (await enter(client, url, host=NORTE)).status_code == 404  # another office's
    assert (await enter(client, url)).status_code == 200
    assert (await enter(client, url)).status_code == 404  # spent


async def test_an_entry_link_expires_in_minutes(client, actions_enabled, db_session):
    url = await entry_url(client)
    await db_session.execute(
        text(
            "UPDATE password_links SET expires_at = now() - interval '1 second' "
            "WHERE kind = 'support'"
        )
    )
    assert (await enter(client, url)).status_code == 404


async def test_a_member_entry_has_a_members_powers(client, actions_enabled):
    headers = await office_headers(client, await entry_url(client, "member"))
    assert (await client.get("/api/me", headers=ALINEA)).json()["role"] == "member"
    invite = {"name": "Bia", "email": "bia@alinea.example", "role": "member"}
    refused = await client.post("/api/team/invites", json=invite, headers=headers)
    assert refused.status_code == 403  # owners only


async def test_each_role_has_one_account_however_many_entries(client, actions_enabled, db_session):
    for role in ("owner", "member", "owner"):
        assert (await enter(client, await entry_url(client, role))).status_code == 200
    accounts = (
        await db_session.execute(text("SELECT role, password_hash FROM users WHERE support"))
    ).all()
    assert sorted(accounts) == [("member", None), ("owner", None)]


async def test_a_support_session_is_never_extended(client, actions_enabled, db_session):
    await enter(client, await entry_url(client))
    ends = await db_session.scalar(text("SELECT expires_at FROM sessions"))
    await db_session.execute(text("UPDATE sessions SET last_seen_at = now() - interval '2 hours'"))
    assert (await client.get("/api/me", headers=ALINEA)).status_code == 200
    assert await db_session.scalar(text("SELECT expires_at FROM sessions")) == ends
    await db_session.execute(text("UPDATE sessions SET expires_at = now() - interval '1 second'"))
    assert (await client.get("/api/me", headers=ALINEA)).status_code == 401  # ended


async def test_suporte_unio_has_no_other_way_in(client, actions_enabled, db_session):
    await enter(client, await entry_url(client))
    client.cookies.clear()
    email = support.address(Role.OWNER)
    signed = await client.post(
        "/api/session", json={"email": email, "password": "x" * 12}, headers=ALINEA
    )
    assert signed.status_code == 401
    await client.post("/api/password-reset", json={"email": email}, headers=ALINEA)
    assert (
        await db_session.scalar(text("SELECT count(*) FROM password_links WHERE kind <> 'support'"))
        == 0
    )


async def test_suporte_unios_own_details_cant_be_changed(client, actions_enabled):
    headers = await office_headers(client, await entry_url(client))
    renamed = await client.patch("/api/me", json={"name": "Outro"}, headers=headers)
    assert (renamed.status_code, renamed.json()["error"]) == (403, "support_account")
    email = await client.post(
        "/api/me/email/change", json={"email": "x@example.com", "password": "x"}, headers=headers
    )
    assert email.status_code == 403


async def test_suporte_unio_is_not_on_the_team_or_in_the_counts(
    client, actions_enabled, db_session
):
    headers = await office_headers(client, await entry_url(client))
    team = (await client.get("/api/team", headers=headers)).json()["members"]
    assert "Suporte Unio" not in [member["name"] for member in team]
    office = (await client.get("/api/admin/offices/alinea", headers=UNIO)).json()
    assert "Suporte Unio" not in [member["name"] for member in office["team"]]
    assert office["staff"] == len(office["team"])
    assert office["last_activity_at"] is None  # the support session isn't the office's activity


async def test_a_suspended_office_cant_be_entered_nor_is_it_audited(
    client, actions_enabled, db_session
):
    headers = await test_admin.sign_in(client)
    path = "/api/admin/offices/alinea/actions"
    assert (await client.post(path, json={"action": "suspend"}, headers=headers)).status_code == 200
    refused = await client.post(path, json={"action": "support_owner"}, headers=headers)
    assert refused.status_code == 409
    actions = await db_session.scalars(text("SELECT action FROM operator_audit_events"))
    assert list(actions) == ["suspend"]


async def test_only_an_operator_can_make_an_entry_link(client, actions_enabled):
    path = "/api/admin/offices/alinea/actions"
    refused = await client.post(path, json={"action": "support_owner"}, headers=UNIO)
    assert refused.status_code in (401, 403)


async def test_a_support_sessions_events_never_reach_posthog(client, actions_enabled, sent):
    headers = await office_headers(client, await entry_url(client))
    sent.clear()
    assert (await client.post("/api/me/tour-seen", headers=headers)).status_code == 204
    tagged = [m for m in sent if m.get("event") == "page_tour_seen"]
    assert tagged and all(m["properties"][auth.SUPPORT_TAG] for m in tagged)
    assert [drop_support(m) for m in tagged] == [None] * len(tagged)
    assert drop_support({"event": "x", "properties": {"tenant": "alinea"}}) is not None


async def test_suporte_unio_is_no_pending_invite_to_send_again(client, actions_enabled):
    """Codex, PR #173: it has no password, like an invite; a link to choose one
    would turn it into a 30-day account outside the audit."""
    headers = await office_headers(client, await entry_url(client))
    me = (await client.get("/api/me", headers=ALINEA)).json()
    again = await client.post(f"/api/team/invites/{me['id']}/link", headers=headers)
    assert again.status_code == 404
    cancel = await client.delete(f"/api/team/invites/{me['id']}", headers=headers)
    assert cancel.status_code == 404


async def test_no_password_link_works_for_suporte_unio(client, actions_enabled, db_session):
    """However one came to exist, a link to choose a password never opens it."""
    from backend.identity import links
    from backend.identity.models import LinkKind, User

    await enter(client, await entry_url(client))
    user = await db_session.scalar(select(User).where(User.support))
    token = await links.create(db_session, user, LinkKind.RESET)
    client.cookies.clear()
    chosen = await client.post(
        "/api/password", json={"token": token, "password": "uma senha nova e boa"}, headers=ALINEA
    )
    assert chosen.status_code == 404
