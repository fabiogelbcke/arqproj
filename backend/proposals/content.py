"""What a proposal holds (A42), the limits on it, and its amounts in words.

Saved as JSON (`proposals.content`) once it passes `ProposalContent`; the PDF and
the client page both draw from it. Amounts are whole centavos, so no rounding
ever creeps in.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator

from backend.proposals.models import SERVICE_DESCRIPTION_MAX, SERVICE_TITLE_MAX
from backend.tenancy.models import Locale

CLIENT_MAX = 80
CITY_MAX = 60
ADDRESS_MAX = 120
PHONE_MAX = 40
EMAIL_MAX = 100
SIGNATORY_MAX = 80
INTRO_MAX = 1500
NOTES_MAX = 3000
LINE_MAX = 80  # a payment's "when", a service not included
SERVICES_MAX = 20
PAYMENTS_MAX = 24
NOT_INCLUDED_MAX = 20
# R$ 99.999.999,99: far beyond any proposal, and still words in a line or two.
AMOUNT_MAX = 9_999_999_999


def _tidy(value: str) -> str:
    """Trimmed, with Windows line breaks made plain."""
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


class Service(BaseModel):
    title: str = Field(max_length=SERVICE_TITLE_MAX)
    description: str = Field(default="", max_length=SERVICE_DESCRIPTION_MAX)

    @field_validator("title", "description")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        return _tidy(value)

    @field_validator("title")
    @classmethod
    def _named(cls, value: str) -> str:
        if not value:
            raise ValueError("a service needs a title")
        return value


class Payment(BaseModel):
    amount: int = Field(gt=0, le=AMOUNT_MAX)  # centavos
    when: str = Field(max_length=LINE_MAX)  # "no aceite da proposta", "30 dias após"

    @field_validator("when")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        return _tidy(value)


class ProposalContent(BaseModel):
    """Everything a proposal says. The office's name and logo are not in it:
    the PDF always shows the office's current ones."""

    client_name: str = Field(max_length=CLIENT_MAX)
    city: str = Field(default="", max_length=CITY_MAX)
    date: date
    intro: str = Field(default="", max_length=INTRO_MAX)
    services: list[Service] = Field(min_length=1, max_length=SERVICES_MAX)
    fee: int = Field(gt=0, le=AMOUNT_MAX)  # centavos
    payments: list[Payment] = Field(default=[], max_length=PAYMENTS_MAX)
    not_included: list[str] = Field(default=[], max_length=NOT_INCLUDED_MAX)
    notes: str = Field(default="", max_length=NOTES_MAX)
    signatory: str = Field(default="", max_length=SIGNATORY_MAX)
    # The footer: the office's details as they were when it was saved.
    address: str = Field(default="", max_length=ADDRESS_MAX)
    phone: str = Field(default="", max_length=PHONE_MAX)
    whatsapp: str = Field(default="", max_length=PHONE_MAX)
    email: str = Field(default="", max_length=EMAIL_MAX)

    @field_validator(
        "client_name",
        "city",
        "intro",
        "notes",
        "signatory",
        "address",
        "phone",
        "whatsapp",
        "email",
    )
    @classmethod
    def _trimmed(cls, value: str) -> str:
        return _tidy(value)

    @field_validator("client_name")
    @classmethod
    def _named(cls, value: str) -> str:
        if not value:
            raise ValueError("the client's name is needed")
        return value

    @field_validator("not_included")
    @classmethod
    def _lines(cls, value: list[str]) -> list[str]:
        lines = [_tidy(line) for line in value]
        if any(len(line) > LINE_MAX for line in lines):
            raise ValueError("a line is too long")
        return [line for line in lines if line]


# -- amounts ---------------------------------------------------------------------


def money(centavos: int, locale: Locale) -> str:
    """R$ 29.000,00 (pt-BR) or R$29,000.00 (en)."""
    reais, cents = divmod(centavos, 100)
    grouped = f"{reais:,}"
    if locale is Locale.EN:
        return f"R${grouped}.{cents:02d}"
    return f"R$ {grouped.replace(',', '.')},{cents:02d}"


_UNITS_PT = (
    "zero um dois três quatro cinco seis sete oito nove dez onze doze treze quatorze "
    "quinze dezesseis dezessete dezoito dezenove"
).split()
_TENS_PT = "_ _ vinte trinta quarenta cinquenta sessenta setenta oitenta noventa".split()
_HUNDREDS_PT = (
    "_ cento duzentos trezentos quatrocentos quinhentos seiscentos setecentos oitocentos novecentos"
).split()
# (singular, plural) for thousands, millions, billions.
_SCALES_PT = ((None, None), ("mil", "mil"), ("milhão", "milhões"), ("bilhão", "bilhões"))


def _below_thousand_pt(n: int) -> str:
    if n == 100:
        return "cem"
    hundreds, rest = divmod(n, 100)
    parts = [_HUNDREDS_PT[hundreds]] if hundreds else []
    if rest:
        if rest < 20:
            parts.append(_UNITS_PT[rest])
        else:
            tens, units = divmod(rest, 10)
            parts.append(_TENS_PT[tens] + (f" e {_UNITS_PT[units]}" if units else ""))
    return " e ".join(parts)


def _integer_pt(n: int) -> str:
    if n == 0:
        return "zero"
    groups = []
    while n:
        n, group = divmod(n, 1000)
        groups.append(group)
    words = []
    for scale in range(len(groups) - 1, -1, -1):
        group = groups[scale]
        if not group:
            continue
        singular, plural = _SCALES_PT[scale]
        if scale == 1 and group == 1:
            text = "mil"  # "mil", never "um mil"
        elif scale == 0:
            text = _below_thousand_pt(group)
        else:
            text = f"{_below_thousand_pt(group)} {singular if group == 1 else plural}"
        words.append((group, text))
    # Groups join with "e" when the next is below 100 or a round hundred ("mil e
    # quinhentos", "mil e cem"), else with a space ("mil duzentos e cinquenta").
    out = words[0][1]
    for group, text in words[1:]:
        out += (" e " if group < 100 or group % 100 == 0 else " ") + text
    return out


def _words_pt(centavos: int) -> str:
    reais, cents = divmod(centavos, 100)
    parts = []
    if reais:
        whole = _integer_pt(reais)
        # "um milhão de reais", "dois mil reais": "de" after a round million or billion.
        millions = reais >= 1_000_000 and reais % 1_000_000 == 0
        parts.append(f"{whole} {'de ' if millions else ''}{'real' if reais == 1 else 'reais'}")
    if cents:
        parts.append(f"{_integer_pt(cents)} {'centavo' if cents == 1 else 'centavos'}")
    return " e ".join(parts) if parts else "zero real"


_UNITS_EN = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen"
).split()
_TENS_EN = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
_SCALES_EN = ("", "thousand", "million", "billion")


def _below_thousand_en(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    parts = [f"{_UNITS_EN[hundreds]} hundred"] if hundreds else []
    if rest:
        if rest < 20:
            parts.append(_UNITS_EN[rest])
        else:
            tens, units = divmod(rest, 10)
            parts.append(_TENS_EN[tens] + (f"-{_UNITS_EN[units]}" if units else ""))
    return " ".join(parts)


def _integer_en(n: int) -> str:
    if n == 0:
        return "zero"
    words = []
    scale = 0
    while n:
        n, group = divmod(n, 1000)
        if group:
            words.insert(0, f"{_below_thousand_en(group)} {_SCALES_EN[scale]}".strip())
        scale += 1
    return " ".join(words)


def _words_en(centavos: int) -> str:
    reais, cents = divmod(centavos, 100)
    parts = []
    if reais:
        parts.append(f"{_integer_en(reais)} {'real' if reais == 1 else 'reais'}")
    if cents:
        parts.append(f"{_integer_en(cents)} {'centavo' if cents == 1 else 'centavos'}")
    return " and ".join(parts) if parts else "zero reais"


def in_words(centavos: int, locale: Locale) -> str:
    """The amount as a proposal writes it out: "vinte e nove mil reais"."""
    return _words_en(centavos) if locale is Locale.EN else _words_pt(centavos)
