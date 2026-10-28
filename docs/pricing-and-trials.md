# Pricing, free trials and operating cost per office

**28 October 2026 · analysis for discussion, not decisions** (cost tables extended the same day)

Companion to [plan section 22](multi-tenant-implementation-plan.md#22-pricing-and-pilot-feedback)
(pricing and pilot feedback) and the
[infrastructure cost comparison](infrastructure-cost-comparison.md). Nothing
here is decided. A choice taken from this document goes into the
[decision register](multi-tenant-implementation-plan.md#2-decision-register)
and the [changelog](decision-changelog.md) like any other.

Prices in BRL use **US$1 = R$5.50**. Third-party prices were checked on
28 Oct 2026 against the sources at the end. Several come from secondary
sources; confirm them on the provider's own page before relying on them.

## 1. What it all costs

Every cost of running Unio, in one place: the product itself, the paid extras an
office could add, and running the business around it. Every amount names its
currency; monthly unless marked. Amounts in reals convert at US$1 = R$5.50.
Prices for extras and tools come from the companion analyses
([storage](storage-strategy.md), [WhatsApp](whatsapp-updates.md),
[AI](ai-for-the-business.md)) and the sources at the end.

### 1a. Running the product (fixed, whatever the number of offices)

| Item | Today (per month) | When it grows (per month) | Notes |
| --- | --- | --- | --- |
| Cloud SQL (`db-f1-micro`, 10 GB, backups) | ~US$10 | ~US$25–30 (`db-g1-small`) | [infrastructure.md](infrastructure.md#costs-approximate-monthly). The next size is likely somewhere past 50–100 active offices; measure first. |
| Global load balancer (A21) | ~US$18–20 + traffic | same | Covered by credits for the first three months. |
| Cloud Run, Build, Artifact Registry, Scheduler | ~US$0 | a few US$ | Within free tiers at pilot scale. |
| Logs and alerts (Cloud Logging and Monitoring) | US$0 | US$0 | 50 GiB of logs a month free; we are far below. |
| Email (Resend) | US$0 | US$20 → US$90 | Free: 3,000 emails a month, 100 a day. Pro: US$20 for 50,000. Scale: from US$90 for 100,000. The 100-a-day cap comes first, around 10 busy offices. |
| Product analytics (PostHog) | US$0 | US$0 at our volume | 1 million events and 5,000 session recordings a month free. |
| Domains (`myunio.app` and others) | ~US$2–4 | same | Averaged per month. An office's own domain is bought by the office; its certificate costs us nothing. |
| **Total** | **~US$30–35 (R$165–190)** | **~US$90 (R$495) at 100 offices** | |

### 1b. Per office, as it is today

Files stay in **the office's own Google Drive**, so storage costs us nothing.
What grows with each office:

| Item | Per office, per month | Notes |
| --- | --- | --- |
| Download traffic | US$1.20–3.60 | The page streams files through Cloud Run: ~US$0.12/GB to the internet, for 10–30 GB a month. |
| Update emails | ~US$0.01–0.20 | A few hundred emails a month, once on a paid Resend plan. |
| Database and compute | ~US$0 | Until the database's next size (1a). |
| **Total** | **~US$1.50–4 (R$8–22)** | Call it **US$2.50** in the totals below. |

### 1c. Extras an office could add (each with its own cost)

These are options, not decided. Each could be in a tier or sold as an add-on
(section 2).

| Extra | Cost to us per office, per month | One-off or fixed cost | Source |
| --- | --- | --- | --- |
| **Our own file storage** (Cloudflare R2) instead of Drive | US$0.75–2.25 for 50–150 GB stored. Downloads from R2 are free, so this **replaces** the US$1.20–3.60 of 1b. | ~2–3 weeks to build | [storage-strategy.md](storage-strategy.md#c-our-own-storage) |
| Own storage on Google Cloud Storage instead | ~US$5.90 for 100 GB stored and 20 GB downloaded (also replacing 1b's downloads) | same | same |
| **More cloud providers** (OneDrive, Dropbox) | ~US$0 | ~2–3 weeks each, then upkeep | [storage-strategy.md](storage-strategy.md#b-more-cloud-providers) |
| **WhatsApp updates** (Meta Cloud API) | ~US$1.30–2.60 for a busy office (160–320 utility messages at ~US$0.008 each); +US$0.005 a message through Twilio | ~1–2 weeks to build; Meta business verification (free) | [whatsapp-updates.md](whatsapp-updates.md#cost) |
| **AI assistant in the panel** | ~US$0.10–0.50 (1,000 questions a month across all offices cost US$10–20) | 1–2 weeks to build | [ai-for-the-business.md](ai-for-the-business.md#1-customer-support) |
| **The office's own domain** for its pages | ~US$0 | An hour of setup per office | — |
| Full Drive access instead of `drive.file` (not recommended) | US$0 | **~US$540 a year** (CASA Tier 2), every year | [storage-strategy.md](storage-strategy.md#where-we-are) |

### 1d. Running the business

| Item | Options (per month unless marked) | Suggested now | Later |
| --- | --- | --- | --- |
| **Support chat on the site and panel** | See the comparison below | **WhatsApp Business app** (free) + **Crisp Free** or **Chatwoot Hacker** (US$0) | Crisp Mini (US$45) or Chatwoot Startups (US$19 per agent) |
| **Error tracking** | Sentry Developer US$0 (1 user, 5,000 errors); Team US$26–29 (50,000 errors) | Cloud Logging's alerts (US$0) | Sentry Team, when a second developer joins |
| **Uptime check and status page** | Better Stack free (10 monitors, 1 status page on our subdomain); UptimeRobot Solo US$12–13 (its free plan is non-commercial only) | Better Stack free | Better Stack paid, from ~US$30 |
| **Email accounts** (`contato@`, `suporte@myunio.app`) | Google Workspace Business Starter US$7–8.40 per user (~R$35–45, plus 6.38% IOF on an international card) | 1–2 users | 1 per person |
| **AI for the business** (support drafts, weekly digest, sales research) | US$5–40 in API costs at pilot scale | Through Fabio's subscription first | See [ai-for-the-business.md](ai-for-the-business.md#what-to-build-first) |
| **Accountant** (Simples Nacional) | R$150–600; online firms R$259–900 | **Needed from the first invoice** | — |
| **Opening the company** (CNPJ) | R$500–3,000, once | Before charging | — |
| **Lawyer** for terms, privacy policy, contract | One-off; get 2–3 quotes | Before public signup | Yearly review |
| **Payment fees** | Pix by hand: ~R$0. Asaas: R$0.99–1.99 per Pix received. Card (Stripe): ~2.9% + a fixed fee per payment | Pix by hand | Asaas at 15–20 paying offices (section 3) |
| **Taxes** | Simples Nacional: from ~6% of revenue (Anexo III), more under Anexo V | — | Confirm with the accountant (section 3) |

#### Support chat tools compared

Prices in US$ per month, mostly from comparison sites (confirm on each
provider's page). "Seat" is one person answering.

| Tool | Free plan | Paid | Notes for us |
| --- | --- | --- | --- |
| **WhatsApp Business app** | Free | — | How Brazilian architects already talk to suppliers. One phone number, a few people via linked devices. No API needed. |
| **Crisp** | 2 seats, chat widget | Mini US$45 (4 seats), Essentials US$95 (10 seats, knowledge base, AI chatbot), Plus US$295 | Priced per workspace, not per seat: cheap for a small team. Has a WhatsApp channel on paid plans. |
| **Chatwoot** (open source) | Hacker: 2 agents, ~500 conversations a month | Startups US$19 per agent, Business US$39 per agent | Can also run on our own server for free. Connects WhatsApp (Cloud API), email and the site chat in one inbox. |
| **tawk.to** | Unlimited agents and chats | Removing "Powered by tawk.to": ~US$19–39 | Cheapest, but its branding shows on our pages unless paid. |
| **Help Scout** | Up to 5 users | Standard US$25 per user, Plus US$45–50 | Email-first help desk with a knowledge base; AI answers US$0.75 per resolution. |
| **Intercom** | — | Essential US$29 per seat (annual), Advanced US$85; Fin AI US$0.99 per resolution, 50 a month minimum | Polished; the most expensive at our size. |
| **Zendesk** | — | Support Team US$19 per agent, Suite Team US$55 | Built for larger support teams. |
| Octadesk, JivoChat (Brazilian) | — | Quote only | Portuguese support and BRL invoices; no public prices found. |

**Suggested:** while Fabio answers support himself, the WhatsApp Business app
plus a free chat widget (Crisp or Chatwoot) on the site and in the panel's help
menu. Move to Chatwoot Startups or Crisp Mini when a second person answers or a
knowledge base is worth writing. Chatwoot fits best if WhatsApp updates (1c)
are built, since one inbox would then hold both.

### 1e. Totals

Three sizes, per month. "Base" is 1a + 1b + the business tools a team that size
needs (1d), without taxes or payment fees.

| | 5 offices (pilot) | 20 offices | 100 offices |
| --- | --- | --- | --- |
| Product (1a) | US$35 | US$50 | US$90 |
| Per office (1b, US$2.50 each) | US$12 | US$50 | US$250 |
| Support chat | US$0 | US$45 (Crisp Mini) | US$95 (Crisp Essentials) |
| Error tracking and uptime | US$0 | US$26 | US$56 |
| Email accounts | US$8 (1 user) | US$16 (2) | US$24 (3) |
| AI for the business | US$0 | US$15 | US$50 |
| Accountant | US$55 (R$300) | US$65 (R$350) | US$110 (R$600) |
| **Base total** | **~US$110 (R$600)** | **~US$265 (R$1,460)** | **~US$675 (R$3,700)** |
| **Base per office** | **~US$22 (R$120)** | **~US$13 (R$73)** | **~US$6.75 (R$37)** |
| + WhatsApp for every office (US$2 each) | +US$10 | +US$40 | +US$200 |
| + Own storage for every office (R2, replaces the downloads in 1b) | ~US$0 | ~US$0 | ~US$0 |

Against the Profissional tier at R$249 a month (section 2), at 100 offices:
about R$37 of base cost, R$11 of WhatsApp, R$15 of Simples tax (6%) and R$1.50
of payment fee per office. **That leaves roughly 75% of the price**, before
salaries and marketing. At 5 offices the base cost per office is high (R$120),
but founding offices are free during the pilot anyway (section 4).

**What actually decides the margin:** taxes (section 3) and the time spent on
support and onboarding, not infrastructure. That's why the support tools above
start free and why the help center (ai-for-the-business.md) is worth writing
early.

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
before setting prices.** It changes the margin more than anything in section 1.

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
| **C. Freemium** | Free forever for 1 active project, with Unio branding | The client page is itself marketing: every client who opens it sees "Unio". Risk: offices that never upgrade. Our cost per free office is small (section 1). |
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

- Support chat: Crisp ([Featurebase](https://www.featurebase.app/blog/crisp-pricing), [Drag](https://www.dragapp.com/blog/crisp-pricing/)); Intercom ([Drag](https://dragapp.com/blog/intercom-pricing/), [Activepieces](https://www.activepieces.com/blog/intercom-pricing-2026-plans-and-ai-fees-explained)); Chatwoot ([eesel](https://www.eesel.ai/blog/chatwoot-pricing), [Featurebase](https://www.featurebase.app/blog/chatwoot-pricing)); Help Scout and Zendesk ([eesel](https://www.eesel.ai/blog/helpscout-vs-zendesk), [Automation Atlas](https://automationatlas.io/answers/zendesk-pricing-explained-2026/)); tawk.to ([Tidio review](https://www.tidio.com/blog/tawk-to-review/), [CostBench](https://costbench.com/software/live-chat/tawk-to/))
- Error tracking: Sentry ([CubeAPM](https://cubeapm.com/blog/sentry-pricing-review/), [CostBench](https://costbench.com/software/developer-tools/sentry))
- Uptime and status pages: [Better Stack](https://betterstack.com/community/comparisons/free-status-page-tools/), UptimeRobot ([Hyperping](https://hyperping.com/blog/uptimerobot-pricing), [Notifier](https://notifier.so/guides/uptimerobot-pricing-2026/))
- PostHog free tier: [Usercall](https://usercall.co/post/posthog-pricing), [CubeAPM](https://cubeapm.com/blog/posthog-pricing-and-review/)
- Resend plans: [Automation Atlas](https://automationatlas.io/answers/resend-pricing-explained-2026/), [resend.com/pricing](https://resend.com/pricing)
- Google Workspace in Brazil: [eesel (pt)](https://www.eesel.ai/pt/blog/google-workspace-pricing), [Guia Ferramentas Digitais](https://guiaferramentasdigitais.com.br/guias/google-workspace-vale-a-pena/)
- Accounting and opening a company: [Meu Contador Online](https://www.meucontadoronline.com.br/blog/quanto-custa-contador-para-me/), [Agilize](https://agilize.com.br/artigos/preco-medio-contabilidade-mensal-microempresa), [Contabilizei](https://www.contabilizei.com.br/contabilidade-online/quanto-custa-abrir-empresa-com-contabilidade-online/)

- Asaas fees: [blog.asaas.com/taxas-asaas](https://blog.asaas.com/taxas-asaas/)
- Pix Automático: [Olhar Digital, 04 Jun 2025](https://olhardigital.com.br/2025/06/04/pro/agora-e-oficial-banco-central-apresenta-o-pix-automatico/), [Tecnoblog](https://tecnoblog.net/noticias/pix-automatico-chega-em-junho-saiba-como-ira-funcionar/)
- Stripe and Pix: [Finextra](https://www.finextra.com/newsarticle/46431/stripe-businesses-can-now-accept-pix-in-brazil); card rates from a secondary guide, [ParityDeals](https://www.paritydeals.com/blog/best-payment-gateways-brazil-2026/) (confirm on stripe.com/br)
- Trial conversion benchmarks: [Userpilot](https://userpilot.com/blog/free-trial-conversion-rate/), [Sixteen Ventures](https://sixteenventures.com/saas-free-trial-benchmarks/), [ProductLed](https://productled.com/blog/free-trial-conversion-rate)
- Google Cloud egress: [cloud.google.com/storage/pricing](https://cloud.google.com/storage/pricing) (network section)
