"""Drawing a proposal as a PDF (A42), in the layout of the offices' own proposals:
the logo at the top of every page, the office's address, phone and email at the
foot, then the letter, the services, the fees, the payments, what is not
included, the observations and two signature lines.

Drawn on the server with fpdf2 (no browser in the image), in Helvetica, which
every PDF reader has. Its encoding (Windows-1252) covers Portuguese and the
usual typography; any other character becomes its closest plain letter.
"""

from __future__ import annotations

import io
import json
import logging
import unicodedata
from functools import cache
from pathlib import Path

from fpdf import FPDF
from PIL import Image

from backend.proposals.content import ProposalContent, in_words, money
from backend.tenancy.models import Locale

log = logging.getLogger(__name__)

_CATALOGS = Path(__file__).resolve().parent.parent / "i18n"
FONT = "helvetica"
BODY = 11  # points
LINE = 6.2  # millimetres between lines of body text
MARGIN = 25
LOGO_BOX = (70, 22)  # the logo fits in this, in millimetres
SIGNATURES_HEIGHT = 48  # closing, acceptance and signatures stay on one page


@cache
def _texts(locale: Locale) -> dict:
    return json.loads((_CATALOGS / f"{locale.value}.json").read_text("utf-8"))["proposal"]


def texts(locale: Locale) -> dict:
    """The proposal's words and built-in defaults, in the office's language."""
    return _texts(locale)


def fill(text: str, **values: object) -> str:
    """`{{name}}` filled in, as the site's `t` does."""
    for name, value in values.items():
        text = text.replace("{{" + name + "}}", str(value))
    return text


def _printable(text: str) -> str:
    """What Helvetica can draw: anything outside Windows-1252 becomes its plain
    letter (é stays; ő becomes o), or goes."""
    out = []
    for char in text:
        try:
            char.encode("cp1252")
            out.append(char)
        except UnicodeEncodeError:
            plain = unicodedata.normalize("NFKD", char).encode("cp1252", "ignore").decode("cp1252")
            out.append(plain)
    return "".join(out)


def _logo(content: bytes | None) -> Image.Image | None:
    """The logo as an image fpdf2 can place, or None if it can't be read."""
    if not content:
        return None
    try:
        image = Image.open(io.BytesIO(content))
        image.load()
    except Exception:  # noqa: BLE001 - a broken logo must not stop the proposal
        log.warning("proposal: the office's logo could not be read")
        return None
    return image


class _Letter(FPDF):
    def __init__(self, office_name: str, logo: Image.Image | None, footer: str) -> None:
        super().__init__(format="A4")
        self.core_fonts_encoding = "windows-1252"
        self.office_name = office_name
        self.logo = logo
        self.footer_text = footer
        self.set_margins(MARGIN, 20, MARGIN)
        self.set_auto_page_break(True, margin=28)

    def header(self) -> None:
        if self.logo is not None:
            width, height = self.logo.size
            scale = min(LOGO_BOX[0] / width, LOGO_BOX[1] / height)
            w, h = width * scale, height * scale
            self.image(self.logo, x=(self.w - w) / 2, y=14, w=w, h=h)
            self.set_y(14 + h + 14)
        else:
            self.set_font(FONT, "B", 15)
            self.set_y(16)
            self.cell(0, 8, _printable(self.office_name.upper()), align="C")
            self.set_y(38)

    def footer(self) -> None:
        if not self.footer_text:
            return
        self.set_y(-18)
        self.set_font(FONT, size=8)
        self.set_text_color(70, 70, 70)
        self.multi_cell(0, 4, _printable(self.footer_text), align="C")
        self.set_text_color(0, 0, 0)


def _footer(content: ProposalContent, locale: Locale) -> str:
    words = texts(locale)["pdf"]
    parts = [content.address, content.phone]
    if content.whatsapp and content.whatsapp != content.phone:
        parts.append(fill(words["whatsapp"], number=content.whatsapp))
    if content.email:
        parts.append(fill(words["email"], email=content.email))
    return " - ".join(part for part in parts if part)


def date_line(content: ProposalContent, locale: Locale) -> str:
    words = texts(locale)["pdf"]
    when = {
        "day": f"{content.date.day:02d}",
        "month": words["months"][content.date.month - 1],
        "year": content.date.year,
    }
    if content.city:
        return fill(words["date"], city=content.city, **when)
    return fill(words["dateNoCity"], **when)


def render(
    content: ProposalContent,
    *,
    office_name: str,
    project_name: str,
    logo: bytes | None,
    locale: Locale,
) -> bytes:
    """The proposal's PDF."""
    words = texts(locale)["pdf"]
    pdf = _Letter(office_name, _logo(logo), _footer(content, locale))
    pdf.set_title(_printable(fill(words["title"], name=project_name)))
    pdf.set_author(_printable(office_name))
    pdf.add_page()

    def paragraph(text: str, style: str = "", align: str = "J", gap: float = 4) -> None:
        pdf.set_font(FONT, style, BODY)
        for block in text.split("\n\n"):
            pdf.multi_cell(0, LINE, _printable(block.strip()), align=align)
            pdf.ln(gap / 2)
        pdf.ln(gap / 2)

    def heading(text: str, underline: bool = False) -> None:
        if pdf.will_page_break(LINE * 3):  # never alone at the foot of a page
            pdf.add_page()
        pdf.ln(3)
        pdf.set_font(FONT, "BU" if underline else "B", BODY)
        pdf.cell(0, LINE, _printable(text), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    paragraph(date_line(content, locale), align="L")
    pdf.ln(2)
    paragraph(content.client_name.upper(), align="L", gap=2)
    paragraph(words["greeting"], align="L")
    if content.intro:
        paragraph(content.intro)

    heading(words["services"])
    for number, service in enumerate(content.services, start=1):
        if pdf.will_page_break(LINE * 3):
            pdf.add_page()
        pdf.set_font(FONT, "B", BODY)
        pdf.multi_cell(0, LINE, _printable(f"{number}. {service.title.upper()}"), align="L")
        pdf.ln(1.5)
        if service.description:
            paragraph(service.description)
        else:
            pdf.ln(2)

    heading(words["fees"])
    paragraph(
        fill(
            words["feesText"],
            amount=money(content.fee, locale),
            words=in_words(content.fee, locale),
        )
    )

    if content.payments:
        heading(words["payment"], underline=True)
        for payment in content.payments:
            paragraph(f"{money(payment.amount, locale)} {payment.when}".strip(), align="L", gap=1.5)
        pdf.ln(2)

    if content.not_included:
        heading(words["notIncluded"])
        for line in content.not_included:
            paragraph(line.upper(), align="L", gap=1.5)
        pdf.ln(2)

    if content.notes:
        heading(words["notes"])
        paragraph(content.notes)

    if pdf.will_page_break(SIGNATURES_HEIGHT):
        pdf.add_page()
    pdf.ln(4)
    paragraph(words["closing"], align="L")
    paragraph(words["acceptance"], align="L")
    pdf.ln(14)
    column = (pdf.w - 2 * MARGIN - 16) / 2
    top = pdf.get_y()
    pdf.set_font(FONT, size=BODY)
    for index, name in enumerate((content.client_name, content.signatory)):
        x = MARGIN + index * (column + 16)
        pdf.set_draw_color(90, 90, 90)
        pdf.set_line_width(0.2)
        pdf.dashed_line(x, top, x + column, top, dash_length=0.6, space_length=0.8)
        pdf.set_xy(x, top + 2)
        pdf.multi_cell(column, LINE, _printable(name.upper()), align="C")
    return bytes(pdf.output())
