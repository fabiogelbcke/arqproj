# Fixed costs (recurring)

**28 October 2026 · analysis for discussion, not decisions** · part of
[What Unio costs](README.md)

What we pay every month whatever the number of offices. These costs don't grow
office by office, but several step up at a certain size (the "When it grows"
columns). Costs that grow with each office are in [per-office.md](per-office.md);
one-off costs in [one-time.md](one-time.md). Every amount names its currency,
monthly unless marked; US$1 = R$5.50.

## Running the product

| Item | Today (per month) | When it grows (per month) | Notes |
| --- | --- | --- | --- |
| Cloud SQL (`db-f1-micro`, 10 GB, backups) | ~US$10 | ~US$25–30 (`db-g1-small`) | [infrastructure.md](../infrastructure.md#costs-approximate-monthly). The next size is likely somewhere past 50–100 active offices; measure first. |
| Global load balancer (A21) | ~US$18–20 + traffic | same | Covered by credits for the first three months. |
| Cloud Run, Build, Artifact Registry, Scheduler | ~US$0 | a few US$ | Within free tiers at pilot scale. |
| Logs and alerts (Cloud Logging and Monitoring) | US$0 | US$0 | 50 GiB of logs a month free; we are far below. |
| Email (Resend) | US$0 | US$20 → US$90 | Free: 3,000 emails a month, 100 a day. Pro: US$20 for 50,000. Scale: from US$90 for 100,000. The 100-a-day cap comes first, around 10 busy offices. |
| Product analytics (PostHog) | US$0 | US$0 at our volume | 1 million events and 5,000 session recordings a month free. |
| Domains (`myunio.app` and others) | ~US$2–4 | same | Paid yearly, averaged per month. An office's own domain is bought by the office; its certificate costs us nothing. |
| **Total** | **~US$30–35 (R$165–190)** | **~US$75–90 (R$410–495) at 100 offices** | |

Only if we ever ask Google for full Drive access instead of `drive.file` (not
recommended): the CASA security assessment, **~US$540 a year** (~R$250 a month),
every year. See [storage-strategy.md](../storage-strategy.md#where-we-are).

## Running the business

| Item | Options (per month unless marked) | Suggested now | Later |
| --- | --- | --- | --- |
| **Support chat on the site and panel** | See the comparison below | **WhatsApp Business app** (free) + **Crisp Free** or **Chatwoot Hacker** (US$0) | Crisp Mini (US$45) or Chatwoot Startups (US$19 per agent) |
| **Error tracking** | Sentry Developer US$0 (1 user, 5,000 errors); Team US$26–29 (50,000 errors) | Cloud Logging's alerts (US$0) | Sentry Team, when a second developer joins |
| **Uptime check and status page** | Better Stack free (10 monitors, 1 status page on our subdomain); UptimeRobot Solo US$12–13 (its free plan is non-commercial only) | Better Stack free | Better Stack paid, from ~US$30 |
| **Email accounts** (`contato@`, `suporte@myunio.app`) | Google Workspace Business Starter US$7–8.40 per user (~R$35–45, plus 6.38% IOF on an international card) | 1–2 users | 1 per person |
| **AI for the business** (support drafts, weekly digest, sales research) | US$5–40 in API costs at pilot scale | Through Fabio's subscription first | See [ai-for-the-business.md](../ai-for-the-business.md#what-to-build-first) |
| **Accountant** (Simples Nacional) | R$150–200 with an online firm (Contabilizei, Agilize, Conube; prices to confirm); a traditional office R$300–600 | **Needed from the first invoice** (we're not a company yet) | — |
| **Lawyer**: reviews of terms and contracts | R$0 for now | Fabio's mother, for free | A paid arrangement with her once there is revenue; not in the simulation yet |

### Support chat tools compared

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
knowledge base is worth writing. Chatwoot fits best if WhatsApp updates
([per-office.md](per-office.md#extras-an-office-could-add)) are built, since one
inbox would then hold both.

## By size

What the simulation ([margin.md](margin.md)) assumes, per month. The steps are
guesses at when each tool becomes worth paying for; change them in
[simulate.py](simulate.py).

| | Up to ~14 offices | 15–59 offices | 60–149 offices | 150+ offices |
| --- | --- | --- | --- | --- |
| Product (database, load balancer, email, domains) | US$32 | US$52–57 | US$75 | US$145 |
| Support chat | US$0 | US$45 (Crisp Mini) | US$95 (Crisp Essentials) | US$95 |
| Error tracking and uptime | US$0 | US$26 | US$56 | US$56 |
| Email accounts | US$8 (1 user) | US$16 (2) | US$24 (3) | US$32 (4) |
| AI for the business | US$0 | US$15 | US$50 | US$50 |
| Accountant | R$150 | R$150 | R$200 | R$200 |
| **Total** | **~R$370** | **~R$1,000** | **~R$1,850** | **~R$2,280** |

Not included: salaries (Fabio's included), marketing, and Fabio's own Claude
subscription.
