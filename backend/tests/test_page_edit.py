"""Edit mode, part 1: description, details, the next meeting and stage notes."""

from datetime import UTC, date, datetime, timedelta

import pytest

from backend.identity.models import Role
from backend.tests import test_office
from backend.tests.test_office import ALINEA, sign_in_as

owner = test_office.owner  # fixtures

pytestmark = pytest.mark.anyio

SLUG = "casa-jardim"


async def page(client, slug=SLUG):
    return (await client.get(f"/api/pages/{slug}", headers=ALINEA)).json()


async def edit(client, headers, method, path, slug=SLUG, **body):
    """`path` after /api/projects/{id}; sends the page's current row version."""
    shown = await page(client, slug)
    staff = shown["staff"]
    url = f"/api/projects/{staff['project_id']}{path}"
    if method == "DELETE":
        return await client.delete(f"{url}?row_version={staff['row_version']}", headers=headers)
    return await client.request(
        method, url, json={"row_version": staff["row_version"], **body}, headers=headers
    )


# -- description and details ----------------------------------------------------------


async def test_the_description_and_details_change(client, owner):
    response = await edit(
        client,
        owner,
        "PATCH",
        "/content",
        description="  Casa nova.\n- Pátio central  ",
        details=[
            {"key": "location", "value": "Joinville — SC"},
            {"key": "built_area", "value": "212,5"},
            {"key": "start_date", "value": "2026-11-03"},
        ],
    )
    assert response.status_code == 204, response.text
    shown = await page(client)
    assert shown["description"] == "Casa nova.\n- Pátio central"
    assert [(d["key"], d["value"]) for d in shown["details"]] == [
        ("location", "Joinville — SC"),
        ("built_area", 212.5),
        ("start_date", "2026-11-03"),
    ]


async def test_editing_the_description_doesnt_move_atualizado(client, owner):
    before = (await page(client))["last_update"]
    await edit(client, owner, "PATCH", "/content", description="Só um ajuste.")
    assert (await page(client))["last_update"] == before


@pytest.mark.parametrize(
    "details",
    [
        [{"key": "no-such-detail", "value": "x"}],
        [{"key": "location", "value": "A"}, {"key": "location", "value": "B"}],
        [{"key": "site_area", "value": "grande"}],
        [{"key": "site_area", "value": "-3"}],
        [{"key": "start_date", "value": "amanhã"}],
        [{"key": "location", "value": "   "}],
    ],
)
async def test_bad_details_are_refused_and_nothing_changes(client, owner, details):
    before = await page(client)
    response = await edit(client, owner, "PATCH", "/content", details=details)
    assert (response.status_code, response.json()["error"]) == (422, "invalid_detail")
    assert (await page(client))["details"] == before["details"]


async def test_a_change_made_meanwhile_is_not_overwritten(client, owner):
    stale = (await page(client))["staff"]
    assert (
        await edit(client, owner, "PATCH", "/content", description="Primeira")
    ).status_code == 204
    second = await client.patch(
        f"/api/projects/{stale['project_id']}/content",
        json={"row_version": stale["row_version"], "description": "Segunda"},
        headers=owner,
    )
    assert (second.status_code, second.json()["error"]) == (409, "project_changed")
    assert (await page(client))["description"] == "Primeira"


# -- the meeting ----------------------------------------------------------------------


def in_days(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


async def test_the_next_meeting_is_set_in_the_offices_time_zone(client, owner):
    before = (await page(client))["last_update"]
    response = await edit(
        client,
        owner,
        "PUT",
        "/meeting",
        title="Visita à obra",
        day=in_days(3),
        start="14:00",
        end="15:30",
        location="Obra",
        link="https://meet.example/abc",
    )
    assert response.status_code == 204, response.text
    meeting = (await page(client))["next_meeting"]
    assert meeting["title"] == "Visita à obra"
    starts = datetime.fromisoformat(meeting["starts_at"]).astimezone(UTC)
    ends = datetime.fromisoformat(meeting["ends_at"]).astimezone(UTC)
    assert (starts.hour, starts.minute) == (17, 0)  # 14:00 in São Paulo
    assert (ends.hour, ends.minute) == (18, 30)
    assert (await page(client))["last_update"] != before  # the client notices this


async def test_setting_the_meeting_changes_the_upcoming_one_not_a_second(client, owner):
    """Casa Jardim already has one upcoming (the seed's "Apresentação do layout")."""
    await edit(client, owner, "PUT", "/meeting", title="Nova data", day=in_days(9), start="10:00")
    shown = await page(client)
    assert shown["next_meeting"]["title"] == "Nova data"
    await edit(client, owner, "DELETE", "/meeting")
    assert (await page(client))["next_meeting"] is None  # no second one was left


@pytest.mark.parametrize(
    "changes",
    [
        {"title": ""},
        {"title": "x" * 41},
        {"start": "15:00", "end": "14:00"},
        {"link": "javascript:alert(1)"},
        {"location": "x" * 61},
    ],
)
async def test_a_bad_meeting_is_refused(client, owner, changes):
    body = {"title": "Reunião", "day": in_days(2), "start": "14:00"} | changes
    response = await edit(client, owner, "PUT", "/meeting", **body)
    assert (response.status_code, response.json()["error"]) == (422, "invalid_meeting")


# -- stage notes ----------------------------------------------------------------------


async def test_a_stage_note_reaches_the_page_and_moves_atualizado(client, owner):
    before = (await page(client))["last_update"]
    response = await edit(
        client, owner, "PUT", "/stages/3/notes", notes="  Confira as plantas antes da reunião. "
    )
    assert response.status_code == 204
    shown = await page(client)
    assert shown["stages"][2]["notes"] == "Confira as plantas antes da reunião."
    assert shown["last_update"] != before
    await edit(client, owner, "PUT", "/stages/3/notes", notes="")
    assert (await page(client))["stages"][2]["notes"] == ""


async def test_a_note_for_a_stage_that_doesnt_exist_is_refused(client, owner):
    response = await edit(client, owner, "PUT", "/stages/42/notes", notes="Oi")
    assert response.status_code == 404


# -- who may edit ---------------------------------------------------------------------


async def test_members_edit_too_but_only_with_their_csrf_token(client, db_session, owner):
    member = await sign_in_as(client, db_session, "membro@alinea.example", Role.MEMBER)
    assert (await edit(client, member, "PATCH", "/content", description="Oi")).status_code == 204
    no_token = await edit(client, ALINEA, "PATCH", "/content", description="Sem token")
    assert no_token.status_code in (401, 403)


async def test_detail_types_come_in_the_offices_language(client, owner):
    types = (await client.get("/api/detail-types", headers=ALINEA)).json()
    assert {"key": "site_area", "label": "Área do terreno", "type": "area"} in types
