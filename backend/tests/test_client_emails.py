"""Client email updates (A12, A32, plan section 14): batching, what an email
says, who gets it, sending once, and unsubscribing."""

import os
import time

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
from backend.tests import test_office
from backend.tests.test_maintenance_scan import CASA, casa, folders  # noqa: F401
from backend.tests.test_office import ALINEA, NORTE

owner = test_office.owner  # fixtures

pytestmark = pytest.mark.anyio

STAFF = "dona@alinea.example"  # the `owner` fixture's account
CLIENT = "cliente@exemplo.com.br"
PDF = b"%PDF-1.4"


class Outbox:
    """A sender that keeps the emails; `fail` makes the next sends fail."""

    def __init__(self):
        self.sent: list[Email] = []
        self.fail = 0

    async def send(self, email: Email) -> str:
        if self.fail:
            self.fail -= 1
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
    await run(app, outbox)
    assert len(outbox.sent) == 1
    assert await batches(db_session) == [("sent",)]


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
    assert email.subject == "Novidades em Casa Jardim"
    assert "2 arquivos novos em 02 " in email.text
    assert "Croqui.pdf" in email.text and "Fachada.pdf" in email.text
    assert "/casa-jardim" in email.text
    assert email.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert email.headers["List-Unsubscribe"].startswith("<http")


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


@pytest.mark.parametrize(("logo_type", "shown"), [("image/png", True), ("image/svg+xml", False)])
async def test_the_logo_shows_unless_email_programs_cant_show_it(
    app, db_session, outbox, ready, logo_type, shown
):
    """Gmail and Outlook don't show SVG images: then the office's name, in text."""
    await db_session.execute(
        text(
            "INSERT INTO office_profiles (tenant_id, display_name, logo_file_id, logo_type) "
            "SELECT id, 'Alinea', '_marca/logo', :t FROM tenants WHERE slug = 'alinea' "
            "ON CONFLICT (tenant_id) DO UPDATE SET logo_file_id = '_marca/logo', logo_type = :t"
        ),
        {"t": logo_type},
    )
    await new_file(app, outbox, ready)
    await make_due(db_session)
    await run(app, outbox)
    html = outbox.sent[0].html
    assert ("/api/office/logo?v=" in html) is shown
    assert ("<img" in html) is shown


async def test_names_from_files_cant_inject_html(app, db_session, outbox, ready):
    await new_file(app, outbox, ready, '<img src=x onerror="alert(1)">.pdf')
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
        f"- Reunião alterada: Visita à obra, {date.fromisoformat(day):%d/%m/%Y} às 15:30."
    ]


# -- sending once ---------------------------------------------------------------------


async def test_a_failed_send_is_retried_and_nothing_goes_twice(
    app, db_session, outbox, ready, caplog, monkeypatch
):
    as_production(monkeypatch)
    await new_file(app, outbox, ready)
    await make_due(db_session)
    outbox.fail = 1  # the first address fails, the second goes
    await run(app, outbox)
    assert [e.to for e in outbox.sent] == [CLIENT]
    assert await batches(db_session) == [("open",)]  # kept for the retry
    assert any(
        "sending batch" in r.getMessage() and "busy" in r.getMessage() for r in caplog.records
    )
    await run(app, outbox)
    assert [e.to for e in outbox.sent] == [CLIENT, STAFF]  # only the one that failed
    assert await batches(db_session) == [("sent",)]
    keys = [e.idempotency_key for e in outbox.sent]
    assert len(set(keys)) == 2  # one key per address


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
    assert done.status_code == 200 and "Pronto." in done.text
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
