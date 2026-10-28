"""Rough margin simulations for Unio: what's left of revenue at each number of offices.

Run `python3 docs/costs/simulate.py` to print the tables, or `--update` to rewrite
them in margin.md (between the `simulate.py` markers). Change an assumption below,
rerun, commit both files. Every figure comes from fixed.md, per-office.md and
one-time.md; this file only adds them up. Rough on purpose: no churn, no growth
curve, every office in steady state.
"""

import re
import sys
from pathlib import Path

USD = 5.50  # R$ per US$1

# -- Revenue --------------------------------------------------------------------------

# (tier, price R$/month, share of offices). Prices: pricing-and-trials.md section 2.
TIERS = [("Essencial", 119, 0.30), ("Profissional", 249, 0.55), ("Escritório", 549, 0.15)]
ANNUAL_SHARE = 0.30  # offices on annual billing: pay 10 months, get 12
FOUNDING = 10  # founding offices (trial model E): 50% off for life
FOUNDING_DISCOUNT = 0.50


def average_price():
    listed = sum(price * share for _, price, share in TIERS)
    return listed * (1 - ANNUAL_SHARE * 2 / 12)


# -- Costs that grow with each office (per-office.md), US$/month -----------------------

PER_OFFICE_USD = {"Downloads (Cloud Run traffic)": 2.50, "Update emails": 0.10}
EXTRAS_USD = {"WhatsApp updates": 2.00, "AI assistant in the panel": 0.30}
PIX_FEE = 1.99  # R$ per payment through Asaas; Pix by hand (R$0) below ASAAS_FROM
ASAAS_FROM = 20


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
        "Accountant": (300 if n < 15 else 350 if n < 60 else 600) / USD,
    }


# -- One-time costs (one-time.md), R$ --------------------------------------------------

ONE_TIME = {"Opening the company": 1_500, "Lawyer: terms, privacy, contract": 5_000}


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


def month(n, price=None, annex=ANEXO_III, extras=False):
    """One month at `n` paying offices, in R$."""
    price = average_price() if price is None else price
    founding = min(n, FOUNDING)
    revenue = price * (n - founding * FOUNDING_DISCOUNT)
    per_office = sum(PER_OFFICE_USD.values()) + (sum(EXTRAS_USD.values()) if extras else 0)
    variable = n * per_office * USD
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


def report():
    out = []
    runs = [month(n) for n in SIZES]
    out.append(
        f"Average price after the tier mix and annual discounts: **{brl(average_price())}"
        "** a month.\n"
    )
    out.append("### Main scenario (Anexo III, no extras), per month\n")
    rows = [
        ("Revenue", "revenue"),
        ("Cost per office (Cloud, email)", "variable"),
        ("Payment fees", "fees"),
        ("Simples Nacional", "tax"),
        ("Fixed costs", "fixed"),
    ]
    body = [[label] + [brl(r[key]) for r in runs] for label, key in rows]
    body.append(
        ["**Left before salaries and marketing**"] + [f"**{brl(r['result'])}**" for r in runs]
    )
    body.append(["**Margin**"] + [f"**{pct(r['margin'])}**" for r in runs])
    body.append(
        ["Total cost per office"]
        + [brl((r["revenue"] - r["result"]) / n) for n, r in zip(SIZES, runs, strict=True)]
    )
    out.append(table(["", *(f"{n} offices" for n in SIZES)], body))

    out.append("\n### Margin under other assumptions\n")
    variants = [
        ("Main scenario", {}),
        ("Anexo V (payroll under 28% of revenue)", {"annex": ANEXO_V}),
        ("WhatsApp + AI assistant for every office", {"extras": True}),
        ("Anexo V and both extras", {"annex": ANEXO_V, "extras": True}),
    ]
    body = [[label] + [pct(month(n, **kw)["margin"]) for n in SIZES] for label, kw in variants]
    out.append(table(["", *(f"{n}" for n in SIZES)], body))

    out.append("\n### Margin by average price (main scenario)\n")
    prices = [129, 199, 249, 299, 399]
    body = [[brl(p)] + [pct(month(n, price=p)["margin"]) for n in SIZES] for p in prices]
    out.append(table(["Average price", *(f"{n}" for n in SIZES)], body))

    out.append("\n### Break-even and paying back the one-off costs\n")
    one_off = sum(ONE_TIME.values())
    body = []
    for p in prices:
        even = next((n for n in range(1, 500) if month(n, price=p)["result"] >= 0), None)
        at_20 = month(20, price=p)["result"]
        payback = f"{one_off / at_20:.0f} months" if at_20 > 0 else "never"
        body.append([brl(p), f"{even} offices", payback])
    out.append(
        table(
            [
                "Average price",
                "Fixed costs covered from",
                f"One-off costs ({brl(one_off)}) paid back at 20 offices",
            ],
            body,
        )
    )
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
