"""The client page's "Atualizações" (A28): the latest changes, files only while the
page shows them."""

import pytest
from sqlalchemy import text

from backend.tests import test_office
from backend.tests.test_maintenance_scan import CASA, PDF, call, folders, run  # noqa: F401
from backend.tests.test_office import ALINEA
from backend.tests.test_page_access import Roles

owner = test_office.owner  # fixtures

pytestmark = pytest.mark.anyio


async def updates(client):
    response = await client.get("/api/pages/casa-jardim/files", headers=ALINEA)
    assert response.status_code == 200, response.text
    return [(u["kind"], u["stage_position"], u["name"]) for u in response.json()["updates"]]


async def test_a_new_file_shows_where_and_as_it_is_now(app, client, owner, folders):  # noqa: F811
    await run(app)  # notes what's there
    (folders / "02 - Conceito" / "Croqui.pdf").write_bytes(PDF)
    await run(app)
    assert await updates(client) == [("file_published", 2, "Croqui.pdf")]
    # Renamed and moved to the first stage: the same file, as it is now.
    (folders / "02 - Conceito" / "Croqui.pdf").rename(
        folders / "01 - Briefing" / "Croqui final.pdf"
    )
    assert await updates(client) == [("file_published", 1, "Croqui final.pdf")]


async def test_a_file_taken_down_leaves_the_list(app, client, owner, folders):  # noqa: F811
    await run(app)
    path = folders / "02 - Conceito" / "Croqui.pdf"
    path.write_bytes(PDF)
    await run(app)
    path.rename(path.with_name("_Croqui.pdf"))  # hidden from the client
    assert await updates(client) == []  # not even its name


async def test_notes_meetings_and_progress_are_listed_newest_first(
    app,
    client,
    db_session,
    owner,
    folders,  # noqa: F811
):
    await call(client, owner, "PUT", "/stages/2/notes", notes="Confira as medidas.")
    await call(client, owner, "DELETE", "/meeting")  # the seed's meeting, cancelled
    listed = await updates(client)
    kinds = sorted(kind for kind, _, _ in listed)  # one test transaction: same time
    assert kinds == ["meeting_cleared", "note_changed"]
    cleared = next(u for u in listed if u[0] == "meeting_cleared")
    assert cleared[2]  # the cancelled meeting's title, for "Reunião cancelada"


async def test_visitors_of_a_protected_page_see_nothing_without_its_password(
    app,
    client,
    db_session,
    owner,
    folders,  # noqa: F811
):
    await call(client, owner, "PUT", "/stages/2/notes", notes="Confira as medidas.")
    await db_session.execute(
        text(f"UPDATE projects SET access_mode = 'password', password_hash = 'x' WHERE id = {CASA}")
    )
    Roles(client).visitor()
    response = await client.get("/api/pages/casa-jardim/files", headers=ALINEA)
    assert response.status_code == 403
