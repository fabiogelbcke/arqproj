"""Client updates by WhatsApp (A44): numbers, what the messages say, who gets a
batch's message, signing up on the page, staff adding a number, and Meta's webhook."""

import hashlib
import hmac
import json
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from backend.notifications import whatsapp_updates
from backend.notifications.digest import StageNews, Summary
from backend.notifications.scan import run_maintenance
from backend.notifications.whatsapp import (
    NOT_ON_WHATSAPP,
    OutboxWhatsAppSender,
    WhatsAppError,
    WhatsAppMessage,
    canonical,
    may_receive,
    param,
    parse_phone,
    read_token,
    request_body,
    token,
)
from backend.settings import Environment, Settings
from backend.tenancy.models import Locale
from backend.tests import test_office
from backend.tests.test_client_emails import Outbox, as_production, make_due, new_file
from backend.tests.test_maintenance_scan import CASA, casa, folders  # noqa: F401
from backend.tests.test_office import ALINEA
from backend.tests.test_project_settings import change, project
from backend.web import attempts
from backend.web import whatsapp as webhook_module

owner = test_office.owner  # fixtures

pytestmark = pytest.mark.anyio

CLIENT = "5511987654321"
OTHER = "5521998765432"
SECRET = "meta-app-secret"


class Phone:
    """A sender that keeps the messages; a number in `fail` fails its next send."""

    def __init__(self):
        self.sent: list[WhatsAppMessage] = []
        self.fail: dict[str, int | None] = {}

    async def send(self, message: WhatsAppMessage) -> str:
        if message.to in self.fail:
            code = self.fail.pop(message.to)
            raise WhatsAppError("whatsapp 400: no", code)
        self.sent.append(message)
        return f"wamid.{len(self.sent)}"

    def to(self, phone):
        return [m for m in self.sent if m.to == phone]


@pytest.fixture
def phone(monkeypatch):
    box = Phone()
    monkeypatch.setattr(whatsapp_updates, "whatsapp_sender_for", lambda settings, http: box)
    monkeypatch.setattr(webhook_module, "whatsapp_sender_for", lambda settings, http: box)
    return box


async def switch_on(db_session, slug="alinea"):
    await db_session.execute(
        text("UPDATE tenants SET features = features || '{whatsapp_updates}' WHERE slug = :s"),
        {"s": slug},
    )


async def add_number(db_session, phone=CLIENT, status="subscribed", source="client", greeted=True):
    await db_session.execute(
        text(
            "INSERT INTO project_whatsapp_recipients "
            "(tenant_id, project_id, phone, status, source, greeted_at) "
            f"SELECT tenant_id, id, :phone, :status, :source, {'now()' if greeted else 'NULL'} "
            f"FROM projects WHERE id = {CASA}"
        ),
        {"phone": phone, "status": status, "source": source},
    )


async def number(db_session, phone=CLIENT):
    row = (
        await db_session.execute(
            text(
                "SELECT status, source, greeted_at FROM project_whatsapp_recipients "
                "WHERE phone = :p"
            ),
            {"p": phone},
        )
    ).first()
    return tuple(row) if row else None


async def run(app, outbox, phone_box):
    return await run_maintenance(
        app.state.sessionmaker, app.state.settings, None, outbox, whatsapp=phone_box
    )


# -- numbers --------------------------------------------------------------------------


# The same cases as the staff app's rule (frontend/src/ui/phone.test.ts).
PHONES = json.loads(
    (Path(__file__).parents[2] / "frontend/src/ui/phone.cases.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize(("typed", "stored"), PHONES["valid"])
def test_numbers_are_kept_in_international_digits(typed, stored):
    assert parse_phone(typed) == stored


@pytest.mark.parametrize("typed", PHONES["invalid"])
def test_what_isnt_a_mobile_is_refused(typed):
    assert parse_phone(typed) is None


def test_a_brazilian_number_meta_reports_without_its_9_is_ours():
    assert canonical("551187654321") == CLIENT
    assert canonical(CLIENT) == CLIENT
    assert canonical("551134567890") == "551134567890"  # a landline (3…) is left alone
    assert canonical("351912345678") == "351912345678"


def test_a_token_names_its_office_and_number_and_cant_be_made_up():
    settings = Settings()
    tenant, recipient = uuid.uuid4(), uuid.uuid4()
    value = token(settings, "yes", tenant, recipient)
    assert len(value) <= 128  # Meta limits a button's payload
    found = read_token(settings, value)
    assert (found.action, found.tenant_id, found.recipient_id) == ("yes", tenant, recipient)
    assert read_token(settings, value.replace("yes.", "no.", 1)) is None  # another answer
    assert read_token(settings, value[:-1] + ("0" if value[-1] != "0" else "1")) is None
    other = Settings(app_secret="another-secret-of-at-least-thirty-two-chars")
    assert read_token(other, value) is None
    assert read_token(settings, "nonsense") is None


def test_a_templates_parts_have_no_line_breaks_and_a_bounded_length():
    assert param("Casa\nJardim \t  2") == "Casa Jardim 2"
    long = param("x" * 2000)
    assert len(long) <= 600 and long.endswith("…")


def test_what_meta_is_sent():
    template = WhatsAppMessage(
        to=CLIENT,
        text="…",
        template="unio_convite",
        params=("Alinea", "Casa Jardim"),
        buttons=("yes-token", "no-token"),
        callback="cb",
    )
    body = request_body(template)
    assert body["to"] == CLIENT and body["type"] == "template"
    assert body["template"]["name"] == "unio_convite"
    assert body["template"]["language"] == {"code": "pt_BR"}
    [parts, yes, no] = body["template"]["components"]
    assert [p["text"] for p in parts["parameters"]] == ["Alinea", "Casa Jardim"]
    assert (yes["index"], yes["parameters"][0]["payload"]) == ("0", "yes-token")
    assert (no["index"], no["parameters"][0]["payload"]) == ("1", "no-token")
    assert body["biz_opaque_callback_data"] == "cb"
    reply = request_body(WhatsAppMessage(to=CLIENT, text="Pronto"))
    assert reply["type"] == "text" and reply["text"] == {"body": "Pronto"}


def test_outside_production_only_test_numbers_get_real_messages():
    local = Settings()
    assert may_receive(local, CLIENT)  # written to the outbox: nothing leaves the machine
    staging = Settings(
        environment=Environment.LOCAL, whatsapp_token="t", whatsapp_test_numbers="+55 11 98765-4321"
    )
    assert may_receive(staging, CLIENT)
    assert not may_receive(staging, OTHER)
    production = staging.model_copy(update={"environment": Environment.PRODUCTION})
    assert may_receive(production, OTHER)


async def test_the_outbox_writes_the_message_as_the_client_reads_it(tmp_path):
    sender = OutboxWhatsAppSender(tmp_path)
    await sender.send(WhatsAppMessage(to=CLIENT, text="Olá!", template="unio_boas_vindas"))
    [written] = tmp_path.iterdir()
    assert CLIENT in written.name
    content = written.read_text()
    assert "Olá!" in content and "unio_boas_vindas" in content


# -- what an update says --------------------------------------------------------------

PT = Locale.PT_BR
WHEN = datetime(2026, 11, 12, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


def news(*stages, project_completed=False, meeting=None):
    return whatsapp_updates.news_line(
        PT,
        Summary(news=list(stages), project_completed=project_completed, meeting=meeting),
    )


# The cases of the texts' review document, one by one.
@pytest.mark.parametrize(
    ("summary", "said"),
    [
        ([StageNews("Estudo Preliminar", 1, None)], "1 arquivo novo na etapa Estudo Preliminar"),
        ([StageNews("Estudo Preliminar", 3, None)], "3 arquivos novos na etapa Estudo Preliminar"),
        (
            [StageNews("Estudo Preliminar", 0, "completed")],
            "a etapa Estudo Preliminar foi concluída",
        ),
        ([StageNews("Anteprojeto", 0, "reopened")], "a etapa Anteprojeto foi reaberta"),
        (
            [StageNews("Estudo Preliminar", 3, "completed")],
            "3 arquivos novos na etapa Estudo Preliminar, que foi concluída",
        ),
        (
            [StageNews("Anteprojeto", 1, "reopened")],
            "1 arquivo novo na etapa Anteprojeto, que foi reaberta",
        ),
        (
            [StageNews("Estudo Preliminar", 3, "completed"), StageNews("Anteprojeto", 1, None)],
            "Estudo Preliminar: 3 arquivos novos, etapa concluída; Anteprojeto: 1 arquivo novo",
        ),
        (
            [
                StageNews("Estudo Preliminar", 3, None),
                StageNews("Anteprojeto", 0, "completed"),
                StageNews("Projeto Legal", 2, None),
                StageNews("Projeto Executivo", 1, None),
                StageNews("Detalhamento", 0, "completed"),
            ],
            "Estudo Preliminar: 3 arquivos novos; Anteprojeto: etapa concluída; "
            "Projeto Legal: 2 arquivos novos; e mais 2 etapas",
        ),
    ],
)
def test_stage_news_on_one_line(summary, said):
    assert news(*summary) == said


def test_one_more_stage_is_said_in_the_singular():
    stages = [StageNews(f"Etapa {i}", 1, None) for i in range(4)]
    assert news(*stages).endswith("; e mais 1 etapa")


def test_the_project_and_meetings_follow_the_stages():
    assert news(project_completed=True) == "o projeto foi concluído"
    assert (
        news(StageNews("Acompanhamento de Obra", 0, "completed"), project_completed=True)
        == "a etapa Acompanhamento de Obra foi concluída; o projeto foi concluído"
    )
    assert (
        news(meeting=("scheduled", "Apresentação do anteprojeto", WHEN))
        == "reunião marcada: Apresentação do anteprojeto, 12/11 às 14h"
    )
    assert (
        news(meeting=("changed", "Apresentação", WHEN.replace(hour=10, minute=30)))
        == "reunião alterada: Apresentação, agora 12/11 às 10h30"
    )
    assert (
        news(meeting=("cleared", "Apresentação", None)) == 'a reunião "Apresentação" foi cancelada'
    )
    assert (
        news(StageNews("Anteprojeto", 2, None), meeting=("scheduled", "Apresentação", WHEN))
        == "2 arquivos novos na etapa Anteprojeto; reunião marcada: Apresentação, 12/11 às 14h"
    )


def test_files_in_a_stage_removed_meanwhile_are_counted_without_a_stage():
    """Never an empty line: Meta refuses an empty part, and each number would fail."""
    assert news(StageNews(None, 2, None)) == "2 arquivos novos"
    assert news(StageNews("Anteprojeto", 0, "completed"), StageNews(None, 1, None)) == (
        "a etapa Anteprojeto foi concluída; 1 arquivo novo"
    )


# -- a batch's message ----------------------------------------------------------------


@pytest.fixture
async def subscribed(app, db_session, owner, folders, phone):  # noqa: F811
    """Casa Jardim scanned once, WhatsApp on for Alinea, one subscribed number."""
    await switch_on(db_session)
    await add_number(db_session)
    await run(app, Outbox(), phone)
    return folders


async def test_a_due_batch_goes_to_each_subscribed_number(app, db_session, subscribed, phone):
    outbox = Outbox()
    await new_file(app, outbox, subscribed, "Croqui.pdf")
    await new_file(app, outbox, subscribed, "Fachada.pdf")
    await run(app, outbox, phone)
    assert phone.sent == []  # quiet period, as the email
    await make_due(db_session)
    await run(app, outbox, phone)
    [message] = phone.to(CLIENT)
    assert message.template == "unio_atualizacao"
    project_name, office, line, link = message.params
    assert project_name == "Casa Jardim" and line == "2 arquivos novos na etapa Levantamento"
    assert "Croqui" not in message.text  # files counted, never named
    assert link.endswith("/casa-jardim?utm_source=whatsapp&utm_medium=update")
    assert "responda SAIR" in message.text
    # Sent once: another pass sends nothing more.
    await run(app, outbox, phone)
    assert len(phone.to(CLIENT)) == 1


async def test_whatsapp_alone_is_enough_to_send_a_batch(app, db_session, subscribed, phone):
    """No client email at all: the batch still goes, to the number."""
    outbox = Outbox()
    await new_file(app, outbox, subscribed)
    await make_due(db_session)
    await run(app, outbox, phone)
    assert outbox.sent == [] and len(phone.to(CLIENT)) == 1


@pytest.mark.parametrize("status", ["invited", "declined", "unreachable"])
async def test_only_subscribed_numbers_get_updates(app, db_session, subscribed, phone, status):
    await add_number(db_session, OTHER, status=status, source="staff")
    outbox = Outbox()
    await new_file(app, outbox, subscribed)
    await make_due(db_session)
    await run(app, outbox, phone)
    assert phone.to(OTHER) == [] and len(phone.to(CLIENT)) == 1


async def test_a_number_that_replied_sair_gets_nothing(app, db_session, subscribed, phone):
    await db_session.execute(
        text("INSERT INTO whatsapp_opt_outs (phone_hash) VALUES (:h)"),
        {"h": whatsapp_updates.opt_out_hash(app.state.settings, CLIENT)},
    )
    outbox = Outbox()
    await new_file(app, outbox, subscribed)
    await make_due(db_session)
    await run(app, outbox, phone)
    assert phone.sent == []


async def test_an_office_without_whatsapp_sends_none(app, db_session, subscribed, phone):
    await db_session.execute(text("UPDATE tenants SET features = '{}'"))
    outbox = Outbox()
    await new_file(app, outbox, subscribed)
    await make_due(db_session)
    await run(app, outbox, phone)
    assert phone.sent == []


async def test_a_failed_message_is_retried_and_never_sent_twice(app, db_session, subscribed, phone):
    await add_number(db_session, OTHER)
    outbox = Outbox()
    await new_file(app, outbox, subscribed)
    await make_due(db_session)
    phone.fail[OTHER] = None
    await run(app, outbox, phone)
    assert len(phone.to(CLIENT)) == 1 and phone.to(OTHER) == []
    sending = await db_session.scalar(text("SELECT state FROM notification_batches"))
    assert sending == "sending"  # kept for the retry
    await run(app, outbox, phone)
    assert len(phone.to(CLIENT)) == 1 and len(phone.to(OTHER)) == 1
    assert await db_session.scalar(text("SELECT state FROM notification_batches")) == "sent"


async def test_without_whatsapp_set_up_the_email_isnt_held_for_it(
    app, db_session, subscribed, monkeypatch
):
    """Deployed without Meta's settings there is no sender: the batch goes by email
    and is done, rather than waiting on messages that can't go."""
    await db_session.execute(
        text(
            "INSERT INTO project_recipients (tenant_id, project_id, email) "
            f"SELECT tenant_id, id, 'cliente@exemplo.com.br' FROM projects WHERE id = {CASA}"
        )
    )
    as_production(monkeypatch)  # the client's address may be emailed
    outbox = Outbox()
    await new_file(app, outbox, subscribed)
    await make_due(db_session)
    await run(app, outbox, None)
    assert len(outbox.sent) == 1
    assert await db_session.scalar(text("SELECT state FROM notification_batches")) == "sent"
    assert await db_session.scalar(text("SELECT count(*) FROM whatsapp_deliveries")) == 0


async def test_outside_production_only_test_numbers_get_a_batch(
    app, db_session, subscribed, phone, monkeypatch
):
    monkeypatch.setattr(app.state.settings, "whatsapp_token", "token")
    monkeypatch.setattr(app.state.settings, "whatsapp_test_numbers", OTHER)
    await add_number(db_session, OTHER)
    outbox = Outbox()
    await new_file(app, outbox, subscribed)
    await make_due(db_session)
    await run(app, outbox, phone)
    assert phone.to(CLIENT) == [] and len(phone.to(OTHER)) == 1


async def test_a_greeting_that_didnt_go_is_sent_by_the_pass(app, db_session, subscribed, phone):
    await add_number(db_session, OTHER, greeted=False)
    await db_session.execute(
        text("UPDATE project_whatsapp_recipients SET created_at = now() - interval '1 hour'")
    )
    report = await run(app, Outbox(), phone)
    [welcome] = phone.to(OTHER)
    assert welcome.template == "unio_boas_vindas" and report.greeted == 1
    assert (await number(db_session, OTHER))[2] is not None
    await run(app, Outbox(), phone)
    assert len(phone.to(OTHER)) == 1  # once


async def test_the_pass_leaves_a_just_added_number_to_its_request(
    app, db_session, subscribed, phone
):
    await add_number(db_session, OTHER, greeted=False)
    await run(app, Outbox(), phone)
    assert phone.to(OTHER) == []


async def test_a_number_without_whatsapp_is_marked_unreachable(app, db_session, subscribed, phone):
    await add_number(db_session, OTHER, greeted=False)
    await db_session.execute(
        text("UPDATE project_whatsapp_recipients SET created_at = now() - interval '1 hour'")
    )
    phone.fail[OTHER] = NOT_ON_WHATSAPP
    await run(app, Outbox(), phone)
    assert (await number(db_session, OTHER))[0] == "unreachable"


# -- the client signs up on the page --------------------------------------------------


@pytest.fixture
async def visitor(client, db_session, owner, phone):
    client.cookies.clear()
    attempts.reset()
    await switch_on(db_session)
    yield phone
    attempts.reset()


async def sign_up(client, phone_number, slug="casa-jardim"):
    return await client.post(
        f"/api/pages/{slug}/whatsapp", json={"phone": phone_number}, headers=ALINEA
    )


async def test_a_client_signs_up_and_is_welcomed(client, db_session, visitor):
    response = await sign_up(client, "(11) 98765-4321")
    assert response.status_code == 204, response.text
    status, source, greeted = await number(db_session)
    assert (status, source) == ("subscribed", "client") and greeted is not None
    [welcome] = visitor.to(CLIENT)
    assert welcome.template == "unio_boas_vindas"
    assert welcome.params[0] == "Casa Jardim"
    assert "responda SAIR" in welcome.text


async def test_the_page_says_whether_the_office_has_whatsapp(client, db_session, owner):
    client.cookies.clear()
    page = await client.get("/api/pages/casa-jardim", headers=ALINEA)
    assert page.json()["whatsapp"] is False
    await switch_on(db_session)
    page = await client.get("/api/pages/casa-jardim", headers=ALINEA)
    assert page.json()["whatsapp"] is True


async def test_signing_up_needs_the_feature(client, db_session, owner, phone):
    client.cookies.clear()
    response = await sign_up(client, CLIENT)
    assert response.status_code == 404 and response.json()["error"] == "feature_off"


async def test_a_number_that_isnt_a_mobile_is_refused(client, db_session, visitor):
    response = await sign_up(client, "(11) 3456-7890")
    assert response.status_code == 422 and response.json()["error"] == "invalid_phone"
    assert await number(db_session, "551134567890") is None


async def test_signing_up_twice_welcomes_once(client, db_session, visitor):
    await sign_up(client, CLIENT)
    await sign_up(client, "+55 11 98765-4321")
    assert len(visitor.to(CLIENT)) == 1


async def test_signing_up_again_lifts_a_sair_and_a_no(client, app, db_session, visitor):
    """The client's own choice: a SAIR or "Não quero" before doesn't stop it."""
    await add_number(db_session, status="declined", source="staff")
    await whatsapp_updates.opt_out(db_session, app.state.settings, CLIENT)
    response = await sign_up(client, CLIENT)
    assert response.status_code == 204
    assert (await number(db_session))[:2] == ("subscribed", "client")
    assert not await whatsapp_updates.opted_out(db_session, app.state.settings, {CLIENT})
    assert len(visitor.to(CLIENT)) == 1


async def test_an_archived_project_takes_no_numbers(client, db_session, visitor):
    await db_session.execute(
        text(f"UPDATE projects SET archived_from = status, status = 'archived' WHERE id = {CASA}")
    )
    response = await sign_up(client, CLIENT)
    assert response.status_code == 409 and response.json()["error"] == "project_archived"


# -- staff add a number ---------------------------------------------------------------


def numbers(found):
    return [(n["phone"], n["state"]) for n in found["whatsapp"]]


async def test_staff_add_a_number_and_the_client_is_asked(client, app, db_session, owner, phone):
    await switch_on(db_session)
    found = await project(client)
    response = await change(client, owner, found, whatsapp=["(11) 98765-4321", CLIENT])
    assert response.status_code == 200, response.text
    assert numbers(response.json()) == [(CLIENT, "invited")]
    [question] = phone.to(CLIENT)
    assert question.template == "unio_convite"
    yes, no = (read_token(app.state.settings, b) for b in question.buttons)
    assert (yes.action, no.action) == ("yes", "no")
    assert yes.recipient_id == no.recipient_id


async def test_staff_numbers_need_the_feature(client, db_session, owner, phone):
    response = await change(client, owner, await project(client), whatsapp=[CLIENT])
    assert response.status_code == 409 and response.json()["error"] == "feature_off"
    assert phone.sent == []


async def test_a_number_that_said_no_stays_and_isnt_asked_again(client, db_session, owner, phone):
    await switch_on(db_session)
    found = (await change(client, owner, await project(client), whatsapp=[CLIENT])).json()
    await db_session.execute(text("UPDATE project_whatsapp_recipients SET status = 'declined'"))
    removed = (await change(client, owner, found, whatsapp=[])).json()
    assert numbers(removed) == [(CLIENT, "declined")]  # still listed, still off
    again = (await change(client, owner, removed, whatsapp=[CLIENT])).json()
    assert numbers(again) == [(CLIENT, "declined")]
    assert len(phone.to(CLIENT)) == 1  # the first question only


async def test_staff_cant_add_a_number_that_replied_sair(client, app, db_session, owner, phone):
    await switch_on(db_session)
    await whatsapp_updates.opt_out(db_session, app.state.settings, CLIENT)
    response = await change(client, owner, await project(client), whatsapp=[CLIENT])
    assert response.status_code == 409 and response.json()["error"] == "whatsapp_refused"
    assert phone.sent == []


async def test_a_number_that_replied_sair_shows_as_stopped(client, app, db_session, owner, phone):
    await switch_on(db_session)
    found = (await change(client, owner, await project(client), whatsapp=[CLIENT])).json()
    await whatsapp_updates.opt_out(db_session, app.state.settings, CLIENT)
    assert numbers(await project(client)) == [(CLIENT, "stopped")]
    # Left out of the list, it is removed (the SAIR stays, for every project).
    assert numbers((await change(client, owner, found, whatsapp=[])).json()) == []


async def test_a_full_list_can_swap_a_number(client, db_session, owner, phone):
    """The limit counts the list as saved, not numbers this save removes."""
    await switch_on(db_session)
    full = [f"55119{n:08d}" for n in range(10000000, 10000020)]
    found = (await change(client, owner, await project(client), whatsapp=full)).json()
    assert len(found["whatsapp"]) == 20
    swapped = await change(client, owner, found, whatsapp=[*full[1:], CLIENT])
    assert swapped.status_code == 200, swapped.text
    # One that said no stays listed (never asked again), so it still counts.
    await db_session.execute(
        text("UPDATE project_whatsapp_recipients SET status = 'declined' WHERE phone = :p"),
        {"p": full[1]},
    )
    too_many = await change(client, owner, swapped.json(), whatsapp=[*full[2:], CLIENT, OTHER])
    assert too_many.status_code == 409 and too_many.json()["error"] == "whatsapp_full"


async def test_staff_numbers_are_checked(client, db_session, owner, phone):
    await switch_on(db_session)
    response = await change(client, owner, await project(client), whatsapp=["1234"])
    assert response.status_code == 422 and response.json()["error"] == "invalid_phone"


# -- Meta's webhook -------------------------------------------------------------------


@pytest.fixture
def meta(app, monkeypatch, phone):
    monkeypatch.setattr(app.state.settings, "whatsapp_app_secret", SECRET)
    monkeypatch.setattr(app.state.settings, "whatsapp_verify_token", "verify-me")
    webhook_module._auto_replied.clear()
    return phone


def signed(payload: dict) -> tuple[bytes, dict]:
    body = json.dumps(payload).encode()
    mac = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return body, {"x-hub-signature-256": f"sha256={mac}", "content-type": "application/json"}


def incoming(message: dict | None = None, status: dict | None = None) -> dict:
    value = {"messages": [message]} if message else {"statuses": [status]}
    return {"entry": [{"changes": [{"value": value}]}]}


async def post(client, payload: dict):
    body, headers = signed(payload)
    return await client.post("/api/whatsapp/webhook", content=body, headers=headers)


async def test_meta_checks_the_address_with_our_verify_token(client, meta):
    query = "hub.mode=subscribe&hub.verify_token=verify-me&hub.challenge=12345"
    response = await client.get(f"/api/whatsapp/webhook?{query}")
    assert response.status_code == 200 and response.text == "12345"
    wrong = query.replace("verify-me", "guess")
    assert (await client.get(f"/api/whatsapp/webhook?{wrong}")).status_code == 404


async def test_an_unsigned_request_is_not_heard(client, db_session, meta):
    payload = incoming({"from": CLIENT, "type": "text", "text": {"body": "SAIR"}})
    body, _ = signed(payload)
    response = await client.post(
        "/api/whatsapp/webhook", content=body, headers={"x-hub-signature-256": "sha256=00"}
    )
    assert response.status_code == 404
    assert await db_session.scalar(text("SELECT count(*) FROM whatsapp_opt_outs")) == 0


async def test_sair_stops_every_project_and_says_so(client, app, db_session, meta):
    response = await post(
        client, incoming({"from": CLIENT, "type": "text", "text": {"body": " Sair! "}})
    )
    assert response.status_code == 200
    assert await whatsapp_updates.opted_out(db_session, app.state.settings, {CLIENT})
    [reply] = meta.to(CLIENT)
    assert reply.template is None and "não vai mais receber" in reply.text
    # Only a hash is kept, never the number.
    kept = await db_session.scalar(text("SELECT phone_hash FROM whatsapp_opt_outs"))
    assert CLIENT not in kept


@pytest.mark.parametrize("word", ["PARAR", "cancelar", "Stop", "pare"])
async def test_other_ways_of_saying_stop(client, app, db_session, meta, word):
    await post(client, incoming({"from": CLIENT, "type": "text", "text": {"body": word}}))
    assert await whatsapp_updates.opted_out(db_session, app.state.settings, {CLIENT})


async def test_a_number_reported_without_its_9_is_stopped_as_stored(client, app, db_session, meta):
    await post(client, incoming({"from": "551187654321", "type": "text", "text": {"body": "SAIR"}}))
    assert await whatsapp_updates.opted_out(db_session, app.state.settings, {CLIENT})


async def test_anything_else_gets_one_automatic_reply_a_day(client, db_session, meta):
    for words in ("Obrigado!", "Pode me ligar?"):
        await post(client, incoming({"from": CLIENT, "type": "text", "text": {"body": words}}))
    [reply] = meta.to(CLIENT)
    assert "avisos automáticos" in reply.text
    assert await db_session.scalar(text("SELECT count(*) FROM whatsapp_opt_outs")) == 0


async def asked(client, db_session, owner, phone_box):
    await switch_on(db_session)
    await change(client, owner, await project(client), whatsapp=[CLIENT])
    return phone_box.to(CLIENT)[0]


async def test_quero_receber_subscribes_the_number(client, db_session, owner, meta):
    question = await asked(client, db_session, owner, meta)
    response = await post(
        client,
        incoming({"from": CLIENT, "type": "button", "button": {"payload": question.buttons[0]}}),
    )
    assert response.status_code == 200
    assert (await number(db_session))[0] == "subscribed"
    assert "Pronto!" in meta.to(CLIENT)[-1].text and "Casa Jardim" in meta.to(CLIENT)[-1].text


async def test_nao_quero_declines_it(client, db_session, owner, meta):
    question = await asked(client, db_session, owner, meta)
    await post(
        client,
        incoming({"from": CLIENT, "type": "button", "button": {"payload": question.buttons[1]}}),
    )
    assert (await number(db_session))[0] == "declined"
    assert "Tudo bem" in meta.to(CLIENT)[-1].text


async def test_another_numbers_button_changes_nothing(client, db_session, owner, meta):
    """A forwarded question tapped from another phone doesn't answer for the client."""
    question = await asked(client, db_session, owner, meta)
    await post(
        client,
        incoming({"from": OTHER, "type": "button", "button": {"payload": question.buttons[0]}}),
    )
    assert (await number(db_session))[0] == "invited"


async def test_a_message_meta_couldnt_deliver_marks_the_number(
    client, app, db_session, owner, meta
):
    question = await asked(client, db_session, owner, meta)
    status = {
        "status": "failed",
        "recipient_id": CLIENT,
        "biz_opaque_callback_data": question.callback,
        "errors": [{"code": NOT_ON_WHATSAPP, "title": "Not a WhatsApp user"}],
    }
    assert (await post(client, incoming(status=status))).status_code == 200
    assert (await number(db_session))[0] == "unreachable"


async def test_another_failure_leaves_the_number_alone(client, db_session, owner, meta):
    question = await asked(client, db_session, owner, meta)
    status = {
        "status": "failed",
        "biz_opaque_callback_data": question.callback,
        "errors": [{"code": 131047, "title": "Re-engagement message"}],
    }
    await post(client, incoming(status=status))
    assert (await number(db_session))[0] == "invited"
