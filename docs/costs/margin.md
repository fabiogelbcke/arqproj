# Margin simulations

**28 October 2026 · rough simulations for discussion, not decisions** · part of
[What Unio costs](README.md)

What's left of revenue at different numbers of offices, prices and tax regimes,
**before salaries and marketing**. Rough on purpose: every office in a steady
month, no churn, no growth curve, no free trial offices.

## How it's calculated

Per month, at a number of paying offices:

> **left = revenue − serving the offices − payment fees − tax − fixed costs**

- **Revenue:** three plans (Essencial, Profissional, Escritório) at each price
  set's prices, mixed 40% / 45% / 15%, less 2 months for offices on annual
  billing, less 50% for the founding offices.
- **Serving the offices:** each plan's download traffic at ~US$0.12 a GB (5, 20
  and 60 GB a month) plus emails, ~R$14 an office on average; WhatsApp and the
  AI assistant add ~R$13. From [per-office.md](per-office.md).
- **Payment fees:** Pix by hand (R$0) up to 19 offices, then Asaas at R$1.99 a
  payment.
- **Tax:** Simples Nacional on the yearly revenue, Anexo III or V
  ([per-office.md](per-office.md#taxes-grow-with-revenue)).
- **Fixed costs:** the steps in [fixed.md](fixed.md#by-size), with an online
  accountant at R$150–200.
- **One-off costs** (~R$1,500, [one-time.md](one-time.md)) only in the payback
  column.

Plans are measured by staff and active projects, with traffic as what they
cost us ([why](../pricing-and-trials.md#tier-sketch-hypotheses-to-test-with-pilot-offices)).

### Assumptions

| | Value | Where it comes from |
| --- | --- | --- |
| Plans and price sets | In the first table below | Hypotheses around [the tier sketch](../pricing-and-trials.md#tier-sketch-hypotheses-to-test-with-pilot-offices) |
| Plan mix | 40% Essencial, 45% Profissional, 15% Escritório | Guess |
| Annual billing | 30% of offices (pay 10 months, get 12) | Guess |
| Founding offices | The first 10, at 50% off for life | [Trial model E](../pricing-and-trials.md#4-free-trials-the-options) |
| Exchange rate | US$1 = R$5.50 | |

To try other numbers, change them at the top of [simulate.py](simulate.py) and
run `python3 docs/costs/simulate.py --update`, which rewrites the tables below.
It needs only Python.

## Results

<!-- simulate.py:start -->
### The plans and price sets compared

| Plan | Staff | Active projects | Traffic | Offices | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Essencial | 1–2 | 3 | 5 GB | 40% | R$59 | R$79 | R$89 | R$99 | R$119 |
| Profissional | up to 5 | 15 | 20 GB | 45% | R$149 | R$199 | R$229 | R$249 | R$299 |
| Escritório | unlimited | 50 | 60 GB | 15% | R$349 | R$449 | R$499 | R$549 | R$649 |
| **Average paid** |  |  |  |  | **R$136** | **R$179** | **R$203** | **R$222** | **R$266** |

“Average paid” is after annual billing's two free months, before founding discounts.

### Price set C, per month (Anexo III, no extras)

|  | 5 offices | 10 offices | 20 offices | 50 offices | 100 offices | 200 offices |
| --- | --- | --- | --- | --- | --- | --- |
| Revenue | R$507 | R$1,014 | R$3,042 | R$9,127 | R$19,268 | R$39,551 |
| Serving the offices (traffic, email) | R$69 | R$138 | R$275 | R$688 | R$1,375 | R$2,750 |
| Payment fees | R$0 | R$0 | R$40 | R$100 | R$199 | R$398 |
| Simples Nacional | R$30 | R$61 | R$183 | R$548 | R$1,378 | R$3,869 |
| Fixed costs | R$370 | R$370 | R$997 | R$1,024 | R$1,850 | R$2,279 |
| **Left before salaries and marketing** | **R$38** | **R$446** | **R$1,548** | **R$6,768** | **R$14,466** | **R$30,255** |
| **Margin** | **7%** | **44%** | **51%** | **74%** | **75%** | **76%** |

### Margin by price set

| Price set | 5 | 10 | 20 | 50 | 100 | 200 |
| --- | --- | --- | --- | --- | --- | --- |
| A (R$59 / R$149 / R$349) | −35% | 19% | 30% | 64% | 67% | 71% |
| B (R$79 / R$199 / R$449) | −4% | 37% | 45% | 72% | 73% | 75% |
| C (R$89 / R$229 / R$499) | 7% | 44% | 51% | 74% | 75% | 76% |
| D (R$99 / R$249 / R$549) | 15% | 48% | 55% | 76% | 76% | 77% |
| E (R$119 / R$299 / R$649) | 28% | 56% | 61% | 79% | 78% | 79% |

### Margin under other assumptions (price set C)

|  | 5 | 10 | 20 | 50 | 100 | 200 |
| --- | --- | --- | --- | --- | --- | --- |
| As above | 7% | 44% | 51% | 74% | 75% | 76% |
| Anexo V (payroll under 28% of revenue) | −2% | 34% | 41% | 65% | 66% | 69% |
| WhatsApp + AI assistant for every office | −5% | 31% | 43% | 67% | 69% | 70% |
| Anexo V and both extras | −15% | 22% | 33% | 58% | 60% | 62% |
| More small offices (60% / 30% / 10%) | −9% | 36% | 43% | 72% | 74% | 76% |

### Each plan on its own (price set C)

| Plan | Price | Paid on average | Tax, fee, serving | Left | Share |
| --- | --- | --- | --- | --- | --- |
| Essencial | R$89 | R$85 | R$11 | R$74 | 87% |
| Profissional | R$229 | R$218 | R$29 | R$189 | 87% |
| Escritório | R$499 | R$474 | R$71 | R$403 | 85% |

### The basic plan's price

| Essencial at | Left per office | Offices on it alone to cover today's fixed costs (R$370) |
| --- | --- | --- |
| R$39 | R$29 | 13 |
| R$49 | R$38 | 10 |
| R$59 | R$47 | 8 |
| R$69 | R$56 | 7 |
| R$79 | R$65 | 6 |
| R$89 | R$74 | 6 |
| R$99 | R$83 | 5 |

### Break-even and paying back the one-off costs

| Price set | Fixed costs covered from | One-off costs (R$1,500) paid back at 20 offices |
| --- | --- | --- |
| A | 8 offices | 3 months |
| B | 6 offices | 2 months |
| C | 5 offices | 1 month |
| D | 5 offices | 1 month |
| E | 4 offices | 1 month |
<!-- simulate.py:end -->

## Reading it

- **A basic plan under R$100 works.** At R$79–99 an Essencial office leaves
  ~R$65–83 a month after tax, fee and traffic (~85% of its price). It costs us
  little because small offices download little. Even at R$49 it pays for
  itself; what a low price changes is how many offices it takes to pay the
  fixed costs.
- **Below ~5 paying offices the fixed costs aren't covered**, and the 10
  founding offices at half price keep the margin low up to about 20. That's
  expected for a pilot, and the amounts are small either way.
- **From ~50 offices about three quarters of revenue is left** with any price
  set from B up, and it barely moves after that: taxes rise with revenue about
  as fast as fixed costs shrink per office.
- **The tax annex moves the margin by about 9 points**, more than WhatsApp and
  the AI assistant together (about 7). Settle Anexo III vs V (the *Fator R*)
  with the accountant before fixing prices.
- **Price matters most at small sizes.** At 20 offices set A leaves 30% and set
  E 61%; at 100 offices the gap narrows (67% vs 78%).
- **Not in here:** salaries (Fabio's *pró-labore* is also what qualifies for
  Anexo III), marketing, the time spent on support and onboarding, and churn.
  The ~R$14,500 a month left at 100 offices (set C) is what pays for all of
  them.
