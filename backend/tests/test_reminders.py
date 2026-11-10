"""Meeting reminders and the notice settings (A48): when each reminder is due,
what it says and to whom, sending once per meeting time, the video call's link,
and "Configurações" → "Avisos"."""

import logging
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from backend.notifications import digest, notices, whatsapp_updates
from backend.notifications.digest import StageNews, Summary
from backend.notifications.models import NotificationBatch, WhatsAppNews
from backend.notifications.reminders import Reminder, day_reminder_at, due
from backend.notifications.whatsapp import (
    REMINDER_TEMPLATE,
    REMINDER_VIDEO_TEMPLATE,
    short_link,
)
from backend.tenancy.models import Locale
from backend.tests import test_admin, test_office, test_operator_actions
from backend.tests.test_client_emails import STAFF, Outbox, add_recipients, make_due, new_file
from backend.tests.test_maintenance_scan import CASA, folders  # noqa: F401
from backend.tests.test_whatsapp import CLIENT, Phone, add_number, casa_ids, run, switch_on

owner = test_office.owner  # fixtures
operators = test_admin.operators
actions_enabled = test_operator_actions.actions_enabled
UNIO = test_admin.UNIO

pytestmark = pytest.mark.anyio

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
OFFICE = SimpleNamespace(zone=SAO_PAULO, locale=Locale.PT_BR)
CALL = "https://meet.google.com/abc-defg-hij"
URL = "/api/admin/settings/notices"


def local(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=SAO_PAULO)


def meeting(starts, link=None, day_for=None, soon_for=None, set_at=None):
    return SimpleNamespace(
        starts_at=starts,
        link=link,
        reminded_day_for=day_for,
        reminded_soon_for=soon_for,
        updated_at=set_at or starts - timedelta(days=5),
    )


# -- when ----------------------------------------------------------------------------


def test_the_days_reminder_is_the_morning_of_or_the_evening_before_an_early_meeting():
    rules = notices.DEFAULT
    assert day_reminder_at(local(12, 14), OFFICE, rules) == local(12, 8, 30)
    assert day_reminder_at(local(12, 9, 30), OFFICE, rules) == local(12, 8, 30)
    # Less than an hour after 8:30: a pass every 10 minutes could remind at the start.
    assert day_reminder_at(local(12, 9, 29), OFFICE, rules) == local(11, 18)
    assert day_reminder_at(local(12, 7), OFFICE, rules) == local(11, 18)
    # In the office's time zone, whatever the meeting's is stored in.
    assert day_reminder_at(local(12, 14).astimezone(UTC), OFFICE, rules) == local(12, 8, 30)
    later = replace(rules, morning=time(9), evening=time(20))
    assert day_reminder_at(local(12, 14), OFFICE, later) == local(12, 9)
    assert day_reminder_at(local(12, 9, 30), OFFICE, later) == local(11, 20)


def test_a_reminder_is_due_from_its_time_until_the_meeting_starts():
    rules = notices.DEFAULT
    talk = meeting(local(12, 14))
    assert due(talk, OFFICE, rules, local(12, 8, 29)) is None
    assert due(talk, OFFICE, rules, local(12, 8, 30)) is Reminder.DAY
    assert due(talk, OFFICE, rules, local(12, 13, 50)) is Reminder.DAY  # a pass ran late
    assert due(talk, OFFICE, rules, local(12, 14)) is None  # started: no use now
    video = meeting(local(12, 14), link=CALL, day_for=local(12, 14))
    assert due(video, OFFICE, rules, local(12, 13, 29)) is None
    assert due(video, OFFICE, rules, local(12, 13, 30)) is Reminder.SOON
    # Due together (the passes stopped all morning): only the video one goes.
    assert due(replace_ns(video, reminded_day_for=None), OFFICE, rules, local(12, 13, 40)) is (
        Reminder.SOON
    )
    # No video reminder without a link.
    assert due(meeting(local(12, 14), day_for=local(12, 14)), OFFICE, rules, local(12, 13, 45)) is (
        None
    )


def replace_ns(found: SimpleNamespace, **changes) -> SimpleNamespace:
    return SimpleNamespace(**(vars(found) | changes))


def test_each_reminder_goes_once_per_meeting_time():
    rules = notices.DEFAULT
    sent = meeting(local(12, 14), link=CALL, day_for=local(12, 14), soon_for=local(12, 14))
    assert due(sent, OFFICE, rules, local(12, 13, 45)) is None
    # Moved to 16:00 the same day (staff changed it at 10:00): reminded again.
    moved = replace_ns(sent, starts_at=local(12, 16), updated_at=local(12, 10))
    assert due(moved, OFFICE, rules, local(12, 15, 30)) is Reminder.SOON
    # The day's reminder for the new time had come due before the change: the
    # update about the change tells the client instead.
    assert due(replace_ns(moved, link=None), OFFICE, rules, local(12, 15, 30)) is None


def test_a_meeting_set_after_its_reminder_came_due_is_not_reminded():
    rules = notices.DEFAULT
    # Scheduled at 10:00 for 14:00 the same day: no morning reminder...
    talk = meeting(local(12, 14), link=CALL, set_at=local(12, 10))
    assert due(talk, OFFICE, rules, local(12, 10, 10)) is None
    # ...but the video reminder at 13:30 still goes.
    assert due(talk, OFFICE, rules, local(12, 13, 30)) is Reminder.SOON
    # Set at 13:40 for 14:00: neither.
    assert due(
        replace_ns(talk, updated_at=local(12, 13, 40)), OFFICE, rules, local(12, 13, 45)
    ) is (None)


def test_the_settings_move_the_reminders():
    rules = replace(notices.DEFAULT, before=timedelta(minutes=60))
    video = meeting(local(12, 14), link=CALL, day_for=local(12, 14))
    assert due(video, OFFICE, rules, local(12, 13)) is Reminder.SOON


# -- sending --------------------------------------------------------------------------


async def add_meeting(db_session, starts, link=CALL, location=None, title="Apresentação"):
    """A meeting of Casa Jardim's, its time set a day ago."""
    await db_session.execute(
        text(
            "INSERT INTO meetings "
            "(tenant_id, project_id, title, starts_at, ends_at, link, location, updated_at) "
            "SELECT tenant_id, id, :title, :starts, :ends, :link, :location, "
            f"now() - interval '1 day' FROM projects WHERE id = {CASA}"
        ),
        {
            "title": title,
            "starts": starts,
            "ends": starts + timedelta(hours=1),
            "link": link,
            "location": location,
        },
    )


async def reminded(db_session, title="Apresentação"):
    row = (
        await db_session.execute(
            text(
                "SELECT starts_at, reminded_day_for, reminded_soon_for FROM meetings "
                "WHERE title = :t"
            ),
            {"t": title},
        )
    ).first()
    return row[0], row[1], row[2]


@pytest.fixture
async def subscribed(app, db_session, owner):
    """Casa Jardim with a staff address (emailed outside production) and a
    WhatsApp number, WhatsApp on."""
    await switch_on(db_session)
    await add_recipients(db_session, STAFF)
    await add_number(db_session)


def reminders_in(outbox: Outbox) -> list:
    return [e for e in outbox.sent if e.subject.startswith("Lembrete")]


async def test_a_video_meeting_soon_is_reminded_by_email_and_whatsapp_once(
    app, db_session, subscribed
):
    outbox, phone = Outbox(), Phone()
    starts = datetime.now(UTC) + timedelta(minutes=20)
    await add_meeting(db_session, starts, location="Sala 2")
    report = await run(app, outbox, phone)
    assert (report.reminder_emails, report.reminder_messages) == (1, 1)
    # Its Drive folder can't be read here (no `folders`): reminders go regardless.
    assert report.failed
    [email] = reminders_in(outbox)
    hour = starts.astimezone(SAO_PAULO).strftime("%H:%M")
    assert email.subject == f"Lembrete: Apresentação, {hour}"
    assert f"A reunião “Apresentação” do projeto Casa Jardim começa às {hour}." in email.text
    assert "Local: Sala 2" in email.text
    assert f"Entrar na reunião: {CALL}" in email.text
    assert "List-Unsubscribe" in email.headers
    [message] = phone.to(CLIENT)
    assert message.template == REMINDER_VIDEO_TEMPLATE
    title, project, _office, when = message.params
    assert (title, project, when) == ("Apresentação", "Casa Jardim", hour)
    [(label, link)] = message.links
    assert label == "Entrar na reunião"
    assert message.text.endswith("responda SAIR.")
    # The day's reminder is past with it: both are noted, and nothing goes again.
    assert await reminded(db_session) == (starts, starts, starts)
    again = await run(app, outbox, phone)
    assert (again.reminder_emails, again.reminder_messages) == (0, 0)
    assert len(reminders_in(outbox)) == 1


async def test_the_join_button_opens_the_call_or_the_page(app, client, db_session, owner):
    tenant, _project = await casa_ids(db_session)
    await add_meeting(db_session, datetime.now(UTC) + timedelta(minutes=20))
    meeting_id = await db_session.scalar(
        text("SELECT id FROM meetings WHERE title = 'Apresentação'")
    )
    path = urlsplit(short_link(app.state.settings, "join", tenant, meeting_id)).path
    response = await client.get(path)
    assert (response.status_code, response.headers["location"]) == (302, CALL)
    assert response.headers["cache-control"] == "private, no-store"
    # Behind a password, the page, which asks for it and shows the link.
    await db_session.execute(
        text(f"UPDATE projects SET access_mode = 'password', password_hash = 'x' WHERE id = {CASA}")
    )
    response = await client.get(path)
    assert "/casa-jardim?utm_source=whatsapp&utm_medium=reminder" in response.headers["location"]
    # Over, or its link taken off: the page.
    await db_session.execute(text(f"UPDATE projects SET access_mode = 'public' WHERE id = {CASA}"))
    await db_session.execute(text("UPDATE meetings SET link = NULL WHERE title = 'Apresentação'"))
    response = await client.get(path)
    assert "/casa-jardim?" in response.headers["location"]
    # Deleted: the code names only the meeting, so it is not found.
    await db_session.execute(text("DELETE FROM meetings WHERE title = 'Apresentação'"))
    assert (await client.get(path)).status_code == 404
    # A meeting's code names the meeting: as a project's, it is nothing.
    page = urlsplit(short_link(app.state.settings, "page", tenant, meeting_id)).path
    assert (await client.get(page)).status_code == 404


async def test_behind_a_password_the_email_opens_the_page(app, db_session, subscribed):
    await db_session.execute(
        text(f"UPDATE projects SET access_mode = 'password', password_hash = 'x' WHERE id = {CASA}")
    )
    outbox = Outbox()
    await add_meeting(db_session, datetime.now(UTC) + timedelta(minutes=20))
    await run(app, outbox, Phone())
    [email] = reminders_in(outbox)
    assert CALL not in email.text and CALL not in email.html
    assert "/casa-jardim?utm_source=email&utm_medium=reminder" in email.text


async def test_the_days_reminder_opens_the_project(app, db_session, subscribed):
    outbox, phone = Outbox(), Phone()
    # Due now (the morning of, or the evening before), two hours on and no video.
    starts = datetime.now(UTC) + timedelta(hours=2)
    await add_meeting(db_session, starts, link=None)
    if datetime.now(UTC) < day_reminder_at(starts, OFFICE, notices.DEFAULT):
        pytest.skip("too early in the day for a reminder two hours ahead")
    await run(app, outbox, phone)
    [email] = reminders_in(outbox)
    hour = starts.astimezone(SAO_PAULO).strftime("%H:%M")
    day = (
        "hoje"
        if starts.astimezone(SAO_PAULO).date() == datetime.now(SAO_PAULO).date()
        else "amanhã"
    )
    assert email.subject == f"Lembrete: Apresentação, {day} às {hour}"
    assert "Abrir a página do projeto: http" in email.text
    [message] = phone.to(CLIENT)
    assert message.template == REMINDER_TEMPLATE
    assert message.params[3] == f"{day} às {hour}"
    assert [label for label, _ in message.links] == ["Abrir o projeto"]
    assert await reminded(db_session) == (starts, starts, None)


async def test_without_reminders_by_whatsapp_only_the_email_goes(app, db_session, subscribed):
    await db_session.execute(
        text("UPDATE notice_settings SET whatsapp_news = array_remove(whatsapp_news, 'reminders')")
    )
    outbox, phone = Outbox(), Phone()
    await add_meeting(db_session, datetime.now(UTC) + timedelta(minutes=20))
    await run(app, outbox, phone)
    assert len(reminders_in(outbox)) == 1
    assert phone.sent == []


async def test_a_number_that_replied_sair_gets_no_reminder(app, db_session, subscribed):
    await whatsapp_updates.opt_out(db_session, app.state.settings, CLIENT)
    phone = Phone()
    await add_meeting(db_session, datetime.now(UTC) + timedelta(minutes=20))
    await run(app, Outbox(), phone)
    assert phone.sent == []


async def test_a_failed_reminder_is_logged_and_not_tried_again(app, db_session, subscribed, caplog):
    outbox, phone = Outbox(), Phone()
    outbox.fail.add(STAFF)
    phone.fail[CLIENT] = None
    await add_meeting(db_session, datetime.now(UTC) + timedelta(minutes=20))
    with caplog.at_level(logging.ERROR):
        report = await run(app, outbox, phone)
    assert (report.reminder_emails, report.reminder_messages) == (0, 0)
    assert sum("reminders:" in r.message for r in caplog.records) == 2
    await run(app, outbox, phone)
    assert reminders_in(outbox) == [] and phone.sent == []


async def test_archived_projects_and_past_meetings_are_not_reminded(app, db_session, subscribed):
    outbox = Outbox()
    await add_meeting(db_session, datetime.now(UTC) - timedelta(minutes=5), title="Passada")
    await run(app, outbox, Phone())
    assert reminders_in(outbox) == []
    await add_meeting(db_session, datetime.now(UTC) + timedelta(minutes=20))
    await db_session.execute(
        text(f"UPDATE projects SET status = 'archived', archived_from = status WHERE id = {CASA}")
    )
    await run(app, outbox, Phone())
    assert reminders_in(outbox) == []


# -- the settings in the pass ---------------------------------------------------------


def test_a_batch_is_due_by_the_settings_quiet_period_and_hold():
    now = datetime(2026, 11, 10, 12, tzinfo=UTC)
    batch = NotificationBatch(
        first_event_at=now - timedelta(minutes=30), last_event_at=now - timedelta(minutes=10)
    )
    assert not digest.is_due(batch, now)
    assert digest.is_due(batch, now, replace(notices.DEFAULT, quiet=timedelta(minutes=10)))
    assert digest.is_due(batch, now, replace(notices.DEFAULT, hold=timedelta(minutes=30)))


async def test_the_pass_reads_the_settings(app, db_session, owner, folders):  # noqa: F811
    await db_session.execute(text("UPDATE notice_settings SET quiet_minutes = 5"))
    found = await notices.current(db_session)
    assert found.quiet == timedelta(minutes=5)
    outbox = Outbox()
    await add_recipients(db_session, STAFF)
    await run(app, outbox, None)  # the first scan only notes what is there
    await new_file(app, outbox, folders)
    await db_session.execute(
        text("UPDATE notification_batches SET last_event_at = last_event_at - interval '6 minutes'")
    )
    await run(app, outbox, None)
    assert len(outbox.sent) == 1  # with 45 minutes, it would still wait


def test_only_the_chosen_news_goes_by_whatsapp():
    summary = Summary(
        stages=[("02 Conceito", ["2 arquivos enviados", "marcada como concluída"])],
        news=[StageNews("Conceito", 2, "completed"), StageNews("Briefing", 1, None)],
        project_completed=True,
        meeting=("cleared", "Visita", None),
    )
    line = whatsapp_updates.news_line
    every = whatsapp_updates.only(summary, frozenset(WhatsAppNews))
    assert line(Locale.PT_BR, every) == line(Locale.PT_BR, summary)
    stages = whatsapp_updates.only(summary, frozenset({WhatsAppNews.STAGES}))
    assert line(Locale.PT_BR, stages) == "a etapa Conceito foi concluída"
    meetings = whatsapp_updates.only(summary, frozenset({WhatsAppNews.MEETINGS}))
    assert line(Locale.PT_BR, meetings) == 'a reunião "Visita" foi cancelada'
    assert line(Locale.PT_BR, whatsapp_updates.only(summary, frozenset())) == ""


async def test_an_update_with_none_of_the_chosen_news_goes_by_email_only(
    app,
    db_session,
    owner,
    folders,  # noqa: F811
):
    await db_session.execute(
        text("UPDATE notice_settings SET whatsapp_news = array_remove(whatsapp_news, 'files')")
    )
    await switch_on(db_session)
    await add_recipients(db_session, STAFF)
    await add_number(db_session)
    outbox, phone = Outbox(), Phone()
    await run(app, outbox, phone)
    await new_file(app, outbox, folders)
    await make_due(db_session)
    await run(app, outbox, phone)
    assert [e.subject for e in outbox.sent] == ["Atualizações em Casa Jardim"]
    assert phone.sent == []
    state = await db_session.scalar(text("SELECT state FROM notification_batches"))
    assert state == "sent"  # not held for a message that has nothing to say


# -- "Avisos" ---------------------------------------------------------------------------


def body(**changes) -> dict:
    return {
        "quiet_minutes": 45,
        "hold_minutes": 120,
        "reminder_morning": "08:30",
        "reminder_evening": "18:00",
        "reminder_before_minutes": 30,
        "ask_again_days": 3,
        "whatsapp_news": [news.value for news in WhatsAppNews],
    } | changes


async def test_operators_see_the_settings_as_the_code_had_them(client, operators):
    response = await client.get(URL, headers=UNIO)
    assert response.status_code == 401
    headers = await test_admin.sign_in(client)
    found = (await client.get(URL, headers=headers)).json()
    assert {k: v for k, v in found.items() if k in body()} == body()
    assert found["limits"]["quietMinutes"] == [5, 120]


async def test_an_operator_changes_the_settings_and_it_is_audited(
    client, actions_enabled, db_session
):
    headers = await test_admin.sign_in(client)
    changed = body(
        quiet_minutes=30,
        reminder_morning="09:00",
        whatsapp_news=["reminders", "files"],
    )
    response = await client.put(URL, json=changed, headers=headers)
    assert response.status_code == 200, response.text
    # In the list's own order, whatever order they came in.
    assert response.json()["whatsapp_news"] == ["files", "reminders"]
    found = await notices.current(db_session)
    assert (found.quiet, found.morning) == (timedelta(minutes=30), time(9))
    assert found.whatsapp == {WhatsAppNews.FILES, WhatsAppNews.REMINDERS}
    action = await db_session.scalar(
        text("SELECT action FROM operator_audit_events ORDER BY created_at DESC LIMIT 1")
    )
    assert action == "settings:notices"


@pytest.mark.parametrize(
    "changes",
    [
        {"quiet_minutes": 4},
        {"quiet_minutes": 121},
        {"hold_minutes": 40},  # shorter than the quiet period
        {"hold_minutes": 721},
        {"reminder_before_minutes": 0},
        {"ask_again_days": 31},
        {"reminder_evening": "08:00"},  # before the morning's
    ],
)
async def test_values_out_of_their_range_are_refused(client, actions_enabled, changes):
    headers = await test_admin.sign_in(client)
    response = await client.put(URL, json=body(**changes), headers=headers)
    assert (response.status_code, response.json()["error"]) == (422, "invalid_notice_settings")


async def test_only_the_operator_login_changes_the_settings(app, actions_enabled):
    """The app's login reads them; the operator's may change them (the self-test
    that the refusal is about rights, not the statement)."""
    from sqlalchemy.exc import ProgrammingError

    change = text("UPDATE notice_settings SET quiet_minutes = 50")
    async with app.state.sessionmaker() as db:
        assert (await notices.current(db)).quiet == timedelta(minutes=45)
        with pytest.raises(ProgrammingError):
            await db.execute(change)
    async with app.state.operator_sessionmaker() as db:
        await db.execute(change)
        await db.rollback()


async def test_the_database_keeps_the_values_in_range(db_session):
    from sqlalchemy.exc import IntegrityError

    for change in (
        "quiet_minutes = 200",
        "hold_minutes = 10",
        "reminder_evening = '07:00'",
        "whatsapp_news = ARRAY['gossip']",
    ):
        with pytest.raises(IntegrityError):
            await db_session.execute(text(f"UPDATE notice_settings SET {change}"))
        await db_session.rollback()
