# Margin simulations

**28 October 2026 · rough simulations for discussion, not decisions** · part of
[What Unio costs](README.md)

What's left of revenue at different numbers of offices, prices and tax regimes,
**before salaries and marketing**. Rough on purpose: every office in a steady
month, no churn, no growth curve, no free trial offices.

## How it's calculated

Per month, at a number of paying offices:

> **left = revenue − cost per office × offices − payment fees − tax − fixed costs**

- **Revenue:** the tier mix below, less 2 months for offices on annual billing,
  less 50% for the founding offices.
- **Cost per office:** downloads and emails, US$2.60 (R$14); with WhatsApp and
  the AI assistant, US$4.90 (R$27). From [per-office.md](per-office.md).
- **Payment fees:** Pix by hand (R$0) up to 19 offices, then Asaas at R$1.99 a
  payment.
- **Tax:** Simples Nacional on the yearly revenue, Anexo III or V
  ([per-office.md](per-office.md#taxes-grow-with-revenue)).
- **Fixed costs:** the steps in [fixed.md](fixed.md#by-size).
- **One-off costs** (~R$1,500, [one-time.md](one-time.md)) only in the payback
  column.

### Assumptions

| | Value | Where it comes from |
| --- | --- | --- |
| Tier mix | 30% Essencial at R$119, 55% Profissional at R$249, 15% Escritório at R$549 | The lower end of [the tier sketch](../pricing-and-trials.md#tier-sketch-hypotheses-to-test-with-pilot-offices); the mix is a guess |
| Annual billing | 30% of offices (pay 10 months, get 12) | Guess |
| Founding offices | The first 10, at 50% off for life | [Trial model E](../pricing-and-trials.md#4-free-trials-the-options) |
| Exchange rate | US$1 = R$5.50 | |

To try other numbers, change them at the top of [simulate.py](simulate.py) and
run `python3 docs/costs/simulate.py --update`, which rewrites the tables below.
It needs only Python.

## Results

<!-- simulate.py:start -->
Average price after the tier mix and annual discounts: **R$242** a month.

### Main scenario (Anexo III, no extras), per month

|  | 5 offices | 10 offices | 20 offices | 50 offices | 100 offices | 200 offices |
| --- | --- | --- | --- | --- | --- | --- |
| Revenue | R$606 | R$1,211 | R$3,634 | R$10,901 | R$23,014 | R$47,239 |
| Cost per office (Cloud, email) | R$72 | R$143 | R$286 | R$715 | R$1,430 | R$2,860 |
| Payment fees | R$0 | R$0 | R$40 | R$100 | R$199 | R$398 |
| Simples Nacional | R$36 | R$73 | R$218 | R$654 | R$1,798 | R$4,907 |
| Fixed costs | R$520 | R$520 | R$1,197 | R$1,224 | R$2,250 | R$2,679 |
| **Left before salaries and marketing** | **−R$22** | **R$476** | **R$1,893** | **R$8,208** | **R$17,337** | **R$36,395** |
| **Margin** | **−4%** | **39%** | **52%** | **75%** | **75%** | **77%** |
| Total cost per office | R$126 | R$74 | R$87 | R$54 | R$57 | R$54 |

### Margin under other assumptions

|  | 5 | 10 | 20 | 50 | 100 | 200 |
| --- | --- | --- | --- | --- | --- | --- |
| Main scenario | −4% | 39% | 52% | 75% | 75% | 77% |
| Anexo V (payroll under 28% of revenue) | −13% | 30% | 43% | 66% | 67% | 70% |
| WhatsApp + AI assistant for every office | −14% | 29% | 45% | 69% | 70% | 72% |
| Anexo V and both extras | −24% | 19% | 36% | 60% | 61% | 64% |

### Margin by average price (main scenario)

| Average price | 5 | 10 | 20 | 50 | 100 | 200 |
| --- | --- | --- | --- | --- | --- | --- |
| R$129 | −89% | −9% | 15% | 59% | 62% | 68% |
| R$199 | −25% | 27% | 43% | 71% | 72% | 75% |
| R$249 | −1% | 41% | 53% | 76% | 76% | 77% |
| R$299 | 15% | 50% | 60% | 79% | 78% | 79% |
| R$399 | 35% | 61% | 69% | 82% | 80% | 80% |

### Break-even and paying back the one-off costs

| Average price | Fixed costs covered from | One-off costs (R$1,500) paid back at 20 offices |
| --- | --- | --- |
| R$129 | 12 offices | 6 months |
| R$199 | 7 offices | 2 months |
| R$249 | 6 offices | 1 month |
| R$299 | 5 offices | 1 month |
| R$399 | 4 offices | 1 month |
<!-- simulate.py:end -->

## Reading it

- **Below ~6 paying offices the fixed costs aren't covered**, and the 10
  founding offices at half price keep the margin low up to about 20. That's
  expected for a pilot, and the amounts are small either way.
- **From ~50 offices about three quarters of revenue is left**, and it barely
  moves after that: taxes rise with revenue about as fast as fixed costs shrink
  per office.
- **The tax annex moves the margin by about 9 points**, more than WhatsApp and
  the AI assistant together (about 6). Settle Anexo III vs V (the *Fator R*)
  with the accountant before fixing prices.
- **Price matters most at small sizes.** At 20 offices an average of R$129
  leaves 15%, R$249 leaves 53%. At 100 offices the gap narrows (62% vs 76%).
- **Not in here:** salaries (Fabio's *pró-labore* is also what qualifies for
  Anexo III), marketing, the time spent on support and onboarding, and churn.
  The ~R$17,000 a month left at 100 offices is what pays for all of them.
