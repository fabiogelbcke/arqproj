"""The client's addresses for email updates, in the Projeto dialog (A32)."""

import pytest
from sqlalchemy import text

from backend.identity.models import Role
from backend.notifications.models import RECIPIENTS_MAX
from backend.tests import test_office
from backend.tests.test_office import NORTE, sign_in_as
from backend.tests.test_project_settings import change, project

owner = test_office.owner  # fixtures

pytestmark = pytest.mark.anyio


def emails(found):
    return [(r["email"], r["subscribed"]) for r in found["recipients"]]


async def test_staff_list_the_clients_addresses(client, owner):
    found = await project(client)
    assert found["recipients"] == []
    response = await change(
        client,
        owner,
        found,
        recipients=[" Ana@Example.com ", "joao@example.com", "ana@example.com"],
    )
    assert response.status_code == 200, response.text
    # Trimmed, lowercase, each once, in the order given; the change bumps the version.
    assert emails(response.json()) == [("ana@example.com", True), ("joao@example.com", True)]
    assert response.json()["row_version"] == found["row_version"] + 1
    assert emails(await project(client)) == emails(response.json())


async def test_the_whole_list_is_sent_so_one_left_out_is_removed(client, owner):
    found = (
        await change(client, owner, await project(client), recipients=["a@x.com", "b@x.com"])
    ).json()
    after = (await change(client, owner, found, recipients=["b@x.com", "c@x.com"])).json()
    assert emails(after) == [("b@x.com", True), ("c@x.com", True)]


async def test_an_unchanged_list_changes_nothing(client, owner):
    found = (await change(client, owner, await project(client), recipients=["a@x.com"])).json()
    again = await change(client, owner, found, recipients=["A@x.com"])
    assert again.json()["row_version"] == found["row_version"]


async def test_an_address_the_client_unsubscribed_stays_off(client, db_session, owner):
    """Staff can't undo it: removing and adding it again keeps it unsubscribed."""
    found = (await change(client, owner, await project(client), recipients=["ana@x.com"])).json()
    await db_session.execute(
        text("UPDATE project_recipients SET status = 'unsubscribed' WHERE email = 'ana@x.com'")
    )
    removed = (await change(client, owner, found, recipients=[])).json()
    assert emails(removed) == [("ana@x.com", False)]  # still listed, still off
    added = (await change(client, owner, removed, recipients=["ana@x.com", "joao@x.com"])).json()
    assert emails(added) == [("ana@x.com", False), ("joao@x.com", True)]


@pytest.mark.parametrize(
    "recipients",
    [
        ["sem-arroba"],
        ["a@b"],
        ["ana@x.com", "x" * 250 + "@x.com"],
        # Refused since the shared rule (identity/emails.py); the old pattern let them by.
        ["ana..souza@x.com"],
        ["ana@gmail,com.br"],
        ["ana@-x.com"],
    ],
)
async def test_a_bad_address_is_refused_and_nothing_changes(client, owner, recipients):
    found = await project(client)
    response = await change(client, owner, found, recipients=recipients)
    assert (response.status_code, response.json()["error"]) == (422, "invalid_email")
    assert (await project(client))["recipients"] == []


async def test_a_long_list_is_refused(client, owner):
    many = [f"pessoa{i}@x.com" for i in range(RECIPIENTS_MAX + 1)]
    response = await change(client, owner, await project(client), recipients=many)
    assert response.status_code == 422


async def test_a_stale_dialog_cant_change_the_list(client, owner):
    seen_by_both = await project(client)
    assert (await change(client, owner, seen_by_both, recipients=["a@x.com"])).status_code == 200
    second = await change(client, owner, seen_by_both, recipients=["b@x.com"])
    assert (second.status_code, second.json()["error"]) == (409, "project_changed")
    assert emails(await project(client)) == [("a@x.com", True)]


async def test_another_office_never_sees_or_changes_the_list(client, db_session, owner):
    found = (await change(client, owner, await project(client), recipients=["ana@x.com"])).json()
    norte = await sign_in_as(client, db_session, "dona@norte.example", Role.OWNER, NORTE, "norte")
    response = await change(client, norte, found, recipients=["intruso@x.com"])
    assert (response.status_code, response.json()["error"]) == (404, "project_not_found")
    assert "ana@x.com" not in (await client.get("/api/projects", headers=norte)).text
    stored = (await db_session.execute(text("SELECT email FROM project_recipients"))).scalars()
    assert list(stored) == ["ana@x.com"]
