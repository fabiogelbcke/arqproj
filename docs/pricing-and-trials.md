# Pricing and free trials

**28 October 2026 · analysis for discussion, not decisions** (costs moved to [costs/](costs/README.md) the same day)

Companion to [plan section 22](multi-tenant-implementation-plan.md#22-pricing-and-pilot-feedback)
(pricing and pilot feedback) and [what Unio costs](costs/README.md). Nothing
here is decided. A choice taken from this document goes into the
[decision register](multi-tenant-implementation-plan.md#2-decision-register)
and the [changelog](decision-changelog.md) like any other.

Prices in BRL use **US$1 = R$5.50**. Third-party prices were checked on
28 Oct 2026 against the sources at the end. Several come from secondary
sources; confirm them on the provider's own page before relying on them.

## 1. What it all costs

The costs are in their own documents, under [costs/](costs/README.md):
[fixed](costs/fixed.md) (product and business tools),
[per office](costs/per-office.md) (traffic, extras, payment fees, taxes),
[one-off](costs/one-time.md), and [margin simulations](costs/margin.md) at 5 to
200 offices.

In short: about R$14 a month per office plus taxes (6% under Simples Anexo III,
15.5% under Anexo V), R$520–2,700 a month of fixed costs depending on size, and
about R$1,500 once. At an average R$242 a month, fixed costs are covered from
about 6 paying offices, and about 75% of revenue is left from 50 offices,
before salaries and marketing.

**What actually decides the margin:** the price, the tax annex (section 3) and
the time spent on support and onboarding, not infrastructure. That's why the
support tools start free and why the help center (ai-for-the-business.md) is
worth writing early.

## 2. What to charge

Section 22 already proposes the price axis: **active projects**. An office pays
for projects that still take uploads and send updates; archived projects stay
viewable for free. It's easy to explain, grows with the office's success, and
matches what costs us anything (downloads and emails come from active projects).

### Tier sketch (hypotheses to test with pilot offices)

| Tier | Active projects | Staff | Price/month (hypothesis) | For |
| --- | --- | --- | --- | --- |
| Essencial | up to 5 | 2 | R$99–129 | A solo architect or a two-person office |
| Profissional | up to 20 | 5 | R$249–299 | The typical small office (our pilot profile) |
| Escritório | up to 60 | unlimited | R$499–599 | Larger offices; own domain included |
| Sob medida | more | — | quoted | Networks of offices, special terms |

How to read it:

- Even the lowest price covers our cost per office many times over. **Price on
  the value to the office**, not on our costs. Compare: the hours an architect
  saves not answering "where's the latest floor plan?", and how professional the
  page looks to clients.
- **Annual billing at 2 months free** (pay 10, get 12) improves cash flow and
  retention. Monthly billing stays available.
- **Extras that could be paid add-ons later:** the office's own domain for its
  pages (in the top tier only, or around R$30/month), WhatsApp updates
  (future-ideas, with a real cost per message), and more staff seats.
- **Don't build these yet** (section 22): seat management, complex permissions,
  automatic tier enforcement. The pilot charges manually.

### Validating the price

Before fixing numbers, ask the first offices (section 22's questions) what the
portal replaced and what it would hurt to lose. Then use a simple test: quote
the Profissional tier to 5–10 offices at R$249 and to another 5–10 at R$299, and
compare acceptance. Ten paying offices tell us more than any benchmark.

## 3. Taking payments in Brazil

| Option | How it charges | Fees (indicative) | Fit |
| --- | --- | --- | --- |
| **Manual invoice + Pix** (pilot) | We send a Pix charge or *boleto* each month | Pix: free to low; boleto ~R$2–3 | Section 22's plan for the pilot. Fine for under ~20 offices. |
| **Asaas** (Brazilian) | Recurring Pix, boleto or card; sends reminders | Pix about R$0.99–1.99 per payment received; boleto charged only when paid; card at a fixed rate | Built for Brazilian SMB subscriptions; issues *notas fiscais* on some plans. |
| **Pix Automático** (via a bank or provider) | The client authorizes once; monthly charges go automatically | Set by the provider; often low | Launched by the Central Bank on 16 Jun 2025. Ideal for small recurring B2B amounts once our provider supports it. |
| **Stripe** | Card subscriptions; Pix through Stripe's EBANX partnership | Card around 2.9% + fixed fee (check stripe.com/br) | Best tools (Billing, customer portal, trials); weaker for Pix and boleto, which Brazilian SMBs prefer. |
| **Merchant of record** (Paddle and others) | They sell on our behalf and handle tax | ~5% + fixed fee | Simplest tax handling for international sales; expensive for a Brazil-first product. |

Suggested path: **manual Pix invoices for the pilot**, then **Asaas (or a
provider with Pix Automático) once there are 15–20 paying offices**. Stripe only
if card payments or international offices become a real share.

**Taxes are a bigger cost than infrastructure.** Under Simples Nacional, a
software service company typically pays from about 6% of revenue (Anexo III)
up to considerably more (Anexo V), depending on payroll and revenue bracket;
ISS is included in Simples. **Confirm the regime and rate with an accountant
before setting prices.** It changes the margin more than anything else in [the costs](costs/margin.md).

## 4. Free trials: the options

The best-known benchmarks (First Page Sage, 86 SaaS companies, 2022–2025):

- **Opt-in trials (no card):** about **17–18%** of trials convert to paid.
- **Opt-out trials (card required, charged automatically):** about **49%**
  convert, but far fewer people start one.
- The median SaaS trial converts about **8%**, with a wide spread.

These are mostly US/English-market figures. Brazilian SMB buyers are often more
wary of leaving a card, and Pix (our likely payment method) has no card to
pre-authorize. That favours opt-in trials here.

| Model | How it works | For us |
| --- | --- | --- |
| **A. Time-limited, no card** | 30 days of everything, then choose a plan | Simple and familiar. 14 days is too short for a project to reach clients: an office needs time to set up one real project and see a client react. **30 days.** |
| **B. Card-required trial** | Same, with automatic charge at the end | Higher conversion, fewer starts, needs card billing (Stripe). Weak with Pix-first buyers. |
| **C. Freemium** | Free forever for 1 active project, with Unio branding | The client page is itself marketing: every client who opens it sees "Unio". Risk: offices that never upgrade. Our cost per free office is small ([per-office.md](costs/per-office.md)). |
| **D. Reverse trial** | 30 days of the top tier, then it drops to the free tier unless they pay | Combines A and C: they feel the full product, then keep a reason to come back. Common in modern SaaS. |
| **E. Founding offices** | First 10–20 offices: free during the pilot, then 50% off for life (or 12 months) | Rewards early feedback (section 22's "friendly free users"). Put the end date and terms in writing. |
| **F. Money-back guarantee** | Pay from day one; full refund within 30 days | Serious buyers only; few refunds in practice. Works better once there are case studies. |

### Recommendation to discuss

1. **Now (pilot):** **E. Founding offices**, by invitation, manually billed,
   with the end date of the free period written in the invitation.
2. **When public signup opens** (the office-signup link in PR #153 is its
   base): **D. Reverse trial**. That's 30 days of Profissional, then down to a
   free tier of 1 active project, with no card asked.
   - It turns the free tier into permanent marketing: every client page says
     "Unio".
   - It lets an office keep using the product slowly until a second project
     forces the upgrade.
   - **Measure:** trial → paid within 60 days, active projects at day 30, and
     whether a client opened the page in the first week (the moment that sells
     it).
3. **Not yet:** card-required trials (wrong fit for Pix) and automatic tier
   enforcement (section 22: manual first).

### What the product needs for this (not built)

- A plan and its limits stored per office, enforced in the service layer
  (section 22: "entitlements centrally"), not in scattered screens.
- A trial end date per office, with emails at 7 days and 1 day before.
- What happens at the end: projects over the limit become read-only (still
  viewable, like archived), **never deleted**, and clients' links keep working.
- The operator dashboard (A38) showing each office's plan, trial end and
  payment status, so we can bill manually at first.

## Sources

- Asaas fees: [blog.asaas.com/taxas-asaas](https://blog.asaas.com/taxas-asaas/)
- Pix Automático: [Olhar Digital, 04 Jun 2025](https://olhardigital.com.br/2025/06/04/pro/agora-e-oficial-banco-central-apresenta-o-pix-automatico/), [Tecnoblog](https://tecnoblog.net/noticias/pix-automatico-chega-em-junho-saiba-como-ira-funcionar/)
- Stripe and Pix: [Finextra](https://www.finextra.com/newsarticle/46431/stripe-businesses-can-now-accept-pix-in-brazil); card rates from a secondary guide, [ParityDeals](https://www.paritydeals.com/blog/best-payment-gateways-brazil-2026/) (confirm on stripe.com/br)
- Trial conversion benchmarks: [Userpilot](https://userpilot.com/blog/free-trial-conversion-rate/), [Sixteen Ventures](https://sixteenventures.com/saas-free-trial-benchmarks/), [ProductLed](https://productled.com/blog/free-trial-conversion-rate)

Cost sources are in [costs/README.md](costs/README.md#sources).
