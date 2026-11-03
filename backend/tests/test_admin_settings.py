"""The operator dashboard's types and stages (A44): one list for every office,
edited live, hidden rather than deleted, every change audited."""

import pytest
from sqlalchemy import text

from backend.tests import test_admin, test_office, test_operator_actions, test_proposals
from backend.tests.test_office import ALINEA
from backend.tests.test_projects_api import create

operators = test_admin.operators
actions_enabled = test_operator_actions.actions_enabled
owner = test_office.owner
UNIO = test_admin.UNIO
pytestmark = pytest.mark.anyio

URL = "/api/admin/settings"


async def catalog(client) -> dict:
    response = await client.get(f"{URL}/types-and-stages", headers=UNIO)
    assert response.status_code == 200, response.text
    return response.json()


def kind(found: dict, key: str) -> dict:
    return next(t for t in found["types"] if t["key"] == key)


def stage(found: dict, key: str) -> dict:
    return next(s for s in found["stages"] if s["key"] == key)


def type_body(found_type: dict, **changes) -> dict:
    """A type as PUT takes it, as it is unless changed."""
    return {
        "labels": found_type["labels"],
        "hidden": found_type["hidden"],
        "stages": [
            {"key": s["key"], "usual": s["usual"], "about": s["about"]}
            for s in found_type["stages"]
        ],
    } | changes


async def new_proposal(client, headers, db_session, **changes) -> list[dict]:
    """A new proposal's first services (A42), proposals switched on for Alinea."""
    await test_proposals.switch_on(db_session)
    created = await create(client, headers, stages=[], proposal=True, **changes)
    assert created.status_code == 201, created.text
    found = await client.get(f"/api/projects/{created.json()['id']}/proposal", headers=headers)
    return found.json()["start"]["services"]


async def options(client, headers) -> dict:
    return (await client.get("/api/project-types", headers=headers)).json()


# -- who and where ----------------------------------------------------------------------


async def test_only_signed_in_operators_on_unios_address(client, operators, owner):
    assert (await client.get(f"{URL}/types-and-stages", headers=UNIO)).status_code == 401
    await test_admin.sign_in(client)
    assert (await client.get(f"{URL}/types-and-stages", headers=ALINEA)).status_code == 404
    assert (await client.get(f"{URL}/types-and-stages", headers=UNIO)).status_code == 200


async def test_changes_need_the_csrf_token_and_the_operator_login(client, operators, owner):
    headers = await test_admin.sign_in(client)
    body = {"labels": {"pt": "Restauro", "en": ""}}
    without_token = await client.post(f"{URL}/types", json=body, headers=UNIO)
    assert without_token.status_code == 403
    # This deployment has no operator login set up: the list is shown, not changed.
    assert (await catalog(client))["can_change"] is False
    unavailable = await client.post(f"{URL}/types", json=body, headers=headers)
    assert unavailable.status_code == 503


# -- what it shows ---------------------------------------------------------------------


async def test_lists_types_and_stages_with_the_projects_that_use_them(
    client, actions_enabled, owner
):
    await test_admin.sign_in(client)
    found = await catalog(client)
    assert found["can_change"] is True
    architecture = kind(found, "architecture")
    assert architecture["labels"]["pt"] == "Projeto Arquitetônico"
    assert architecture["projects"] >= 2  # the seeded offices' "Casa Jardim", at least
    listed = {s["key"]: s for s in architecture["stages"]}
    assert listed["briefing"]["usual"] and listed["briefing"]["about"]["pt"]
    assert not listed["detailing"]["usual"] and listed["detailing"]["about"] is None
    assert listed["briefing"]["projects"] >= 1
    assert stage(found, "briefing")["projects"] >= listed["briefing"]["projects"]
    assert kind(found, "other")["lists_every_stage"] is True
    # In order: the stages as every project lists them.
    keys = [s["key"] for s in found["stages"]]
    assert keys[0] == "briefing" and keys[-1] == "final_delivery"


# -- changing texts ---------------------------------------------------------------------


async def test_a_stages_texts_change_everywhere_at_once_and_are_audited(
    client, actions_enabled, owner, db_session
):
    headers = await test_admin.sign_in(client)
    found = stage(await catalog(client), "briefing")
    changed = await client.put(
        f"{URL}/stages/briefing",
        json={
            "titles": {"pt": "Conversa inicial", "en": ""},
            "about": {"pt": "Entendemos o que você precisa.", "en": "We learn what you need."},
            "hidden": False,
        },
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    after = stage(changed.json(), "briefing")
    # English left blank takes the Portuguese.
    assert after["titles"] == {"pt": "Conversa inicial", "en": "Conversa inicial"}
    assert after["projects"] == found["projects"]
    # Staff see the new name at once, for new projects and on existing ones.
    titles = {s["key"]: s["title"] for s in (await options(client, owner))["stages"]}
    assert titles["briefing"] == "Conversa inicial"
    page = (await client.get("/api/pages/casa-jardim", headers=owner)).json()
    assert "Conversa inicial" in [s["title"] for s in page["stages"]]
    event = (
        await db_session.execute(
            text(
                "SELECT actor, action, target_tenant_id, target_slug, request_id "
                "FROM operator_audit_events WHERE action LIKE 'settings:%'"
            )
        )
    ).one()
    assert (event.actor, event.action) == (test_admin.OPERATOR, "settings:stage:briefing")
    assert event.target_tenant_id is None and event.target_slug is None and event.request_id


@pytest.mark.parametrize(
    "texts",
    [
        {"pt": "   ", "en": "Briefing"},  # no Portuguese name
        {"pt": "x" * 81, "en": ""},  # longer than a stage's name may be
    ],
)
async def test_a_name_must_be_given_and_fit(client, actions_enabled, owner, texts):
    headers = await test_admin.sign_in(client)
    response = await client.put(
        f"{URL}/stages/briefing",
        json={"titles": texts, "about": {"pt": "Texto.", "en": ""}, "hidden": False},
        headers=headers,
    )
    assert (response.status_code, response.json()["error"]) == (422, "invalid_setting_text")


async def test_two_stages_cannot_share_a_name(client, actions_enabled, owner):
    headers = await test_admin.sign_in(client)
    response = await client.put(
        f"{URL}/stages/survey",
        json={
            "titles": {"pt": "briefing", "en": ""},
            "about": {"pt": "x", "en": ""},
            "hidden": False,
        },
        headers=headers,
    )
    assert (response.status_code, response.json()["error"]) == (409, "setting_name_taken")


# -- a type's stages ----------------------------------------------------------------------


async def test_a_type_lists_and_ticks_the_stages_set_for_it(
    client, actions_enabled, owner, db_session
):
    headers = await test_admin.sign_in(client)
    interiors = kind(await catalog(client), "interiors")
    body = type_body(
        interiors,
        stages=[
            {"key": "briefing", "usual": True, "about": {"pt": "Nossa conversa.", "en": ""}},
            {"key": "survey", "usual": False, "about": None},
            {"key": "documentation", "usual": True, "about": None},
        ],
    )
    changed = await client.put(f"{URL}/types/interiors", json=body, headers=headers)
    assert changed.status_code == 200, changed.text
    offered = next(t for t in (await options(client, owner))["types"] if t["key"] == "interiors")
    assert offered["stages"] == ["briefing", "documentation"]  # ticked, in the stages' order
    assert offered["offered"] == ["briefing", "survey", "documentation"]
    # A new proposal's services: its ticked stages, in the type's words or the general text.
    services = await new_proposal(
        client, owner, db_session, project_type="interiors", slug="nova-proposta"
    )
    assert [s["title"] for s in services] == ["Briefing", "Documentação"]
    # Documentação has no words of this type's: its general text (Briefing takes the
    # office's own text for a service of that name first, A42).
    general = stage(changed.json(), "documentation")["about"]["pt"]
    assert services[1]["description"] == general


async def test_outro_keeps_only_its_ticked_stages_and_lists_every_one(
    client, actions_enabled, owner
):
    headers = await test_admin.sign_in(client)
    other = kind(await catalog(client), "other")
    body = type_body(
        other,
        stages=[
            {"key": "briefing", "usual": True, "about": None},
            {"key": "survey", "usual": False, "about": None},
        ],
    )
    changed = await client.put(f"{URL}/types/other", json=body, headers=headers)
    assert [s["key"] for s in kind(changed.json(), "other")["stages"]] == ["briefing"]
    offered = next(t for t in (await options(client, owner))["types"] if t["key"] == "other")
    assert len(offered["offered"]) == len((await options(client, owner))["stages"])


async def test_a_type_lists_only_known_stages_once(client, actions_enabled, owner):
    headers = await test_admin.sign_in(client)
    interiors = kind(await catalog(client), "interiors")
    for stages in (
        [{"key": "nope", "usual": True, "about": None}],
        [{"key": "survey", "usual": True, "about": None}] * 2,
    ):
        response = await client.put(
            f"{URL}/types/interiors", json=type_body(interiors, stages=stages), headers=headers
        )
        assert (response.status_code, response.json()["error"]) == (422, "setting_not_found")
    missing = await client.put(f"{URL}/types/nope", json=type_body(interiors), headers=headers)
    assert missing.status_code == 422


# -- new ones ------------------------------------------------------------------------------


async def test_new_types_and_stages_come_last_with_a_key_from_their_name(
    client, actions_enabled, owner
):
    headers = await test_admin.sign_in(client)
    added = await client.post(
        f"{URL}/stages",
        json={
            "titles": {"pt": "Pós-Produção", "en": "Post-production"},
            "about": {"pt": "Ajustes.", "en": ""},
        },
        headers=headers,
    )
    assert added.status_code == 200, added.text
    assert added.json()["stages"][-1]["key"] == "pos_producao"
    typed = await client.post(
        f"{URL}/types", json={"labels": {"pt": "Restauro", "en": ""}}, headers=headers
    )
    restoration = typed.json()["types"][-1]
    assert (restoration["key"], restoration["stages"]) == ("restauro", [])
    # Offered at once, though it lists nothing until its stages are set.
    assert "restauro" in [t["key"] for t in (await options(client, owner))["types"]]
    again = await client.post(
        f"{URL}/types", json={"labels": {"pt": "RESTAURO", "en": ""}}, headers=headers
    )
    assert (again.status_code, again.json()["error"]) == (409, "setting_name_taken")


async def test_a_new_key_never_repeats_one_in_use():
    from backend.operators.catalog import new_key

    assert new_key("Pós-Produção!", set()) == "pos_producao"
    assert new_key("Pós Produção", {"pos_producao", "pos_producao_2"}) == "pos_producao_3"
    assert new_key("???", set()) == "item"


# -- hidden -----------------------------------------------------------------------------


async def test_a_hidden_type_stays_with_its_projects_but_is_no_longer_offered(
    client, actions_enabled, owner
):
    headers = await test_admin.sign_in(client)
    architecture = kind(await catalog(client), "architecture")
    hidden = await client.put(
        f"{URL}/types/architecture", json=type_body(architecture, hidden=True), headers=headers
    )
    assert hidden.status_code == 200, hidden.text
    assert "architecture" not in [t["key"] for t in (await options(client, owner))["types"]]
    refused = await create(client, owner, project_type="architecture", slug="nova-casa")
    assert (refused.status_code, refused.json()["error"]) == (422, "unknown_project_type")
    page = (await client.get("/api/pages/casa-jardim", headers=owner)).json()
    assert page["project_type"] == "Projeto Arquitetônico"  # kept, still named
    # No project switches to it; one that has it may keep it while changing other things.
    other_project = next(
        p
        for p in (await client.get("/api/projects", headers=owner)).json()
        if p["project_type"] != "architecture"
    )
    switch = await client.patch(
        f"/api/projects/{other_project['id']}/content",
        json={"row_version": other_project["row_version"], "project_type": "architecture"},
        headers=owner,
    )
    assert (switch.status_code, switch.json()["error"]) == (422, "unknown_project_type")


async def test_a_hidden_stage_stays_with_its_projects_but_is_no_longer_offered(
    client, actions_enabled, owner, db_session
):
    headers = await test_admin.sign_in(client)
    found = stage(await catalog(client), "survey")
    hidden = await client.put(
        f"{URL}/stages/survey",
        json={"titles": found["titles"], "about": found["about"], "hidden": True},
        headers=headers,
    )
    assert hidden.status_code == 200, hidden.text
    offered = await options(client, owner)
    assert "survey" not in [s["key"] for s in offered["stages"]]
    assert all("survey" not in t["offered"] + t["stages"] for t in offered["types"])
    refused = await create(client, owner, stages=["briefing", "survey"], slug="nova-casa")
    assert (refused.status_code, refused.json()["error"]) == (422, "unknown_stage")
    # A new proposal's services leave it out too.
    services = await new_proposal(client, owner, db_session, slug="nova-proposta")
    assert "Levantamento" not in [s["title"] for s in services]
    # Projects that have it keep it.
    page = (await client.get("/api/pages/casa-jardim", headers=owner)).json()
    assert "Levantamento" in [s["title"] for s in page["stages"]]


# -- order -------------------------------------------------------------------------------


async def test_the_order_is_set_whole(client, actions_enabled, owner):
    headers = await test_admin.sign_in(client)
    found = await catalog(client)
    keys = [t["key"] for t in found["types"]]
    turned = await client.put(
        f"{URL}/order", json={"kind": "types", "keys": keys[::-1]}, headers=headers
    )
    assert [t["key"] for t in turned.json()["types"]] == keys[::-1]
    assert [t["key"] for t in (await options(client, owner))["types"]] == keys[::-1]
    stages = [s["key"] for s in found["stages"]]
    moved = stages[1:] + stages[:1]  # Briefing last
    changed = await client.put(
        f"{URL}/order", json={"kind": "stages", "keys": moved}, headers=headers
    )
    assert [s["key"] for s in changed.json()["stages"]] == moved
    for partial in (stages[1:], stages + stages[:1]):
        response = await client.put(
            f"{URL}/order", json={"kind": "stages", "keys": partial}, headers=headers
        )
        assert (response.status_code, response.json()["error"]) == (422, "setting_not_found")


# -- the logins' rights ----------------------------------------------------------------------


async def test_only_the_operator_login_writes_the_lists(app, actions_enabled):
    """The app's login reads them; the operator's may change them (the self-test
    that the refusal is about rights, not the statement)."""
    from sqlalchemy.exc import ProgrammingError

    change = text("UPDATE stage_definitions SET hidden = hidden WHERE key = 'briefing'")
    async with app.state.sessionmaker() as db:
        with pytest.raises(ProgrammingError):
            await db.execute(change)
    async with app.state.operator_sessionmaker() as db:
        await db.execute(change)
        with pytest.raises(ProgrammingError):
            await db.execute(text("UPDATE projects SET name = name"))
