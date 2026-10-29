"""Who works on each project (A41), behind a feature switched on per office (A40)."""

import uuid

import pytest
from sqlalchemy import text

from backend.identity import accounts
from backend.identity.models import Role
from backend.tenancy.models import Feature
from backend.tenancy.resolve import known_features
from backend.tests import test_admin, test_office, test_operator_actions
from backend.tests.test_office import ALINEA, NORTE, sign_in_as
from backend.tests.test_project_settings import change, project

owner = test_office.owner  # fixtures
operators = test_admin.operators
actions_enabled = test_operator_actions.actions_enabled

pytestmark = pytest.mark.anyio


async def switch_on(db, slug="alinea"):
    await db.execute(
        text("UPDATE tenants SET features = '{project_members}' WHERE slug = :s"), {"s": slug}
    )


async def account(db, email, name, slug="alinea"):
    """Another account of the office (or of `slug`'s), not signed in."""
    tenant = await test_office.tenant_id(db, slug)
    await db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
    user = await accounts.create_user(
        db, email=email, name=name, password="a good password", role=Role.MEMBER
    )
    alinea = await test_office.tenant_id(db, "alinea")
    await db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(alinea)})
    return str(user.id)


async def me(client):
    return (await client.get("/api/me", headers=ALINEA)).json()


async def page(client, slug="casa-jardim"):
    return (await client.get(f"/api/pages/{slug}", headers=ALINEA)).json()


# -- switched off: as before -----------------------------------------------------------


async def test_off_nothing_changes_for_the_office(client, owner):
    assert (await me(client))["features"] == []
    found = await project(client)
    assert found["members"] == []
    refused = await change(client, owner, found, members=[(await me(client))["id"]])
    assert (refused.status_code, refused.json()["error"]) == (409, "feature_off")
    # The typed "Responsável" is still offered and shown.
    types = (await client.get("/api/detail-types", headers=ALINEA)).json()
    assert "responsible" in {t["key"] for t in types}
    shown = await page(client)
    assert "responsible" in {d["key"] for d in shown["details"]}
    assert shown["team"] == []


async def test_members_saved_before_switching_off_are_not_shown(client, db_session, owner):
    await switch_on(db_session)
    found = await project(client)
    saved = await change(client, owner, found, members=[(await me(client))["id"]])
    assert saved.status_code == 200, saved.text
    await db_session.execute(text("UPDATE tenants SET features = '{}'"))
    assert (await project(client))["members"] == []
    assert (await page(client))["team"] == []


# -- switched on -----------------------------------------------------------------------


async def test_staff_assign_and_unassign_people_from_the_projeto_dialog(client, db_session, owner):
    await switch_on(db_session)
    mine = (await me(client))["id"]
    pedro = await account(db_session, "pedro@alinea.example", "Pedro Lima")
    found = await project(client)
    saved = await change(client, owner, found, members=[pedro, mine, pedro])
    assert saved.status_code == 200, saved.text
    # By name, each once.
    assert saved.json()["members"] == [
        {"id": mine, "name": "Ana"},
        {"id": pedro, "name": "Pedro Lima"},
    ]
    assert saved.json()["row_version"] == found["row_version"] + 1
    assert (await project(client))["members"] == saved.json()["members"]
    fewer = await change(client, owner, saved.json(), members=[pedro])
    assert [m["name"] for m in fewer.json()["members"]] == ["Pedro Lima"]
    # The same list again changes nothing, so a second dialog isn't refused for it.
    same = await change(client, owner, fewer.json(), members=[pedro])
    assert same.json()["row_version"] == fewer.json()["row_version"]


async def test_only_the_offices_own_staff_can_be_assigned(client, db_session, owner):
    await switch_on(db_session)
    found = await project(client)
    other_office = await account(db_session, "nora@norte.example", "Nora", slug="norte")
    for someone in (other_office, str(uuid.uuid4())):
        refused = await change(client, owner, found, members=[someone])
        assert (refused.status_code, refused.json()["error"]) == (422, "unknown_member")
    assert (await project(client))["members"] == []


async def test_a_removed_account_leaves_its_projects(client, db_session, owner):
    await switch_on(db_session)
    pedro = await account(db_session, "pedro@alinea.example", "Pedro Lima")
    found = await project(client)
    assert (await change(client, owner, found, members=[pedro])).status_code == 200
    await db_session.execute(text("DELETE FROM users WHERE id = :u"), {"u": pedro})
    assert (await project(client))["members"] == []


async def test_the_client_page_names_the_members_instead_of_the_typed_detail(
    client, db_session, owner
):
    await switch_on(db_session)
    before = await page(client)
    assert before["team"] == []
    # Casa Jardim's typed "Responsável" (from the seed) is no longer shown or offered.
    assert "responsible" not in {d["key"] for d in before["details"]}
    types = (await client.get("/api/detail-types", headers=ALINEA)).json()
    assert "responsible" not in {t["key"] for t in types}
    pedro = await account(db_session, "pedro@alinea.example", "Pedro Lima")
    await change(client, owner, await project(client), members=[pedro, (await me(client))["id"]])
    assert (await page(client))["team"] == ["Ana", "Pedro Lima"]


async def test_on_the_typed_responsavel_cant_be_saved(client, db_session, owner):
    await switch_on(db_session)
    shown = await page(client)
    response = await client.patch(
        f"/api/projects/{shown['staff']['project_id']}/content",
        json={
            "row_version": shown["staff"]["row_version"],
            "details": [{"key": "responsible", "value": "Arq. Marina"}],
        },
        headers=owner,
    )
    assert (response.status_code, response.json()["error"]) == (422, "invalid_detail")


async def test_one_office_switched_on_leaves_the_others_off(client, db_session, owner):
    await switch_on(db_session)
    assert (await me(client))["features"] == ["project_members"]
    await sign_in_as(client, db_session, "dona@norte.example", Role.OWNER, NORTE, "norte")
    assert (await client.get("/api/me", headers=NORTE)).json()["features"] == []


async def test_me_says_who_is_signed_in(client, db_session, owner):
    stored = await db_session.scalar(
        text("SELECT id FROM users WHERE email = 'dona@alinea.example'")
    )
    assert (await me(client))["id"] == str(stored)


def test_a_feature_the_code_no_longer_knows_is_ignored():
    assert known_features(["project_members", "gone_long_ago"]) == {Feature.PROJECT_MEMBERS}
    assert known_features(None) == frozenset()


# -- switching from the operator dashboard ---------------------------------------------


async def test_the_operator_switches_a_feature_per_office_audited(
    client, db_session, owner, actions_enabled
):
    headers = await test_admin.sign_in(client)
    path = "/api/admin/offices/alinea/actions"
    office = (await client.get("/api/admin/offices/alinea", headers=test_admin.UNIO)).json()
    assert (office["features"], office["all_features"]) == ([], ["project_members"])
    on = await client.post(
        path, json={"action": "feature_on", "feature": "project_members"}, headers=headers
    )
    assert on.status_code == 200, on.text
    assert (await me(client))["features"] == ["project_members"]
    office = (await client.get("/api/admin/offices/alinea", headers=test_admin.UNIO)).json()
    assert office["features"] == ["project_members"]
    # Twice is still once.
    await client.post(
        path, json={"action": "feature_on", "feature": "project_members"}, headers=headers
    )
    stored = await db_session.scalar(text("SELECT features FROM tenants WHERE slug = 'alinea'"))
    assert stored == ["project_members"]
    off = await client.post(
        path, json={"action": "feature_off", "feature": "project_members"}, headers=headers
    )
    assert off.status_code == 200
    assert (await me(client))["features"] == []
    assert (
        await db_session.scalar(text("SELECT features FROM tenants WHERE slug = 'norte'"))
    ) == []
    events = (
        await db_session.scalars(
            text(
                "SELECT action FROM operator_audit_events "
                "WHERE target_slug = 'alinea' ORDER BY created_at"
            )
        )
    ).all()
    assert events == [
        "feature_on:project_members",
        "feature_on:project_members",
        "feature_off:project_members",
    ]


async def test_a_switch_names_a_feature_the_code_knows(client, owner, actions_enabled):
    headers = await test_admin.sign_in(client)
    path = "/api/admin/offices/alinea/actions"
    missing = await client.post(path, json={"action": "feature_on"}, headers=headers)
    assert missing.status_code == 409
    unknown = await client.post(
        path, json={"action": "feature_on", "feature": "no_such_feature"}, headers=headers
    )
    assert unknown.status_code == 422


async def test_offices_cant_switch_their_own_features(app, owner):
    """Only the operator role may change `features`: the app's role can't, even
    through a bug in a route."""
    from sqlalchemy.exc import ProgrammingError

    async with app.state.sessionmaker() as db:
        with pytest.raises(ProgrammingError):
            await db.execute(text("UPDATE tenants SET features = '{project_members}'"))


async def test_deleting_an_office_removes_its_project_members(
    client, db_session, owner, actions_enabled
):
    await switch_on(db_session)
    found = await project(client)
    assert (
        await change(client, owner, found, members=[(await me(client))["id"]])
    ).status_code == 200
    headers = await test_admin.sign_in(client)
    path = "/api/admin/offices/alinea/actions"
    name = await db_session.scalar(text("SELECT name FROM tenants WHERE slug = 'alinea'"))
    assert (await client.post(path, json={"action": "suspend"}, headers=headers)).status_code == 200
    deleted = await client.post(
        path, json={"action": "delete", "confirmation": name}, headers=headers
    )
    assert deleted.status_code == 200, deleted.text
    assert await db_session.scalar(text("SELECT count(*) FROM project_members")) == 0
