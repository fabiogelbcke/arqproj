"""Comments on a project's files and stages, by clients and staff (A49): who may
post, where they show, what follows a file, and the emails they make."""

import httpx2
import pytest
from sqlalchemy import text

from backend.identity.models import Role
from backend.tests import test_maintenance_scan, test_office
from backend.tests.test_client_emails import (
    CLIENT,
    STAFF,
    Outbox,
    add_recipients,
    make_due,
)
from backend.tests.test_client_emails import run as run_with
from backend.tests.test_maintenance_scan import CASA
from backend.tests.test_office import ALINEA, sign_in_as
from backend.web import page_comments

owner = test_office.owner  # fixtures
folders = test_maintenance_scan.folders

pytestmark = pytest.mark.anyio

PDF = b"%PDF-1.4"
JPEG = b"\xff\xd8\xff\xe0 jpeg"


async def switch(db, feature: str, on: bool):
    change = (
        f"array_append(features, '{feature}')" if on else f"array_remove(features, '{feature}')"
    )
    await db.execute(text(f"UPDATE tenants SET features = {change} WHERE slug = 'alinea'"))


@pytest.fixture(autouse=True)
async def switched_on(owner, db_session):
    """Comments are a feature switched on per office (A40): on for these tests."""
    await switch(db_session, "comments", on=True)
    page_comments._posted.clear()
    yield
    page_comments._posted.clear()


@pytest.fixture
async def visitor(app):
    """A client: no session, the page's address."""
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def listing(client, headers=ALINEA):
    response = await client.get("/api/pages/casa-jardim/files", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def stage_comments(client, position=1):
    return (await listing(client))["stages"][position - 1]["comments"]


async def card(client, name, position=1):
    stages = (await listing(client))["stages"]
    return next(f for g in stages[position - 1]["groups"] for f in g["files"] if f["name"] == name)


async def post(client, headers=ALINEA, **body):
    return await client.post("/api/pages/casa-jardim/comments", json=body, headers=headers)


async def said(client, body, headers=ALINEA, **where):
    """Post, and fail loudly if it wasn't taken."""
    response = await post(client, headers, body=body, **where)
    assert response.status_code == 200, response.text
    return response.json()


async def events(db_session):
    rows = await db_session.execute(
        text(f"SELECT kind, stage_position, title FROM project_events WHERE project_id = {CASA}")
    )
    return [tuple(row) for row in rows]


# -- posting -----------------------------------------------------------------------------


async def test_a_client_comments_on_a_stage_signed_with_their_name(client, visitor, owner, folders):
    shown = await said(visitor, "  Podemos rever a sala?  ", position=1, name=" Maria ")
    assert (shown["author"], shown["name"], shown["body"]) == (
        "client",
        "Maria",
        "Podemos rever a sala?",
    )
    # Everyone who can open the page sees it: the client, and staff.
    for who in (visitor, client):
        assert [(c["name"], c["body"]) for c in await stage_comments(who)] == [
            ("Maria", "Podemos rever a sala?")
        ]
    assert await stage_comments(visitor, 2) == []


async def test_staff_comment_as_their_account_and_tell_the_client(
    client, db_session, owner, folders
):
    shown = await said(client, "Enviamos a revisão.", owner, position=1, name="Outro nome")
    assert (shown["author"], shown["name"]) == ("staff", "Ana")  # the account's, not a typed one
    assert await events(db_session) == [("office_commented", 1, None)]


async def test_staff_with_the_longest_name_allowed_can_comment(client, db_session, owner, folders):
    from backend.web.team import NAME_MAX

    long = "Ana " + "Beatriz " * 20
    await db_session.execute(
        text("UPDATE users SET name = :name WHERE email = 'dona@alinea.example'"),
        {"name": long[:NAME_MAX].strip()},
    )
    shown = await said(client, "Olá", owner, position=1)
    assert shown["name"] == long[:NAME_MAX].strip()


async def test_a_clients_comment_is_not_client_news(visitor, db_session, owner, folders):
    await said(visitor, "Olá", position=1, name="Maria")
    assert await events(db_session) == []


@pytest.mark.parametrize(
    "body",
    [
        {"body": "Olá", "position": 1},  # a client must sign
        {"body": "   ", "position": 1, "name": "Maria"},
        {"body": "Olá", "name": "Maria"},  # nowhere
        {"body": "Olá", "name": "Maria", "position": 1, "key": "x"},  # two places
    ],
)
async def test_an_unsigned_blank_or_misplaced_comment_is_refused(visitor, owner, folders, body):
    response = await visitor.post("/api/pages/casa-jardim/comments", json=body, headers=ALINEA)
    assert (response.status_code, response.json()["error"]) == (422, "invalid_comment")


async def test_a_stage_the_page_doesnt_have_is_refused(visitor, owner, folders):
    response = await post(visitor, body="Olá", position=40, name="Maria")
    assert response.status_code == 404


async def test_too_long_is_refused(visitor, owner, folders):
    response = await post(visitor, body="a" * 2001, position=1, name="Maria")
    assert response.status_code == 422
    response = await post(visitor, body="Olá", position=1, name="M" * 61)
    assert response.status_code == 422


async def test_a_device_posts_a_few_a_minute_and_staff_any(client, visitor, owner, folders):
    for n in range(page_comments.PER_MINUTE):
        await said(visitor, f"Comentário {n}", position=1, name="Maria")
    refused = await post(visitor, body="Mais um", position=1, name="Maria")
    assert (refused.status_code, refused.json()["error"]) == (429, "too_many_comments")
    await said(client, "A equipe segue", owner, position=1)


async def test_the_limit_frees_up_after_a_minute():
    project = "p"
    for _ in range(page_comments.PER_MINUTE):
        assert page_comments._admit(project, "device", now=100.0)
    assert not page_comments._admit(project, "device", now=159.0)
    assert page_comments._admit(project, "device", now=160.0)
    assert page_comments._admit(project, "another device", now=159.0)


async def test_a_locked_page_takes_comments_only_once_unlocked(visitor, db_session, owner, folders):
    await db_session.execute(
        text(f"UPDATE projects SET access_mode = 'password', password_hash = 'x' WHERE id = {CASA}")
    )
    response = await post(visitor, body="Olá", position=1, name="Maria")
    assert (response.status_code, response.json()["error"]) == (403, "page_locked")


async def test_an_archived_project_takes_no_new_comments(client, db_session, owner, folders):
    await db_session.execute(
        text(f"UPDATE projects SET status = 'archived', archived_from = 'active' WHERE id = {CASA}")
    )
    response = await post(client, owner, body="Olá", position=1)
    assert (response.status_code, response.json()["error"]) == (409, "project_archived")


async def test_signed_in_staff_must_send_the_csrf_token(client, owner, folders):
    response = await post(client, ALINEA, body="Olá", position=1)
    assert response.status_code == 403


# -- switched off --------------------------------------------------------------------------


async def test_switched_off_nothing_shows_and_nothing_is_taken(
    client, visitor, db_session, owner, folders
):
    await said(visitor, "Olá", position=1, name="Maria")
    await switch(db_session, "comments", on=False)
    found = await listing(visitor)
    assert found["stages"][0]["comments"] is None
    assert all(f["comments"] is None for g in found["stages"][0]["groups"] for f in g["files"])
    refused = await post(visitor, body="Olá", position=1, name="Maria")
    assert (refused.status_code, refused.json()["error"]) == (409, "feature_off")


async def test_with_comments_on_the_listing_is_never_kept_by_the_browser(visitor, owner, folders):
    response = await visitor.get("/api/pages/casa-jardim/files", headers=ALINEA)
    assert response.headers["cache-control"] == "private, no-store"


# -- on a file -----------------------------------------------------------------------------


async def test_a_files_comments_follow_it_to_its_new_version(visitor, db_session, owner, folders):
    first = await card(visitor, "Programa.pdf")
    await said(visitor, "Faltou a garagem", key=first["key"], name="Maria")
    await age_comments(db_session, 1)  # one test is one transaction: one now()
    (folders / "01 - Briefing" / "Programa v2.pdf").write_bytes(PDF)
    now = await card(visitor, "Programa.pdf")
    assert now["version"] == 2
    assert [c["body"] for c in now["comments"]] == ["Faltou a garagem"]
    # Commented on its new version too: one conversation, oldest first.
    await said(visitor, "Agora sim", key=now["key"], name="Maria")
    again = await card(visitor, "Programa.pdf")
    assert [c["body"] for c in again["comments"]] == ["Faltou a garagem", "Agora sim"]


async def test_a_files_comments_follow_it_renamed_or_moved(visitor, owner, folders):
    """Local files keep their identity across renames, as Drive ids do."""
    first = await card(visitor, "Programa.pdf")
    await said(visitor, "Faltou a garagem", key=first["key"], name="Maria")
    (folders / "01 - Briefing" / "Programa.pdf").rename(folders / "02 - Conceito" / "Briefing.pdf")
    moved = await card(visitor, "Briefing.pdf", position=2)
    assert [c["body"] for c in moved["comments"]] == ["Faltou a garagem"]


async def test_a_hidden_file_takes_its_comments_off_the_page(visitor, owner, folders):
    first = await card(visitor, "Programa.pdf")
    await said(visitor, "Faltou a garagem", key=first["key"], name="Maria")
    (folders / "01 - Briefing" / "Programa.pdf").rename(folders / "01 - Briefing" / "_Programa.pdf")
    found = await listing(visitor)
    assert not any(f["comments"] for g in found["stages"][0]["groups"] for f in g["files"])
    assert found["stages"][0]["comments"] == []  # nor do they move to the stage


async def test_a_comparisons_two_images_are_one_conversation(visitor, db_session, owner, folders):
    await switch(db_session, "before_after", on=True)
    for name in ("Cozinha (antes).jpg", "Cozinha (depois).jpg"):
        (folders / "01 - Briefing" / name).write_bytes(JPEG)
    found = await card(visitor, "Cozinha")
    await said(visitor, "Ficou ótimo", key=found["comparison"]["after"]["key"], name="Maria")
    assert [c["body"] for c in (await card(visitor, "Cozinha"))["comments"]] == ["Ficou ótimo"]


async def test_a_key_from_another_page_or_expired_is_not_found(visitor, owner, folders):
    response = await post(visitor, body="Olá", key="not-a-key", name="Maria")
    assert (response.status_code, response.json()["error"]) == (404, "file_not_found")


async def test_a_removed_stage_takes_its_comments(visitor, db_session, owner, folders):
    await said(visitor, "Olá", position=2, name="Maria")
    await db_session.execute(
        text(f"DELETE FROM project_stages WHERE project_id = {CASA} AND position = 2")
    )
    assert await db_session.scalar(text("SELECT count(*) FROM comments")) == 0


# -- removing -------------------------------------------------------------------------------


async def test_staff_remove_any_comment(client, visitor, owner, folders):
    shown = await said(visitor, "Spam", position=1, name="Maria")
    gone = await client.delete(f"/api/pages/casa-jardim/comments/{shown['id']}", headers=owner)
    assert gone.status_code == 204
    assert await stage_comments(visitor) == []
    again = await client.delete(f"/api/pages/casa-jardim/comments/{shown['id']}", headers=owner)
    assert (again.status_code, again.json()["error"]) == (404, "comment_not_found")


async def remove(who, comment_id, headers=ALINEA, receipt=None):
    extra = {"X-Comment-Receipt": receipt} if receipt is not None else {}
    return await who.delete(
        f"/api/pages/casa-jardim/comments/{comment_id}", headers={**headers, **extra}
    )


async def test_a_client_removes_their_own_with_the_receipt_their_device_kept(
    visitor, owner, folders
):
    mine = await said(visitor, "Mandei por engano", position=1, name="Maria")
    other = await said(visitor, "Outro", position=1, name="João")
    assert mine["receipt"] and mine["receipt"] != other["receipt"]
    # Without its receipt, or with another comment's, it stays.
    for receipt, status in ((None, 401), (other["receipt"], 403), ("x" * 64, 403)):
        refused = await remove(visitor, mine["id"], receipt=receipt)
        assert refused.status_code == status
    assert len(await stage_comments(visitor)) == 2
    assert (await remove(visitor, mine["id"], receipt=mine["receipt"])).status_code == 204
    assert [c["body"] for c in await stage_comments(visitor)] == ["Outro"]
    assert (await remove(visitor, mine["id"], receipt=mine["receipt"])).status_code == 404


async def test_staff_get_no_receipt_and_a_client_cannot_take_theirs(
    client, visitor, owner, folders
):
    office = await said(client, "Da equipe", owner, position=1)
    assert office["receipt"] is None
    guess = await remove(visitor, office["id"], receipt="x" * 64)
    assert (guess.status_code, guess.json()["error"]) == (403, "comment_not_yours")


async def test_a_member_removes_only_their_own_and_an_owner_any(
    client, visitor, db_session, owner, folders
):
    by_client = await said(visitor, "Do cliente", position=1, name="Maria")
    by_owner = await said(client, "Da dona", owner, position=1)
    member = await sign_in_as(client, db_session, "bruno@alinea.example", Role.MEMBER)
    by_member = await said(client, "Do Bruno", member, position=1)
    # What the listing says each may remove, for the member asking.
    shown = {c["body"]: c["removable"] for c in await stage_comments(client)}
    assert shown == {"Do cliente": False, "Da dona": False, "Do Bruno": True}
    for other in (by_client, by_owner):
        refused = await remove(client, other["id"], member)
        assert (refused.status_code, refused.json()["error"]) == (403, "comment_not_yours")
    assert (await remove(client, by_member["id"], member)).status_code == 204
    # The owner: anyone's.
    again = await sign_in_as(client, db_session, "dona2@alinea.example", Role.OWNER)
    assert all(c["removable"] for c in await stage_comments(client))
    assert (await remove(client, by_client["id"], again)).status_code == 204
    assert (await remove(client, by_owner["id"], again)).status_code == 204
    assert await stage_comments(client) == []


async def test_a_client_sees_nothing_marked_removable(visitor, client, owner, folders):
    await said(client, "Da equipe", owner, position=1)
    await said(visitor, "Do cliente", position=1, name="Maria")
    assert not any(c["removable"] for c in await stage_comments(visitor))


# -- the updates panel ----------------------------------------------------------------------


async def test_the_offices_comments_are_one_update_per_stage_or_file(client, owner, folders):
    await said(client, "Primeiro", owner, position=1)
    await said(client, "Segundo", owner, position=1)
    first = await card(client, "Programa.pdf")
    await said(client, "Sobre o programa", owner, key=first["key"])
    updates = (await listing(client))["updates"]
    assert sorted((u["kind"], u["stage_position"], u["name"] or "") for u in updates) == [
        ("office_commented", 1, ""),
        ("office_commented", 1, "Programa.pdf"),
    ]


async def test_switched_off_the_offices_comments_leave_the_updates(
    client, db_session, owner, folders
):
    await said(client, "Primeiro", owner, position=1)
    await switch(db_session, "comments", on=False)
    assert (await listing(client))["updates"] == []


# -- emails ---------------------------------------------------------------------------------


async def age_comments(db_session, minutes):
    await db_session.execute(
        text(f"UPDATE comments SET created_at = created_at - interval '{minutes} minutes'")
    )


async def test_a_clients_comments_email_the_staff_once_quiet(
    app, visitor, db_session, owner, folders
):
    outbox = Outbox()
    await said(visitor, "Podemos rever a sala?", position=1, name="Maria")
    await run_with(app, outbox)
    assert outbox.sent == []  # just posted: more may follow
    first = await card(visitor, "Programa.pdf")
    await said(visitor, "Faltou a <garagem>", key=first["key"], name="João")
    await age_comments(db_session, 6)
    await run_with(app, outbox)
    [email] = outbox.sent
    assert email.to == STAFF
    assert email.subject == "2 novos comentários em Casa Jardim"
    assert "Maria, em 01 Briefing" in email.text and "Podemos rever a sala?" in email.text
    assert "João, em Programa.pdf" in email.text
    assert "Faltou a &lt;garagem&gt;" in email.html  # what a client typed is never HTML
    await run_with(app, outbox)
    assert len(outbox.sent) == 1  # told once


async def test_comments_that_keep_coming_go_after_half_an_hour(
    app, visitor, db_session, owner, folders
):
    outbox = Outbox()
    await said(visitor, "Primeiro", position=1, name="Maria")
    await age_comments(db_session, 31)
    await said(visitor, "Mais um, agora", position=1, name="Maria")
    await run_with(app, outbox)
    assert len(outbox.sent) == 1


async def test_with_a_project_team_only_its_members_are_emailed(
    app, client, visitor, db_session, owner, folders
):
    await switch(db_session, "project_members", on=True)
    await sign_in_as(client, db_session, "bruno@alinea.example", Role.MEMBER)
    await db_session.execute(
        text(
            "INSERT INTO project_members (tenant_id, project_id, user_id) "
            f"SELECT tenant_id, {CASA}, id FROM users WHERE email = 'bruno@alinea.example'"
        )
    )
    outbox = Outbox()
    await said(visitor, "Olá", position=1, name="Maria")
    await age_comments(db_session, 6)
    await run_with(app, outbox)
    assert [e.to for e in outbox.sent] == ["bruno@alinea.example"]


async def test_a_failed_email_is_retried_and_none_goes_twice(
    app, client, visitor, db_session, owner, folders
):
    await sign_in_as(client, db_session, "bruno@alinea.example", Role.MEMBER)
    outbox = Outbox()
    outbox.fail.add("bruno@alinea.example")
    await said(visitor, "Olá", position=1, name="Maria")
    await age_comments(db_session, 6)
    await run_with(app, outbox)
    assert [e.to for e in outbox.sent] == [STAFF]
    await run_with(app, outbox)
    keys = {e.to: e.idempotency_key for e in outbox.sent}
    assert sorted(e.to for e in outbox.sent) == ["bruno@alinea.example", STAFF, STAFF]
    # The one already sent is sent again under the same key: Resend sends it once.
    first, again = (e.idempotency_key for e in outbox.sent if e.to == STAFF)
    assert first == again and keys[STAFF] == first
    await run_with(app, outbox)
    assert len(outbox.sent) == 3


async def test_removed_or_switched_off_comments_never_email(
    app, client, visitor, db_session, owner, folders
):
    outbox = Outbox()
    shown = await said(visitor, "Spam", position=1, name="Maria")
    await client.delete(f"/api/pages/casa-jardim/comments/{shown['id']}", headers=owner)
    await said(visitor, "Olá", position=1, name="Maria")
    await switch(db_session, "comments", on=False)
    await age_comments(db_session, 6)
    await run_with(app, outbox)
    await switch(db_session, "comments", on=True)
    await run_with(app, outbox)
    assert outbox.sent == []  # off when due: not news later either


async def test_the_offices_comments_reach_the_clients_update_email(
    app, client, db_session, owner, folders
):
    outbox = Outbox()
    await add_recipients(db_session, STAFF, CLIENT)
    await run_with(app, outbox)  # the files noted
    await said(client, "Enviamos a revisão.", owner, position=1)
    await said(client, "E mais isto.", owner, position=1)
    await run_with(app, outbox)  # batched
    await make_due(db_session)
    await run_with(app, outbox)
    [email] = [e for e in outbox.sent if e.to == STAFF]
    assert "A etapa 01 Briefing foi atualizada: 2 comentários do escritório." in email.text


async def test_a_clients_comment_reaches_staff_while_drive_fails(
    app, visitor, db_session, owner, folders, monkeypatch
):
    """The email needs nothing from Drive: a project whose files can't be read
    (its folder gone, Drive down) still tells its staff."""
    from backend.notifications import scan
    from backend.storage.base import StorageError, StorageProblem

    async def gone(db, storage, project):
        raise StorageError(StorageProblem.NOT_FOUND, "folder gone")

    outbox = Outbox()
    await said(visitor, "Olá", position=1, name="Maria")
    await age_comments(db_session, 6)
    monkeypatch.setattr(scan, "scan_project", gone)
    await run_with(app, outbox)
    assert [e.to for e in outbox.sent] == [STAFF]
    await run_with(app, outbox)
    assert len(outbox.sent) == 1  # marked as told, though the scan failed after


async def test_a_bug_in_the_scan_still_keeps_the_comments_told(
    app, visitor, db_session, owner, folders, monkeypatch
):
    from backend.notifications import scan

    async def broken(db, storage, project):
        raise RuntimeError("a bug")

    outbox = Outbox()
    await said(visitor, "Olá", position=1, name="Maria")
    await age_comments(db_session, 6)
    monkeypatch.setattr(scan, "scan_project", broken)
    await run_with(app, outbox)
    await run_with(app, outbox)
    assert len(outbox.sent) == 1


async def test_a_retry_sends_the_same_email_though_comments_came_meanwhile(
    app, client, visitor, db_session, owner, folders
):
    """A comment arriving between a failed send and its retry waits for the next
    email: the retry is the same email, under the same key, so nobody gets two."""
    await sign_in_as(client, db_session, "bruno@alinea.example", Role.MEMBER)
    outbox = Outbox()
    outbox.fail.add("bruno@alinea.example")
    await said(visitor, "Primeiro", position=1, name="Maria")
    await age_comments(db_session, 6)
    await run_with(app, outbox)  # Ana got it; Bruno's failed
    await said(visitor, "Segundo", position=1, name="Maria")
    await run_with(app, outbox)  # the retry: the first email again
    to_ana = [e for e in outbox.sent if e.to == STAFF]
    assert len({e.idempotency_key for e in to_ana}) == 1  # Resend sends it once
    assert all("Segundo" not in e.text for e in outbox.sent)
    await age_comments(db_session, 6)
    await run_with(app, outbox)  # then the next email, with the new comment
    last = [e for e in outbox.sent if "Segundo" in e.text]
    assert sorted(e.to for e in last) == ["bruno@alinea.example", STAFF]
    assert "Primeiro" not in last[0].text
    # Each address got the first comment under one key only: one email from Resend.
    for to in ("bruno@alinea.example", STAFF):
        first = {e.idempotency_key for e in outbox.sent if e.to == to and "Primeiro" in e.text}
        assert len(first) == 1


async def test_an_office_comment_removed_is_no_news(app, client, db_session, owner, folders):
    """Removed, it leaves the updates panel and the client's next email."""
    outbox = Outbox()
    await add_recipients(db_session, STAFF, CLIENT)
    await run_with(app, outbox)  # the files noted
    shown = await said(client, "Por engano", owner, position=1)
    await said(client, "Este fica", owner, position=2)
    # Two on one stage, one of them removed: the other still counts, alone.
    await age_comments(db_session, 1)
    # (One test is one transaction, so one now(): its events go back with them.)
    await db_session.execute(
        text("UPDATE project_events SET occurred_at = occurred_at - interval '1 minute'")
    )
    again = await said(client, "Também por engano", owner, position=2)
    await client.delete(f"/api/pages/casa-jardim/comments/{shown['id']}", headers=owner)
    await client.delete(f"/api/pages/casa-jardim/comments/{again['id']}", headers=owner)
    updates = (await listing(client))["updates"]
    assert [(u["kind"], u["stage_position"]) for u in updates] == [("office_commented", 2)]
    await run_with(app, outbox)
    await make_due(db_session)
    await run_with(app, outbox)
    [email] = [e for e in outbox.sent if e.to == STAFF]
    assert "A etapa 02 Levantamento foi atualizada: 1 comentário do escritório." in email.text
    assert "01 Briefing" not in email.text


async def test_the_project_stays_locked_while_its_files_are_scanned(
    app, visitor, db_session, owner, folders, monkeypatch
):
    """Emailing staff first must not end the project's lock (a commit would):
    another pass, or a switch of Drive account, waits for the scan (plan section 9)."""
    from backend.notifications import scan

    real = scan.scan_project
    held = []

    async def watched(db, storage, project):
        held.append(
            await db.scalar(
                text(
                    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
                    "AND pid = pg_backend_pid() AND classid = :key"
                ),
                {"key": scan.MAINTENANCE_LOCK},
            )
        )
        return await real(db, storage, project)

    await said(visitor, "Olá", position=1, name="Maria")
    await age_comments(db_session, 6)
    monkeypatch.setattr(scan, "scan_project", watched)
    outbox = Outbox()
    await run_with(app, outbox)
    assert len(outbox.sent) == 1 and held and all(held)


async def test_a_failure_after_the_staff_email_does_not_send_it_again(
    app, visitor, db_session, owner, folders, monkeypatch
):
    """Drive failing while the client's update email is made: the staff email
    sent before it stays told."""
    from backend.notifications import digest
    from backend.storage.base import StorageError, StorageProblem

    async def drive_down(db, project, now):
        raise StorageError(StorageProblem.UNAVAILABLE, "Drive said 503")

    outbox = Outbox()
    await said(visitor, "Olá", position=1, name="Maria")
    await age_comments(db_session, 6)
    monkeypatch.setattr(digest, "to_send", drive_down)
    await run_with(app, outbox)
    await run_with(app, outbox)
    assert len(outbox.sent) == 1


async def test_an_unconfirmed_address_gets_no_clients_comments(
    app, visitor, db_session, owner, folders
):
    """Joined by the shared link (A36) and not yet confirmed: perhaps mistyped."""
    from backend.identity import accounts

    await accounts.create_user(
        db_session, email="novo@alinea.example", name="Novo", email_confirmed=False
    )
    outbox = Outbox()
    await said(visitor, "Olá", position=1, name="Maria")
    await age_comments(db_session, 6)
    await run_with(app, outbox)
    assert [e.to for e in outbox.sent] == [STAFF]
