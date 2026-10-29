"""Client email updates (A12, A32, plan section 14): batching, what an email
says, who gets it, sending once, and unsubscribing."""

import json
import os
import re
import time
from pathlib import Path

import httpx2
import pytest
from sqlalchemy import text

from backend.notifications import digest
from backend.notifications.email import (
    Email,
    EmailError,
    OutboxSender,
    ResendSender,
    sender_for,
)
from backend.notifications.scan import run_maintenance
from backend.settings import Environment, Settings
from backend.tenancy.models import Locale
from backend.tests import test_office
from backend.tests.test_maintenance_scan import CASA, casa, folders  # noqa: F401
from backend.tests.test_office import ALINEA, NORTE

ROOT = Path(__file__).resolve().parents[2]

owner = test_office.owner  # fixtures

pytestmark = pytest.mark.anyio

STAFF = "dona@alinea.example"  # the `owner` fixture's account
CLIENT = "cliente@exemplo.com.br"
PDF = b"%PDF-1.4"


class Outbox:
    """A sender that keeps the emails; the next send to an address in `fail` fails."""

    def __init__(self):
        self.sent: list[Email] = []
        self.fail: set[str] = set()

    async def send(self, email: Email) -> str:
        if email.to in self.fail:
            self.fail.discard(email.to)
            raise EmailError("resend 503: busy")
        self.sent.append(email)
        return f"id-{len(self.sent)}"


def as_production(monkeypatch):
    """Clients may be emailed, as in production; local folders keep working."""
    monkeypatch.setattr(Settings, "email_staff_only", property(lambda self: False))


DEPLOYED_DB = "postgresql+psycopg://app@db/portal"


@pytest.fixture
def outbox():
    return Outbox()


async def run(app, outbox):
    return await run_maintenance(app.state.sessionmaker, app.state.settings, None, outbox)


async def add_recipients(db_session, *emails):
    for email in emails:
        await db_session.execute(
            text(
                f"INSERT INTO project_recipients (tenant_id, project_id, email) "
                f"SELECT tenant_id, id, :email FROM projects WHERE id = {CASA}"
            ),
            {"email": email},
        )


async def make_due(db_session):
    """As if the batch's last change were an hour old, and its files too."""
    await db_session.execute(
        text(
            "UPDATE notification_batches SET first_event_at = first_event_at - interval '1 hour',"
            " last_event_at = last_event_at - interval '1 hour'"
        )
    )


def age(path, minutes=5):
    then = time.time() - minutes * 60
    os.utime(path, (then, then))


async def new_file(app, outbox, folders, name="Croqui.pdf", stage="02 - Conceito"):  # noqa: F811
    path = folders / stage / name
    path.write_bytes(PDF)
    age(path)
    await run(app, outbox)
    return path


async def batches(db_session):
    return [
        tuple(row)
        for row in await db_session.execute(
            text("SELECT state FROM notification_batches ORDER BY created_at")
        )
    ]


@pytest.fixture
async def ready(app, db_session, owner, folders, outbox):  # noqa: F811
    """Casa Jardim scanned once (its files noted), with a staff and a client address."""
    await add_recipients(db_session, STAFF, CLIENT)
    await run(app, outbox)
    return folders


# -- batching -------------------------------------------------------------------------


async def test_nothing_goes_until_things_have_been_quiet(app, db_session, outbox, ready):
    await new_file(app, outbox, ready)
    assert await batches(db_session) == [("open",)]
    assert outbox.sent == []
    await make_due(db_session)
    report = await run(app, outbox)
    assert len(outbox.sent) == 1
    assert await batches(db_session) == [("sent",)]
    # Counted per office for analytics (each email is paid for).
    office = await db_session.scalar(text(f"SELECT tenant_id FROM projects WHERE id = {CASA}"))
    assert report.emails_by_tenant == {str(office): 1}


def test_due_after_45_quiet_minutes_or_2_hours_at_most():
    from datetime import UTC, datetime, timedelta

    from backend.notifications.models import NotificationBatch

    now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)

    def batch(first, last):
        return NotificationBatch(first_event_at=now - first, last_event_at=now - last)

    assert not digest.is_due(batch(timedelta(minutes=50), timedelta(minutes=10)), now)
    assert digest.is_due(batch(timedelta(minutes=50), timedelta(minutes=45)), now)
    # Uploads all afternoon still get an email: the hold closes it.
    assert digest.is_due(batch(timedelta(hours=2), timedelta(minutes=1)), now)


async def test_a_note_never_emails(app, client, db_session, owner, outbox, ready):
    from backend.tests.test_maintenance_scan import call

    await call(client, owner, "PUT", "/stages/2/notes", notes="Confira as medidas.")
    await run(app, outbox)
    assert await batches(db_session) == []


async def test_a_due_batch_goes_as_it_was_and_later_changes_wait_their_turn(
    app, db_session, outbox, ready
):
    """Due between two passes, then a new file: the email has only the old file,
    and the new one starts its own 45 minutes (section 14)."""
    await new_file(app, outbox, ready, "Croqui.pdf")
    await make_due(db_session)
    path = ready / "02 - Conceito" / "Fachada.pdf"
    path.write_bytes(PDF)
    age(path)
    await run(app, outbox)
    assert len(outbox.sent) == 1
    assert "foi atualizada: 1 arquivo enviado." in outbox.sent[0].text  # not Fachada.pdf too
    assert await batches(db_session) == [("sent",), ("open",)]


# Stages 3 to 6 of Casa Jardim's 7 completed, as if earlier: the last one is open.
ALL_BUT_THE_LAST = (
    f"UPDATE project_stages SET completed_at = now() WHERE project_id = {CASA} AND position < 7"
)


@pytest.mark.parametrize(
    ("setup", "position"),
    [
        (None, 3),  # a stage completed, then reopened
        (ALL_BUT_THE_LAST, 7),  # the project completed, then reopened
    ],
)
async def test_progress_taken_back_within_the_quiet_period_is_not_news(
    app, client, db_session, owner, outbox, ready, setup, position
):
    from backend.tests.test_maintenance_scan import call

    if setup:
        await db_session.execute(text(setup))
    await call(client, owner, "PUT", f"/stages/{position}/completion", completed=True)
    if setup:
        await call(client, owner, "PUT", "/completion")  # "Concluir projeto"
    await call(client, owner, "PUT", f"/stages/{position}/completion", completed=False)
    await run(app, outbox)
    await make_due(db_session)
    await run(app, outbox)
    assert outbox.sent == []  # nothing left to say
    assert await batches(db_session) == [("dropped",)]


async def test_archiving_drops_a_waiting_email_for_good(app, db_session, outbox, ready):
    await new_file(app, outbox, ready)
    await db_session.execute(
        text(f"UPDATE projects SET status = 'archived', archived_from = 'active' WHERE id = {CASA}")
    )
    await make_due(db_session)
    await run(app, outbox)
    assert await batches(db_session) == [("dropped",)]
    await db_session.execute(
        text(f"UPDATE projects SET status = 'active', archived_from = NULL WHERE id = {CASA}")
    )
    await run(app, outbox)
    assert outbox.sent == []  # back from the archive, the old news stays unsent


async def test_a_proposal_never_emails_its_client(app, client, db_session, owner, outbox, ready):
    """Staff send a proposal's link themselves (A42): saving one, or files and
    stages changing meanwhile, emails nobody."""
    from backend.tests.test_maintenance_scan import call
    from backend.tests.test_proposals import content

    await db_session.execute(text("UPDATE tenants SET features = '{proposals}'"))
    await db_session.execute(text(f"UPDATE projects SET status = 'proposal' WHERE id = {CASA}"))
    project_id = await db_session.scalar(text(f"SELECT id FROM projects WHERE id = {CASA}"))
    saved = await client.post(
        f"/api/projects/{project_id}/proposals", json=content(), headers=owner
    )
    assert saved.status_code == 201, saved.text
    await new_file(app, outbox, ready)
    await call(client, owner, "PUT", "/stages/3/completion", completed=True)
    await make_due(db_session)
    await run(app, outbox)
    assert (await batches(db_session), outbox.sent) == ([], [])


async def test_a_file_renamed_or_moved_meanwhile_shows_as_it_is_now(app, db_session, outbox, ready):
    path = await new_file(app, outbox, ready, "Croqui v1.pdf", "02 - Conceito")
    moved = ready / "01 - Briefing" / "Croqui final.pdf"
    path.rename(moved)  # renamed, and into the first stage
    age(moved)
    await make_due(db_session)
    await run(app, outbox)
    text_ = outbox.sent[0].text
    assert "A etapa 01 Briefing foi atualizada: 1 arquivo enviado." in text_
    assert "Croqui" not in text_  # files are counted, never named (Fabio, 26 Oct 2026)


async def test_each_stage_still_completed_is_news_named_where_it_is_now(
    app, client, db_session, owner, outbox, ready
):
    """Completed in any order; one reopened since, one moved within the quiet period."""
    from backend.tests.test_maintenance_scan import call

    for position in (5, 3, 4):
        await call(client, owner, "PUT", f"/stages/{position}/completion", completed=True)
    await call(client, owner, "PUT", "/stages/4/completion", completed=False)
    await call(client, owner, "POST", "/stages/5/move", direction=-1)  # Projeto Legal: now 04
    await run(app, outbox)
    await make_due(db_session)
    await run(app, outbox)
    text_ = outbox.sent[0].text
    assert "As seguintes etapas foram atualizadas:" in text_
    lines = [line for line in text_.splitlines() if "concluída" in line]
    assert lines == [
        "- 03 Estudo Preliminar: marcada como concluída",
        "- 04 Projeto Legal: marcada como concluída",
    ]


async def test_a_stage_reopened_is_news_unless_completed_again_meanwhile(
    app, client, db_session, owner, outbox, ready
):
    """Stages completed in an earlier email: one reopened, one reopened and completed
    again within the quiet period (Fabio, 25 Oct 2026)."""
    from backend.tests.test_maintenance_scan import call

    await db_session.execute(text(ALL_BUT_THE_LAST))
    await call(client, owner, "PUT", "/stages/4/completion", completed=False)
    await call(client, owner, "PUT", "/stages/5/completion", completed=False)
    await call(client, owner, "PUT", "/stages/5/completion", completed=True)
    await run(app, outbox)
    await make_due(db_session)
    await run(app, outbox)
    lines = [line for line in outbox.sent[0].text.splitlines() if "etapa" in line]
    assert lines == ["A etapa 04 Anteprojeto foi atualizada: reaberta."]


async def test_reopening_a_stage_of_a_completed_project_is_news(
    app, client, db_session, owner, outbox, ready
):
    from backend.tests.test_maintenance_scan import call

    await db_session.execute(text(ALL_BUT_THE_LAST))
    await call(client, owner, "PUT", "/stages/7/completion", completed=True)
    await call(client, owner, "PUT", "/completion")  # "Concluir projeto"
    await run(app, outbox)
    await make_due(db_session)
    await run(app, outbox)  # the project completed: sent
    await call(client, owner, "PUT", "/stages/3/completion", completed=False)
    await run(app, outbox)
    await make_due(db_session)
    await run(app, outbox)
    assert len(outbox.sent) == 2
    text_ = outbox.sent[1].text
    assert "A etapa 03 Estudo Preliminar foi atualizada: reaberta." in text_
    assert "concluído" not in text_  # active again: no longer said to be completed


async def test_the_last_stage_completed_says_nothing_of_the_project_until_staff_complete_it(
    app, client, db_session, owner, outbox, ready
):
    from backend.tests.test_maintenance_scan import call

    await db_session.execute(text(ALL_BUT_THE_LAST))
    await call(client, owner, "PUT", "/stages/7/completion", completed=True)  # "Agora não"
    await run(app, outbox)
    await make_due(db_session)
    await run(app, outbox)
    text_ = outbox.sent[0].text
    assert "A etapa 07 Compatibilização foi atualizada: marcada como concluída." in text_
    assert "O projeto foi concluído." not in text_


async def test_the_last_stage_completed_is_news_with_the_project(
    app, client, db_session, owner, outbox, ready
):
    from backend.tests.test_maintenance_scan import call

    await db_session.execute(text(ALL_BUT_THE_LAST))
    await call(client, owner, "PUT", "/stages/7/completion", completed=True)
    await call(client, owner, "PUT", "/completion")  # "Concluir projeto", when asked
    await run(app, outbox)
    await make_due(db_session)
    await run(app, outbox)
    text_ = outbox.sent[0].text
    assert "A etapa 07 Compatibilização foi atualizada: marcada como concluída." in text_
    assert "O projeto foi concluído." in text_


# -- who gets it ----------------------------------------------------------------------


async def test_outside_production_only_staff_addresses_get_email(app, db_session, outbox, ready):
    await new_file(app, outbox, ready)
    await make_due(db_session)
    await run(app, outbox)
    assert [e.to for e in outbox.sent] == [STAFF]  # never the client, in a test


async def test_in_production_every_subscribed_address_gets_its_own(
    app, db_session, outbox, ready, monkeypatch
):
    as_production(monkeypatch)
    await db_session.execute(
        text(f"UPDATE project_recipients SET status = 'unsubscribed' WHERE email = '{STAFF}'")
    )
    await new_file(app, outbox, ready)
    await make_due(db_session)
    await run(app, outbox)
    assert [e.to for e in outbox.sent] == [CLIENT]  # one each, never a shared list


def test_only_production_emails_clients():
    def settings(environment):
        return Settings(environment=environment, database_url=DEPLOYED_DB)

    assert settings(Environment.PRODUCTION).email_staff_only is False
    for environment in (Environment.LOCAL, Environment.TEST, Environment.STAGING):
        assert settings(environment).email_staff_only is True


async def test_nobody_to_tell_drops_the_batch(app, db_session, outbox, ready):
    await db_session.execute(text("UPDATE project_recipients SET status = 'unsubscribed'"))
    await new_file(app, outbox, ready)
    await make_due(db_session)
    await run(app, outbox)
    assert outbox.sent == []
    assert await batches(db_session) == [("dropped",)]


# -- what it says ---------------------------------------------------------------------


async def test_the_email_says_what_changed_and_links_the_page(app, db_session, outbox, ready):
    await new_file(app, outbox, ready, "Croqui.pdf")
    await new_file(app, outbox, ready, "Fachada.pdf")
    await make_due(db_session)
    await run(app, outbox)
    email = outbox.sent[0]
    assert "Casa Jardim" in email.subject  # the project it's about (the wording is the catalog's)
    assert "Há atualizações no projeto Casa Jardim." in email.text
    # One stage changed: a sentence, not a list; files counted, never named.
    assert "A etapa 02 Levantamento foi atualizada: 2 arquivos enviados." in email.text
    assert "Croqui" not in email.text and "Fachada" not in email.text
    assert "Croqui" not in email.html and "<ul" not in email.html
    # Tagged, so page analytics can tell visits that came from the email (A39).
    assert "/casa-jardim?utm_source=email&utm_medium=update" in email.text
    assert email.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert email.headers["List-Unsubscribe"].startswith("<http")


async def test_several_stages_read_as_a_list_each_with_its_changes(
    app, client, db_session, owner, outbox, ready
):
    from backend.tests.test_maintenance_scan import call

    await new_file(app, outbox, ready, "Croqui.pdf")  # into 02 Levantamento
    await call(client, owner, "PUT", "/stages/2/completion", completed=False)  # done in the seed
    await call(client, owner, "PUT", "/stages/3/completion", completed=True)
    await run(app, outbox)
    await make_due(db_session)
    await run(app, outbox)
    email = outbox.sent[0]
    lead = email.text.index("As seguintes etapas foram atualizadas:")
    assert email.text[lead:].splitlines()[1:3] == [
        "- 02 Levantamento: 1 arquivo enviado e reaberta",
        "- 03 Estudo Preliminar: marcada como concluída",
    ]
    assert email.html.count("<li") == 2


@pytest.mark.parametrize(("count", "said"), [(1, "1 arquivo enviado"), (4, "4 arquivos enviados")])
async def test_files_are_counted_in_the_right_form(app, db_session, outbox, ready, count, said):
    """Once a missing text here stopped every email (21 Oct 2026)."""
    for i in range(count):
        await new_file(app, outbox, ready, f"Prancha {i + 1}.pdf")
    await make_due(db_session)
    await run(app, outbox)
    assert f"A etapa 02 Levantamento foi atualizada: {said}." in outbox.sent[0].text


async def test_a_file_taken_down_before_sending_is_left_out(app, db_session, outbox, ready):
    path = await new_file(app, outbox, ready)
    path.rename(path.with_name("_" + path.name))  # hidden: the page no longer shows it
    await make_due(db_session)
    await run(app, outbox)
    assert outbox.sent == []
    assert await batches(db_session) == [("dropped",)]


async def test_a_file_still_changing_waits_for_the_next_pass(app, db_session, outbox, ready):
    path = await new_file(app, outbox, ready)
    await make_due(db_session)
    path.write_bytes(PDF + b"more")  # changed just now
    await run(app, outbox)
    assert outbox.sent == [] and await batches(db_session) == [("open",)]
    age(path)
    await run(app, outbox)
    assert len(outbox.sent) == 1


@pytest.mark.parametrize(
    ("logo_type", "png", "shown"),
    [
        ("image/png", None, "/api/office/logo?v="),
        ("image/svg+xml", "_marca/logo.png", "/api/office/logo?png=true&amp;v="),  # its PNG
        ("image/svg+xml", None, None),  # no PNG yet: the name, in text
    ],
)
async def test_the_email_shows_a_logo_email_programs_can_show(
    app, db_session, outbox, ready, logo_type, png, shown
):
    """Gmail and Outlook don't show SVG images: an SVG logo emails as its PNG."""
    await db_session.execute(
        text(
            "INSERT INTO office_profiles "
            "(tenant_id, display_name, logo_file_id, logo_type, logo_png_file_id) "
            "SELECT id, 'Alinea', '_marca/logo', :t, :png FROM tenants WHERE slug = 'alinea' "
            "ON CONFLICT (tenant_id) DO UPDATE SET logo_file_id = '_marca/logo', "
            "logo_type = :t, logo_png_file_id = :png"
        ),
        {"t": logo_type, "png": png},
    )
    await new_file(app, outbox, ready)
    await make_due(db_session)
    await run(app, outbox)
    html = outbox.sent[0].html
    assert ("<img" in html) is (shown is not None)
    if shown:
        assert shown in html


async def test_names_the_office_typed_cant_inject_html(
    app, client, db_session, owner, outbox, ready
):
    from datetime import date, timedelta

    from backend.tests.test_maintenance_scan import call

    day = (date.today() + timedelta(days=5)).isoformat()
    await call(
        client, owner, "PUT", "/meeting", title="<img src=x onerror=1>", day=day, start="10:00"
    )
    await run(app, outbox)
    await make_due(db_session)
    await run(app, outbox)
    html = outbox.sent[0].html
    assert "<img src=x" not in html and "&lt;img src=x" in html


async def test_several_meeting_changes_read_as_the_latest(
    app, client, db_session, owner, outbox, ready
):
    from datetime import date, timedelta

    from backend.tests.test_maintenance_scan import call

    day = (date.today() + timedelta(days=5)).isoformat()
    await call(client, owner, "PUT", "/meeting", title="Visita", day=day, start="10:00")
    await call(client, owner, "PUT", "/meeting", title="Visita à obra", day=day, start="15:30")
    await run(app, outbox)
    await make_due(db_session)
    await run(app, outbox)
    lines = [line for line in outbox.sent[0].text.splitlines() if "Reunião" in line]
    assert lines == [
        f"Reunião alterada: Visita à obra, {date.fromisoformat(day):%d/%m/%Y} às 15:30."
    ]


async def test_a_meeting_scheduled_and_cancelled_meanwhile_is_not_news(
    app, client, db_session, owner, outbox, ready
):
    from datetime import date, timedelta

    from backend.tests.test_maintenance_scan import call

    # Casa Jardim's seed meeting is cleared first, so the next one is new.
    await call(client, owner, "DELETE", "/meeting")
    await run(app, outbox)
    await make_due(db_session)
    await run(app, outbox)
    cancelled = [e.text for e in outbox.sent]
    assert any("foi cancelada" in t_ for t_ in cancelled)  # it was announced before: news
    day = (date.today() + timedelta(days=5)).isoformat()
    await call(client, owner, "PUT", "/meeting", title="Visita", day=day, start="10:00")
    await call(client, owner, "DELETE", "/meeting")
    await run(app, outbox)
    await make_due(db_session)
    await run(app, outbox)
    assert len(outbox.sent) == len(cancelled)  # scheduled and cancelled: nothing to say


# -- sending once ---------------------------------------------------------------------


async def test_a_failed_send_is_retried_and_nothing_goes_twice(
    app, db_session, outbox, ready, caplog, monkeypatch
):
    as_production(monkeypatch)
    await new_file(app, outbox, ready)
    await make_due(db_session)
    outbox.fail = {STAFF}  # the staff address fails once
    await run(app, outbox)
    assert [e.to for e in outbox.sent] == [CLIENT]
    assert await batches(db_session) == [("sending",)]  # kept for the retry, as it was
    assert any(
        "sending batch" in r.getMessage() and "busy" in r.getMessage() for r in caplog.records
    )
    await run(app, outbox)
    assert [e.to for e in outbox.sent] == [CLIENT, STAFF]  # only the one that failed
    assert await batches(db_session) == [("sent",)]
    keys = [e.idempotency_key for e in outbox.sent]
    assert len(set(keys)) == 2  # one key per address


async def test_removing_and_adding_back_an_address_sends_nothing_twice(
    app, client, db_session, owner, outbox, ready, monkeypatch
):
    """Kept by address: the retry of a half-sent email skips who already got it."""
    from backend.tests.test_project_settings import change, project

    as_production(monkeypatch)
    await new_file(app, outbox, ready)
    await make_due(db_session)
    outbox.fail = {STAFF}  # the staff address fails once
    await run(app, outbox)
    assert [e.to for e in outbox.sent] == [CLIENT]
    found = await project(client)
    removed = (await change(client, owner, found, recipients=[STAFF])).json()
    await change(client, owner, removed, recipients=[STAFF, CLIENT])  # back again
    await run(app, outbox)
    assert [e.to for e in outbox.sent] == [CLIENT, STAFF]  # not the client twice


async def test_a_half_sent_email_is_retried_as_it_was_and_new_changes_wait(
    app, db_session, outbox, ready, monkeypatch
):
    """Who already got it isn't skipped for the news that came after."""
    as_production(monkeypatch)
    await new_file(app, outbox, ready, "Croqui.pdf")
    await make_due(db_session)
    outbox.fail = {STAFF}  # the staff address fails once
    await run(app, outbox)  # the client gets Croqui
    path = ready / "02 - Conceito" / "Fachada.pdf"
    path.write_bytes(PDF)
    age(path)
    await run(app, outbox)  # the retry, and Fachada found
    retry = [e for e in outbox.sent if e.to == STAFF]
    assert len(retry) == 1 and "foi atualizada: 1 arquivo enviado." in retry[0].text  # as it was
    assert await batches(db_session) == [("sent",), ("open",)]  # Fachada waits its turn
    before = len(outbox.sent)
    await make_due(db_session)
    await run(app, outbox)
    later = outbox.sent[before:]
    assert sorted(e.to for e in later) == sorted([CLIENT, STAFF])  # both hear of it


async def test_an_address_added_while_retrying_doesnt_get_the_old_news(
    app, client, db_session, owner, outbox, ready, monkeypatch
):
    """The addresses are fixed when the email starts going out (section 14)."""
    as_production(monkeypatch)
    await new_file(app, outbox, ready)
    await make_due(db_session)
    outbox.fail = {STAFF}  # the staff address fails once
    await run(app, outbox)
    await add_recipients(db_session, "novo@exemplo.com.br")
    await run(app, outbox)  # the retry
    assert sorted(e.to for e in outbox.sent) == sorted([CLIENT, STAFF])


async def test_the_database_refuses_linking_a_change_to_another_projects_email(
    app, db_session, outbox, ready
):
    """Section 7: a link names the office and project too, so a mistake can't
    attach one project's change to another's email."""
    from sqlalchemy.exc import IntegrityError

    await new_file(app, outbox, ready)
    other = (
        "(SELECT id FROM projects WHERE name = 'Refúgio da Mantiqueira' AND tenant_id = "
        "(SELECT id FROM tenants WHERE slug = 'alinea'))"
    )
    await db_session.execute(
        text(f"INSERT INTO project_events (tenant_id, project_id, kind) SELECT tenant_id, id, "
             f"'project_completed' FROM projects WHERE id = {other}")
    )  # fmt: skip
    nested = await db_session.begin_nested()
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                f"UPDATE project_events SET batch_id = (SELECT id FROM notification_batches "
                f"LIMIT 1) WHERE project_id = {other}"
            )
        )
    await nested.rollback()


# -- unsubscribing --------------------------------------------------------------------


async def unsubscribe_link(app, db_session, outbox, ready):
    await new_file(app, outbox, ready)
    await make_due(db_session)
    await run(app, outbox)
    return outbox.sent[0].headers["List-Unsubscribe"].strip("<>").split("/", 3)[3]


async def status(db_session, email=STAFF):
    return await db_session.scalar(
        text("SELECT status FROM project_recipients WHERE email = :e"), {"e": email}
    )


async def test_opening_the_link_asks_and_confirming_unsubscribes(
    app, client, db_session, outbox, ready
):
    path = "/" + await unsubscribe_link(app, db_session, outbox, ready)
    page = await client.get(path, headers=ALINEA)
    assert page.status_code == 200 and "<form" in page.text
    assert await status(db_session) == "subscribed"  # a mail scanner opening it changes nothing
    done = await client.post(path, headers=ALINEA)
    # Says whose emails stop (the wording is the catalog's).
    assert done.status_code == 200 and "dona@alinea.example" in done.text
    assert await status(db_session) == "unsubscribed"


async def test_the_email_programs_one_click_unsubscribes(app, client, db_session, outbox, ready):
    path = "/" + await unsubscribe_link(app, db_session, outbox, ready)
    response = await client.post(
        path,
        content="List-Unsubscribe=One-Click",
        headers=ALINEA | {"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    assert await status(db_session) == "unsubscribed"


async def test_a_bad_or_another_offices_link_changes_nothing(
    app, client, db_session, outbox, ready
):
    path = "/" + await unsubscribe_link(app, db_session, outbox, ready)
    assert (await client.post(path[:-5] + "AAAAA", headers=ALINEA)).status_code == 404
    assert (await client.post(path, headers=NORTE)).status_code == 404  # isolation
    assert await status(db_session) == "subscribed"


async def test_an_old_link_still_works_after_the_address_was_removed_and_added_back(
    app, client, db_session, owner, outbox, ready
):
    from backend.tests.test_project_settings import change, project

    path = "/" + await unsubscribe_link(app, db_session, outbox, ready)
    found = await project(client)
    removed = (await change(client, owner, found, recipients=[CLIENT])).json()
    await change(client, owner, removed, recipients=[CLIENT, STAFF])  # a new row
    assert (await client.post(path, headers=ALINEA)).status_code == 200
    assert await status(db_session) == "unsubscribed"


async def test_unsubscribing_a_removed_address_keeps_it_off(
    app, client, db_session, owner, outbox, ready
):
    """Removed by staff, then the client's link: kept as unsubscribed, so adding it
    back can't override them."""
    from backend.tests.test_project_settings import change, project

    path = "/" + await unsubscribe_link(app, db_session, outbox, ready)
    found = await project(client)
    removed = (await change(client, owner, found, recipients=[CLIENT])).json()
    assert (await client.post(path, headers=ALINEA)).status_code == 200
    added = (await change(client, owner, removed, recipients=[CLIENT, STAFF])).json()
    assert {r["email"]: r["subscribed"] for r in added["recipients"]}[STAFF] is False


async def test_after_unsubscribing_nothing_more_is_sent(app, client, db_session, outbox, ready):
    path = "/" + await unsubscribe_link(app, db_session, outbox, ready)
    await client.post(path, headers=ALINEA)
    await new_file(app, outbox, ready, "Outro.pdf")
    await make_due(db_session)
    await run(app, outbox)
    assert len(outbox.sent) == 1  # only the one before


# -- the provider ---------------------------------------------------------------------


async def test_resend_gets_the_email_with_its_idempotency_key():
    seen = {}

    def resend(request):
        seen.update(
            auth=request.headers["authorization"],
            key=request.headers["idempotency-key"],
            body=request.content,
        )
        return httpx2.Response(200, json={"id": "re_123"})

    http = httpx2.AsyncClient(transport=httpx2.MockTransport(resend))
    sent = await ResendSender(http, "re_test").send(
        Email(
            sender="Alinea <atualizacoes@alinea.example>",
            to=CLIENT,
            subject="Novidades",
            html="<p>Oi</p>",
            text="Oi",
            idempotency_key="batch-1-2",
            reply_to="contato@alinea.example",
        )
    )
    assert sent == "re_123"
    assert (seen["auth"], seen["key"]) == ("Bearer re_test", "batch-1-2")
    assert b'"reply_to"' in seen["body"]


async def test_a_resend_refusal_is_an_error_with_its_detail_for_the_log():
    http = httpx2.AsyncClient(
        transport=httpx2.MockTransport(lambda r: httpx2.Response(422, json={"message": "bad"}))
    )
    with pytest.raises(EmailError) as error:
        await ResendSender(http, "re_test").send(
            Email(
                sender="a <a@b.co>", to=CLIENT, subject="s", html="h", text="t", idempotency_key="k"
            )
        )
    assert "422" in error.value.detail and "re_test" not in error.value.detail


def test_without_a_key_emails_are_written_locally_and_never_when_deployed(tmp_path):
    http = httpx2.AsyncClient()
    local = Settings(environment=Environment.LOCAL, email_outbox=str(tmp_path))
    assert isinstance(sender_for(local, http), OutboxSender)
    staging = Settings(environment=Environment.STAGING, database_url=DEPLOYED_DB)
    with pytest.raises(RuntimeError):
        sender_for(staging, http)
    keyed = local.model_copy(update={"resend_api_key": "re_test"})
    assert isinstance(sender_for(keyed, http), ResendSender)


# -- the email's words ----------------------------------------------------------------

_COUNTED = re.compile(r'\bt\(\s*\w+,\s*"(\w+)",\s*count=')


def counted_keys(source: str) -> set[str]:
    """The texts the code asks for by a count: each needs its _one and _other."""
    return set(_COUNTED.findall(source))


def test_every_text_asked_for_by_a_count_has_both_forms_in_every_language():
    """A missing form only fails when that count comes up: once, every email
    stopped (21 Oct 2026). So every such call is checked here, ahead of time."""
    code = "\n".join(
        p.read_text("utf-8") for p in (ROOT / "backend").rglob("*.py") if "tests" not in p.parts
    )
    keys = counted_keys(code)
    assert "filesSent" in keys
    for locale in Locale:
        texts = json.loads((ROOT / "backend" / "i18n" / f"{locale.value}.json").read_text("utf-8"))[
            "email"
        ]
        for key in keys:
            assert {f"{key}_one", f"{key}_other"} <= texts.keys(), (locale, key)


def test_the_count_check_finds_such_calls():
    assert counted_keys('x = t(locale, "andMore", count=2)') == {"andMore"}
    assert counted_keys('x = t(locale, "subject", name=n)') == set()
