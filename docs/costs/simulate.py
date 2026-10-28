"""Rough margin simulations for Unio: what's left of revenue at each number of offices.

Run `python3 docs/costs/simulate.py` to print the tables, or `--update` to rewrite
them in margin.md (between the `simulate.py` markers). Change an assumption below,
rerun, commit both files. Costs come from fixed.md, per-office.md and
one-time.md; plans and prices are hypotheses to compare. Rough on purpose: no churn, no growth
curve, every office in steady state.
"""

import math
import re
import sys
from pathlib import Path

USD = 5.50  # R$ per US$1

# -- Plans ----------------------------------------------------------------------------

# What each plan includes and what an office on it costs us. Traffic is what its client
# pages download in a month (per-office.md: ~US$0.12 a GB through Cloud Run).
# (plan, staff, active projects, GB downloaded a month, share of offices)
PLANS = [
    ("Essencial", "1–2", "3", 5, 0.40),
    ("Profissional", "up to 5", "15", 20, 0.45),
    ("Escritório", "unlimited", "50", 60, 0.15),
]
# Monthly prices (R$) for each plan, in PLANS' order: the price sets compared.
PRICE_SETS = {
    "A": (59, 149, 349),
    "B": (79, 199, 449),
    "C": (89, 229, 499),
    "D": (99, 249, 549),
    "E": (119, 299, 649),
}
MAIN = "C"
ANNUAL_SHARE = 0.30  # offices on annual billing: pay 10 months, get 12
FOUNDING = 10  # founding offices (trial model E): 50% off for life
FOUNDING_DISCOUNT = 0.50


def paid(price):
    """What a plan's price brings in a month, after annual billing's 2 free months."""
    return price * (1 - ANNUAL_SHARE * 2 / 12)


def average_price(prices, mix=None):
    mix = mix or [plan[4] for plan in PLANS]
    return sum(paid(price) * share for price, share in zip(prices, mix, strict=True))


# -- Costs that grow with each office (per-office.md), US$/month -----------------------

GB_USD = 0.12  # download traffic, per GB
EMAILS_USD = 0.10  # update emails, per office
EXTRAS_USD = {"WhatsApp updates": 2.00, "AI assistant in the panel": 0.30}
PIX_FEE = 1.99  # R$ per payment through Asaas; Pix by hand (R$0) below ASAAS_FROM
ASAAS_FROM = 20


def serving_usd(gb, extras=False):
    """US$/month an office costs us: its traffic, its emails and any extras."""
    return gb * GB_USD + EMAILS_USD + (sum(EXTRAS_USD.values()) if extras else 0)


# -- Fixed costs (fixed.md): each steps up with the number of offices ------------------


def fixed_usd(n):
    """US$/month of everything that doesn't grow office by office."""
    return {
        "Cloud SQL": 10 if n <= 60 else 28,
        "Load balancer": 19,
        "Cloud Run, Build, Scheduler": 0 if n < 50 else 5,
        "Email (Resend)": 0 if n <= 10 else 20 if n <= 150 else 90,
        "Domains": 3,
        "Support chat": 0 if n < 15 else 45 if n < 60 else 95,
        "Error tracking and uptime": 0 if n < 15 else 26 if n < 60 else 56,
        "Email accounts (Workspace)": 8 * (1 if n < 15 else 2 if n < 60 else 3 if n < 150 else 4),
        "AI for the business": 0 if n < 15 else 15 if n < 60 else 50,
        "Claude subscription (building, support, the business)": 50,
        "Accountant": (150 if n < 60 else 200) / USD,
    }


# -- Taxes: Simples Nacional, by the last 12 months' revenue ---------------------------

# (revenue up to R$/year, nominal rate, deduction R$). LC 123/2006, annexes III and V.
ANEXO_III = [
    (180e3, 0.06, 0),
    (360e3, 0.112, 9_360),
    (720e3, 0.135, 17_640),
    (1.8e6, 0.16, 35_640),
    (3.6e6, 0.21, 125_640),
    (4.8e6, 0.33, 648_000),
]
ANEXO_V = [
    (180e3, 0.155, 0),
    (360e3, 0.18, 4_500),
    (720e3, 0.195, 9_900),
    (1.8e6, 0.205, 17_100),
    (3.6e6, 0.23, 62_100),
    (4.8e6, 0.305, 540_000),
]


def tax_rate(yearly, annex):
    for ceiling, rate, deduction in annex:
        if yearly <= ceiling:
            return rate if yearly <= 180e3 else (yearly * rate - deduction) / yearly
    raise ValueError("over the Simples Nacional ceiling")


# -- The model -------------------------------------------------------------------------


def month(n, prices=PRICE_SETS[MAIN], annex=ANEXO_III, extras=False, mix=None):
    """One month at `n` paying offices, in R$."""
    mix = mix or [plan[4] for plan in PLANS]
    founding = min(n, FOUNDING)
    revenue = average_price(prices, mix) * (n - founding * FOUNDING_DISCOUNT)
    gb = sum(plan[3] * share for plan, share in zip(PLANS, mix, strict=True))
    variable = n * serving_usd(gb, extras) * USD
    fees = n * PIX_FEE if n >= ASAAS_FROM else 0
    tax = revenue * tax_rate(revenue * 12, annex)
    fixed = sum(fixed_usd(n).values()) * USD
    result = revenue - variable - fees - tax - fixed
    return {
        "revenue": revenue,
        "variable": variable,
        "fees": fees,
        "tax": tax,
        "fixed": fixed,
        "result": result,
        "margin": result / revenue,
    }


def one_office(price, gb):
    """What one office on a plan leaves each month, before fixed costs (R$, first tax
    bracket, Asaas fee)."""
    income = paid(price)
    cost = income * ANEXO_III[0][1] + PIX_FEE + serving_usd(gb) * USD
    return income, cost, income - cost


def brl(value):
    sign = "−" if value < -0.5 else ""
    return f"{sign}R${abs(value):,.0f}"


def pct(value):
    return f"{value:.0%}".replace("-", "−")


def table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + " --- |" * len(header)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


SIZES = [5, 10, 20, 50, 100, 200]


def by_size(label, **kw):
    return [label] + [pct(month(n, **kw)["margin"]) for n in SIZES]


def report():
    out = []
    main = PRICE_SETS[MAIN]
    out.append("### The plans and price sets compared\n")
    body = [
        [name, staff, projects, f"{gb} GB", pct(share)]
        + [brl(prices[i]) for prices in PRICE_SETS.values()]
        for i, (name, staff, projects, gb, share) in enumerate(PLANS)
    ]
    body.append(
        ["**Average paid**", "", "", "", ""]
        + [f"**{brl(average_price(prices))}**" for prices in PRICE_SETS.values()]
    )
    out.append(
        table(
            ["Plan", "Staff", "Active projects", "Traffic", "Offices", *PRICE_SETS],
            body,
        )
    )
    out.append(
        "\n“Average paid” is after annual billing's two free months, before founding discounts.\n"
    )

    out.append(f"### Price set {MAIN}, per month (Anexo III, no extras)\n")
    runs = [month(n) for n in SIZES]
    rows = [
        ("Revenue", "revenue"),
        ("Serving the offices (traffic, email)", "variable"),
        ("Payment fees", "fees"),
        ("Simples Nacional", "tax"),
        ("Fixed costs", "fixed"),
    ]
    body = [[label] + [brl(r[key]) for r in runs] for label, key in rows]
    body.append(
        ["**Left before salaries and marketing**"] + [f"**{brl(r['result'])}**" for r in runs]
    )
    body.append(["**Margin**"] + [f"**{pct(r['margin'])}**" for r in runs])
    out.append(table(["", *(f"{n} offices" for n in SIZES)], body))

    out.append("\n### Margin by price set\n")
    body = [
        by_size(f"{name} ({' / '.join(brl(p) for p in prices)})", prices=prices)
        for name, prices in PRICE_SETS.items()
    ]
    out.append(table(["Price set", *(f"{n}" for n in SIZES)], body))

    out.append(f"\n### Margin under other assumptions (price set {MAIN})\n")
    small = [0.60, 0.30, 0.10]
    body = [
        by_size("As above"),
        by_size("Anexo V (payroll under 28% of revenue)", annex=ANEXO_V),
        by_size("WhatsApp + AI assistant for every office", extras=True),
        by_size("Anexo V and both extras", annex=ANEXO_V, extras=True),
        by_size(f"More small offices ({' / '.join(pct(s) for s in small)})", mix=small),
    ]
    out.append(table(["", *(f"{n}" for n in SIZES)], body))

    out.append(f"\n### Each plan on its own (price set {MAIN})\n")
    body = []
    for (name, _, _, gb, _), price in zip(PLANS, main, strict=True):
        income, cost, left = one_office(price, gb)
        body.append([name, brl(price), brl(income), brl(cost), brl(left), pct(left / income)])
    out.append(
        table(["Plan", "Price", "Paid on average", "Tax, fee, serving", "Left", "Share"], body)
    )

    out.append("\n### The basic plan's price\n")
    small_fixed = sum(fixed_usd(10).values()) * USD
    gb = PLANS[0][3]
    body = []
    for price in [39, 49, 59, 69, 79, 89, 99]:
        _, _, left = one_office(price, gb)
        body.append([brl(price), brl(left), f"{math.ceil(small_fixed / left)}"])
    out.append(
        table(
            [
                "Essencial at",
                "Left per office",
                f"Offices on it alone to cover today's fixed costs ({brl(small_fixed)})",
            ],
            body,
        )
    )

    out.append("\n### Break-even\n")
    body = []
    for name, prices in PRICE_SETS.items():
        even = next((n for n in range(1, 500) if month(n, prices=prices)["result"] >= 0), None)
        body.append([name, f"{even} offices", brl(month(20, prices=prices)["result"])])
    out.append(table(["Price set", "Fixed costs covered from", "Left at 20 offices"], body))
    return "\n".join(out)


START, END = "<!-- simulate.py:start -->", "<!-- simulate.py:end -->"

if __name__ == "__main__":
    text = report()
    if "--update" in sys.argv:
        doc = Path(__file__).with_name("margin.md")
        pattern = re.compile(re.escape(START) + ".*?" + re.escape(END), re.S)
        doc.write_text(pattern.sub(lambda _: f"{START}\n{text}\n{END}", doc.read_text()))
    else:
        print(text)
