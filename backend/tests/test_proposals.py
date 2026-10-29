"""Proposals (A40): the "Proposta" status, the generator, versions, the PDF and
what a client sees while a project is a proposal."""

import re
import zlib
from datetime import date

import pytest
from sqlalchemy import text

from backend.identity.models import Role
from backend.proposals.content import ProposalContent, in_words, money
from backend.proposals.pdf import render
from backend.tenancy.models import Locale
from backend.tests import test_office
from backend.tests.test_office import ALINEA, NORTE, PNG, sign_in_as
from backend.tests.test_projects_api import create

owner = test_office.owner  # fixtures

pytestmark = pytest.mark.anyio


def pdf_text(pdf: bytes) -> str:
    """The text a PDF draws, line after line joined by spaces, from its
    (compressed) content streams."""
    shown = []
    for stream in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S):
        try:
            commands = zlib.decompress(stream).decode("cp1252", "replace")
        except zlib.error:
            continue
        # Each string drawn, escapes undone: "(Prezado\(a\))" -> "Prezado(a)".
        for string in re.findall(r"\(((?:\\.|[^\\)])*)\) ?Tj", commands):
            shown.append(re.sub(r"\\(.)", r"\1", string))
    return re.sub(r"\s+", " ", " ".join(shown))


def content(**changes):
    return {
        "client_name": "Helena Duarte Ramos",
        "city": "Joinville",
        "date": "2026-10-28",
        "intro": "Conforme solicitação, segue nossa proposta.",
        "services": [
            {"title": "Briefing", "description": "Conversas sobre o programa."},
            {"title": "Imagens renderizadas", "description": "Perspectivas da fachada."},
        ],
        "fee": 2_900_000,
        "payments": [{"amount": 1_450_000, "when": "no aceite da proposta"}] * 2,
        "not_included": ["Projeto estrutural", "  ", "Projeto de paisagismo"],
        "notes": "As despesas com RRT correm por conta do contratante.",
        "signatory": "Arq. Laura Mendes",
        "address": "Rua das Palmeiras, 120 - Centro",
        "phone": "(47) 3000-0000",
        "email": "contato@alinea.example",
    } | changes


async def casa_jardim(client):
    found = [p for p in (await client.get("/api/projects", headers=ALINEA)).json()]
    return next(p for p in found if p["slug"] == "casa-jardim")


async def make_proposal(db_session, name="Casa Jardim"):
    await db_session.execute(
        text("UPDATE projects SET status = 'proposal' WHERE name = :n"), {"n": name}
    )


async def save(client, headers, project_id, **changes):
    return await client.post(
        f"/api/projects/{project_id}/proposals", json=content(**changes), headers=headers
    )


# -- the status ---------------------------------------------------------------------


async def test_a_project_created_as_a_proposal_shows_only_its_proposal(client, owner):
    created = await create(client, owner, proposal=True)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "proposal"
    # Its folders are made as for any project (A07 unchanged).
    assert created.json()["stage_count"] > 0
    page = (await client.get("/api/pages/casa-do-lago", headers=ALINEA)).json()
    assert page["in_proposal"] is True
    assert (page["stages"], page["details"], page["description"]) == ([], [], "")
    assert page["next_meeting"] is None and page["proposal"] is None  # none saved yet


async def test_a_project_created_without_the_option_is_active_as_before(client, owner):
    created = await create(client, owner)
    assert created.json()["status"] == "active"
    page = (await client.get("/api/pages/casa-do-lago", headers=ALINEA)).json()
    assert page["in_proposal"] is False and page["proposal_url"] is None


async def test_while_a_proposal_a_client_reaches_nothing_but_the_page_and_its_pdf(
    client, db_session, owner
):
    found = await casa_jardim(client)
    assert (await save(client, owner, found["id"])).status_code == 201
    await make_proposal(db_session)
    await client.delete("/api/session", headers=owner)  # now a client
    assert (await client.get("/api/pages/casa-jardim", headers=ALINEA)).status_code == 200
    assert (
        await client.get("/api/pages/casa-jardim/proposal.pdf", headers=ALINEA)
    ).status_code == 200
    for path in ("files", "meeting.ics", "updates"):
        response = await client.get(f"/api/pages/casa-jardim/{path}", headers=ALINEA)
        assert response.status_code == 404, path
    subscribe = await client.post(
        "/api/pages/casa-jardim/subscribe", json={"email": "a@b.example"}, headers=ALINEA
    )
    assert subscribe.status_code == 404


async def test_staff_still_reach_a_proposals_files(client, db_session, owner):
    await make_proposal(db_session)
    assert (await client.get("/api/pages/casa-jardim/files", headers=ALINEA)).status_code == 200


async def test_accepting_makes_the_project_active_and_keeps_a_link_to_the_proposal(
    client, db_session, owner
):
    found = await casa_jardim(client)
    await save(client, owner, found["id"])
    await make_proposal(db_session)
    found = await casa_jardim(client)
    accepted = await client.post(
        f"/api/projects/{found['id']}/accept-proposal",
        json={"row_version": found["row_version"]},
        headers=owner,
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "active"
    page = (await client.get("/api/pages/casa-jardim", headers=ALINEA)).json()
    assert page["in_proposal"] is False and page["stages"]
    assert page["proposal"] is None
    assert page["proposal_url"].startswith("/api/pages/casa-jardim/proposal.pdf?v=1")
    # Accepting again changes nothing.
    again = await client.post(
        f"/api/projects/{found['id']}/accept-proposal",
        json={"row_version": accepted.json()["row_version"]},
        headers=owner,
    )
    assert (again.status_code, again.json()["status"]) == (200, "active")


async def test_accepting_a_proposal_someone_changed_meanwhile_is_refused(client, db_session, owner):
    await make_proposal(db_session)
    found = await casa_jardim(client)
    stale = await client.post(
        f"/api/projects/{found['id']}/accept-proposal",
        json={"row_version": found["row_version"] - 1},
        headers=owner,
    )
    assert (stale.status_code, stale.json()["error"]) == (409, "project_changed")


async def test_only_a_proposal_or_an_active_project_can_be_accepted(client, db_session, owner):
    await db_session.execute(text("UPDATE projects SET status = 'completed'"))
    found = await casa_jardim(client)
    refused = await client.post(
        f"/api/projects/{found['id']}/accept-proposal",
        json={"row_version": found["row_version"]},
        headers=owner,
    )
    assert (refused.status_code, refused.json()["error"]) == (422, "invalid_status_change")


async def test_an_archived_proposal_still_shows_the_proposal_and_restores_to_one(
    client, db_session, owner
):
    await make_proposal(db_session)
    found = await casa_jardim(client)
    archived = await client.patch(
        f"/api/projects/{found['id']}",
        json={"row_version": found["row_version"], "status": "archived"},
        headers=owner,
    )
    assert archived.status_code == 200, archived.text
    page = (await client.get("/api/pages/casa-jardim", headers=ALINEA)).json()
    assert page["in_proposal"] is True
    restored = await client.patch(
        f"/api/projects/{found['id']}",
        json={"row_version": archived.json()["row_version"], "status": "proposal"},
        headers=owner,
    )
    assert restored.json()["status"] == "proposal"


# -- the generator ------------------------------------------------------------------


async def test_a_first_proposal_starts_from_the_built_in_texts_and_the_offices_details(
    client, owner
):
    await client.patch(
        "/api/office",
        json={
            "city": "Joinville",
            "signatory": "Arq. Laura Mendes",
            "contact_email": "a@b.example",
        },
        headers=owner,
    )
    found = await casa_jardim(client)
    start = (await client.get(f"/api/projects/{found['id']}/proposal", headers=owner)).json()
    assert start["versions"] == []
    first = start["start"]
    assert first["client_name"] == found["client_name"]
    assert (first["city"], first["signatory"], first["email"]) == (
        "Joinville",
        "Arq. Laura Mendes",
        "a@b.example",
    )
    assert first["fee"] is None
    assert [s["title"] for s in first["services"]][:2] == ["Briefing", "Anteprojeto"]
    assert first["intro"] == start["default_intro"] and first["notes"] == start["default_notes"]


async def test_a_saved_proposal_is_where_the_generator_starts_next(client, owner):
    found = await casa_jardim(client)
    await save(client, owner, found["id"], fee=1_000_000)
    start = (await client.get(f"/api/projects/{found['id']}/proposal", headers=owner)).json()
    assert start["start"]["fee"] == 1_000_000
    assert [v["version"] for v in start["versions"]] == [1]
    assert start["versions"][0]["created_by"] == "Ana"


async def test_each_save_is_a_new_version_and_the_client_sees_the_latest(client, owner):
    found = await casa_jardim(client)
    first = await save(client, owner, found["id"], fee=1_000_000)
    second = await save(client, owner, found["id"], fee=2_000_000)
    assert (first.json()["version"], second.json()["version"]) == (1, 2)
    latest = await client.get("/api/pages/casa-jardim/proposal.pdf", headers=ALINEA)
    assert "R$ 20.000,00" in pdf_text(latest.content)
    older = await client.get(f"/api/projects/{found['id']}/proposals/1/pdf", headers=owner)
    assert "R$ 10.000,00" in pdf_text(older.content)


@pytest.mark.parametrize(
    "changes",
    [
        {"fee": 0},
        {"services": []},
        {"services": [{"title": "  ", "description": ""}]},
        {"client_name": " "},
        {"payments": [{"amount": 0, "when": "no aceite"}]},
        {"not_included": ["x" * 81]},
        {"intro": "x" * 1501},
    ],
)
async def test_an_incomplete_proposal_is_refused(client, owner, changes):
    found = await casa_jardim(client)
    refused = await save(client, owner, found["id"], **changes)
    assert refused.status_code == 422, refused.text


async def test_saving_fills_in_only_the_office_details_it_lacks(client, db_session, owner):
    await client.patch("/api/office", json={"phone": "(11) 1111-1111"}, headers=owner)
    found = await casa_jardim(client)
    await save(
        client,
        owner,
        found["id"],
        phone="(47) 3000-0000",
        whatsapp="(47) 99123-4567",
        email="não é e-mail",
    )
    office = (await client.get("/api/office", headers=ALINEA)).json()
    assert office["phone"] == "(11) 1111-1111"  # set before: owners change it in settings
    assert office["whatsapp"] == "(47) 99123-4567"
    generator = (await client.get(f"/api/projects/{found['id']}/proposal", headers=owner)).json()
    assert generator["office"]["whatsapp"] == "(47) 99123-4567"
    assert office["address"] == "Rua das Palmeiras, 120 - Centro"  # was blank: filled in
    assert (office["city"], office["signatory"]) == ("Joinville", "Arq. Laura Mendes")
    assert office["contact_email"] is None  # not an address: never saved


async def test_an_owner_may_update_the_offices_details_when_saving(client, db_session, owner):
    await client.patch(
        "/api/office",
        json={"phone": "(11) 1111-1111", "city": "Blumenau", "contact_email": "a@alinea.example"},
        headers=owner,
    )
    found = await casa_jardim(client)
    saved = await client.post(
        f"/api/projects/{found['id']}/proposals?update_office=true",
        json=content(phone="(47) 3000-0000", city="", email="b@alinea.example"),
        headers=owner,
    )
    assert saved.status_code == 201, saved.text
    office = (await client.get("/api/office", headers=ALINEA)).json()
    assert office["phone"] == "(47) 3000-0000"
    assert office["contact_email"] == "b@alinea.example"
    assert office["city"] == "Blumenau"  # left blank in the proposal: kept

    member = await sign_in_as(client, db_session, "membro@alinea.example", Role.MEMBER)
    refused = await client.post(
        f"/api/projects/{found['id']}/proposals?update_office=true",
        json=content(phone="(47) 2222-2222"),
        headers=member,
    )
    assert (refused.status_code, refused.json()["error"]) == (403, "owner_only")
    office = (await client.get("/api/office", headers=ALINEA)).json()
    assert office["phone"] == "(47) 3000-0000"
    versions = (await client.get(f"/api/projects/{found['id']}/proposal", headers=owner)).json()
    assert len(versions["versions"]) == 1  # the refused save made no version


async def test_members_make_proposals_too(client, db_session, owner):
    member = await sign_in_as(client, db_session, "membro@alinea.example", Role.MEMBER)
    found = await casa_jardim(client)
    assert (await save(client, member, found["id"])).status_code == 201


async def test_an_archived_project_keeps_its_proposals_unchanged(client, db_session, owner):
    await db_session.execute(
        text("UPDATE projects SET status = 'archived', archived_from = 'active'")
    )
    found = (await client.get("/api/projects", headers=ALINEA)).json()
    assert found == []  # archived projects leave the list
    project_id = await db_session.scalar(text("SELECT id FROM projects WHERE name = 'Casa Jardim'"))
    refused = await save(client, owner, project_id)
    assert (refused.status_code, refused.json()["error"]) == (409, "project_archived")


async def test_another_offices_staff_never_reach_a_proposal(client, db_session, owner):
    found = await casa_jardim(client)
    await save(client, owner, found["id"])
    norte = await sign_in_as(
        client, db_session, "dona@norte.example", Role.OWNER, host=NORTE, slug="norte"
    )
    for path in ("proposal", "proposals/1/pdf"):
        response = await client.get(f"/api/projects/{found['id']}/{path}", headers=norte)
        assert response.status_code == 404, path
    assert (await save(client, norte, found["id"])).status_code == 404


async def test_a_missing_version_says_so(client, owner):
    found = await casa_jardim(client)
    missing = await client.get(f"/api/projects/{found['id']}/proposals/3/pdf", headers=owner)
    assert (missing.status_code, missing.json()["error"]) == (404, "proposal_not_found")
    none = await client.get("/api/pages/casa-jardim/proposal.pdf", headers=ALINEA)
    assert none.status_code == 404


async def test_a_password_protected_pages_proposal_needs_the_password(client, db_session, owner):
    found = await casa_jardim(client)
    await save(client, owner, found["id"])
    await client.patch(
        f"/api/projects/{found['id']}",
        json={
            "row_version": found["row_version"],
            "access_mode": "password",
            "password": "segredo1",
        },
        headers=owner,
    )
    await client.delete("/api/session", headers=owner)
    locked = await client.get("/api/pages/casa-jardim/proposal.pdf", headers=ALINEA)
    assert locked.status_code == 404
    await client.post(
        "/api/pages/casa-jardim/unlock", json={"password": "segredo1"}, headers=ALINEA
    )
    unlocked = await client.get("/api/pages/casa-jardim/proposal.pdf", headers=ALINEA)
    assert unlocked.status_code == 200
    assert unlocked.headers["cache-control"] == "private, no-store"


async def test_the_pdf_is_named_after_the_project_and_downloads_on_request(client, owner):
    found = await casa_jardim(client)
    await save(client, owner, found["id"])
    shown = await client.get("/api/pages/casa-jardim/proposal.pdf", headers=ALINEA)
    assert shown.headers["content-type"] == "application/pdf"
    assert shown.headers["content-disposition"].startswith('inline; filename="Proposta - Casa')
    assert (
        "filename*=UTF-8''Proposta%20-%20Casa%20Jardim.pdf" in shown.headers["content-disposition"]
    )
    saved = await client.get("/api/pages/casa-jardim/proposal.pdf?download=true", headers=ALINEA)
    assert saved.headers["content-disposition"].startswith("attachment;")


async def test_previews_save_nothing(client, owner):
    found = await casa_jardim(client)
    pdf = await client.post(
        f"/api/projects/{found['id']}/proposal/preview", json=content(), headers=owner
    )
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    page = await client.post(
        f"/api/projects/{found['id']}/proposal/preview-page",
        json=content(fee=None, services=[]),
        headers=owner,
    )
    assert page.status_code == 200, page.text
    assert (page.json()["fee"], page.json()["services"]) == ("", [])
    start = (await client.get(f"/api/projects/{found['id']}/proposal", headers=owner)).json()
    assert start["versions"] == []


async def test_the_page_shows_the_proposal_with_its_amounts_written_out(client, db_session, owner):
    found = await casa_jardim(client)
    await save(client, owner, found["id"])
    await make_proposal(db_session)
    shown = (await client.get("/api/pages/casa-jardim", headers=ALINEA)).json()["proposal"]
    assert shown["fee"] == "R$ 29.000,00"
    assert shown["fee_in_words"] == "vinte e nove mil reais"
    assert shown["date_line"] == "Joinville, 28 de outubro de 2026"
    assert shown["payments"][0] == {"amount": "R$ 14.500,00", "when": "no aceite da proposta"}
    assert shown["not_included"] == ["Projeto estrutural", "Projeto de paisagismo"]


# -- presets and defaults -------------------------------------------------------------


async def test_the_offices_services_replace_the_built_in_ones_until_emptied(client, owner):
    mine = [{"title": "Consultoria", "description": "Uma visita."}]
    saved = await client.put("/api/proposal-presets", json={"services": mine}, headers=owner)
    assert saved.json() == mine
    found = await casa_jardim(client)
    start = (await client.get(f"/api/projects/{found['id']}/proposal", headers=owner)).json()
    assert start["presets"] == mine and start["start"]["services"] == mine
    emptied = await client.put("/api/proposal-presets", json={"services": []}, headers=owner)
    assert emptied.json()[0]["title"] == "Briefing"  # the built-in list again


async def test_an_offices_presets_and_defaults_are_its_own(client, db_session, owner):
    await client.put(
        "/api/proposal-presets",
        json={"services": [{"title": "Só Alinea", "description": ""}]},
        headers=owner,
    )
    await client.patch("/api/proposal-defaults", json={"intro": "Olá da Alinea."}, headers=owner)
    norte = await sign_in_as(
        client, db_session, "dona@norte.example", Role.OWNER, host=NORTE, slug="norte"
    )
    norte_project = (await client.get("/api/projects", headers=NORTE)).json()[0]
    start = (
        await client.get(f"/api/projects/{norte_project['id']}/proposal", headers=norte)
    ).json()
    assert start["presets"][0]["title"] == "Briefing"
    assert start["default_intro"] != "Olá da Alinea."


async def test_saved_defaults_start_the_next_new_proposal(client, owner):
    changed = await client.patch(
        "/api/proposal-defaults", json={"intro": " Nova abertura. ", "notes": ""}, headers=owner
    )
    assert changed.json() == {"intro": "Nova abertura.", "notes": ""}
    found = await casa_jardim(client)
    start = (await client.get(f"/api/projects/{found['id']}/proposal", headers=owner)).json()
    assert (start["start"]["intro"], start["start"]["notes"]) == ("Nova abertura.", "")


async def test_only_owners_change_the_offices_proposal_details(client, db_session, owner):
    changed = await client.patch("/api/office", json={"city": " Blumenau "}, headers=owner)
    assert changed.json()["city"] == "Blumenau"
    cleared = await client.patch("/api/office", json={"city": ""}, headers=owner)
    assert cleared.json()["city"] == ""
    member = await sign_in_as(client, db_session, "membro@alinea.example", Role.MEMBER)
    refused = await client.patch("/api/office", json={"city": "Blumenau"}, headers=member)
    assert refused.status_code == 403


# -- the PDF itself ---------------------------------------------------------------------


def test_the_pdf_says_what_the_proposal_holds():
    proposal = ProposalContent.model_validate(content())
    pdf = render(
        proposal, office_name="Alinea", project_name="Casa Jardim", logo=None, locale=Locale.PT_BR
    )
    drawn = pdf_text(pdf)
    for expected in (
        "Joinville, 28 de outubro de 2026",
        "HELENA DUARTE RAMOS",
        "Prezado(a) Senhor(a),",
        "1. BRIEFING",
        "2. IMAGENS RENDERIZADAS",
        "vinte e nove mil reais",
        "R$ 14.500,00 no aceite da proposta",
        "PROJETO DE PAISAGISMO",
        "ARQ. LAURA MENDES",
        "contato@alinea.example",
        "ALINEA",  # no logo: the office's name at the top
    ):
        assert expected in drawn, expected


def test_the_pdf_draws_any_text_and_survives_a_broken_logo():
    """Text from anywhere (an emoji, a dash Helvetica lacks) never stops a proposal,
    nor does a logo that can't be read."""
    proposal = ProposalContent.model_validate(
        content(client_name="Zoë 😀 Ŵ", intro="Prédio – “novo” … ≥ 3 pavimentos")
    )
    pdf = render(proposal, office_name="A", project_name="B", logo=PNG, locale=Locale.EN)
    assert pdf.startswith(b"%PDF")
    drawn = pdf_text(pdf)
    # Windows-1252 kept (Ë, the dash, curly quotes, the ellipsis); Ŵ as its W.
    assert "ZOË W" in drawn and "Prédio – “novo” …" in drawn


def test_a_logo_is_drawn_at_the_top(tmp_path):
    from PIL import Image

    image = tmp_path / "logo.png"
    Image.new("RGB", (400, 100), "black").save(image)
    proposal = ProposalContent.model_validate(content())
    pdf = render(
        proposal,
        office_name="Alinea",
        project_name="B",
        logo=image.read_bytes(),
        locale=Locale.PT_BR,
    )
    assert b"/Subtype /Image" in pdf
    assert "ALINEA" not in pdf_text(pdf).split("Joinville")[0]


@pytest.mark.parametrize(
    ("whatsapp", "shown"),
    [("(47) 99123-4567", True), ("", False), ("(47) 3000-0000", False)],  # the phone's twin: once
)
def test_the_footer_names_a_whatsapp_number_of_its_own(whatsapp, shown):
    proposal = ProposalContent.model_validate(content(whatsapp=whatsapp))
    pdf = render(proposal, office_name="A", project_name="B", logo=None, locale=Locale.PT_BR)
    assert ("WhatsApp" in pdf_text(pdf)) is shown


def test_a_long_proposal_runs_over_several_pages_with_the_footer_on_each():
    many = [{"title": f"Serviço {n}", "description": "Texto longo. " * 40} for n in range(12)]
    proposal = ProposalContent.model_validate(content(services=many))
    pdf = render(proposal, office_name="A", project_name="B", logo=None, locale=Locale.PT_BR)
    pages = len(re.findall(rb"/Type /Page\b", pdf))
    assert pages >= 3
    assert pdf_text(pdf).count("contato@alinea.example") == pages


# -- amounts ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("centavos", "words"),
    [
        (2_900_000, "vinte e nove mil reais"),
        (325_000, "três mil duzentos e cinquenta reais"),
        (580_000, "cinco mil e oitocentos reais"),
        (110_000, "mil e cem reais"),
        (100_100, "mil e um reais"),
        (10_000, "cem reais"),
        (100, "um real"),
        (150, "um real e cinquenta centavos"),
        (1, "um centavo"),
        (100_000_000, "um milhão de reais"),
        (250_000_000, "dois milhões e quinhentos mil reais"),
        (
            123_456_789,
            "um milhão duzentos e trinta e quatro mil quinhentos e sessenta e sete reais "
            "e oitenta e nove centavos",
        ),
    ],
)
def test_amounts_are_written_out_as_a_proposal_writes_them(centavos, words):
    assert in_words(centavos, Locale.PT_BR) == words


def test_amounts_in_english_and_as_figures():
    assert in_words(2_900_050, Locale.EN) == "twenty-nine thousand reais and fifty centavos"
    assert money(2_900_000, Locale.PT_BR) == "R$ 29.000,00"
    assert money(2_900_000, Locale.EN) == "R$29,000.00"


def test_the_date_line_names_the_month_in_the_offices_language():
    from backend.proposals.pdf import date_line

    proposal = ProposalContent.model_validate(content(date=date(2026, 3, 7), city=""))
    assert date_line(proposal, Locale.PT_BR) == "07 de março de 2026"
    assert date_line(proposal, Locale.EN) == "March 07, 2026"
