# What Unio costs, and what's left

**28 October 2026 · analysis for discussion, not decisions**

Every cost of running Unio, split by how it behaves, and a rough simulation of
the margin. Nothing here is decided: a choice taken from these documents goes
into the [decision register](../multi-tenant-implementation-plan.md#2-decision-register)
and the [changelog](../decision-changelog.md) like any other. Prices and plans
are in [pricing-and-trials.md](../pricing-and-trials.md).

Every amount names its currency, monthly unless marked. Amounts convert at
**US$1 = R$5.50**. Third-party prices were checked on 28 Oct 2026 against the
sources below; several come from secondary sources, so confirm them on the
provider's own page before relying on them.

## The documents

| Document | What it holds | Behaves like |
| --- | --- | --- |
| [fixed.md](fixed.md) | Running the product (database, load balancer, email, domains) and the business (support chat, error tracking, email accounts, accountant) | **Recurring, fixed**: paid whatever the number of offices; steps up at a few sizes |
| [per-office.md](per-office.md) | Download traffic and emails of each office, paid extras (own storage, WhatsApp, AI assistant), payment fees, taxes | **Recurring, grows with offices or revenue** |
| [one-time.md](one-time.md) | Opening the company, the lawyer, building each extra | **Once** (money or weeks of work) |
| [margin.md](margin.md) | Rough simulations: margin at 5 to 200 offices, by price, tax annex and extras; break-even | Calculated by [simulate.py](simulate.py) from the three above |

Companion analyses: [storage](../storage-strategy.md),
[WhatsApp](../whatsapp-updates.md), [AI for the business](../ai-for-the-business.md),
[infrastructure.md](../infrastructure.md) (what runs today) and the
[infrastructure cost comparison](../infrastructure-cost-comparison.md).

## In short

- **Fixed:** ~R$520 a month today (US$30–35 of product, the accountant, one
  email account), ~R$1,200 from about 15 offices (paid support and monitoring
  tools), ~R$2,250 at 100.
- **Per office:** ~R$14 a month (downloads and emails); ~R$27 with WhatsApp and
  the AI assistant. Plus payment fees (~R$2 a payment through Asaas) and
  **taxes, the largest per-office cost**: 6% of revenue under Simples Anexo III,
  15.5% or more under Anexo V.
- **One-off:** ~R$6,500 in cash (company and lawyer, the lawyer still a
  guess), plus weeks of building for each extra.
- **Margin** ([margin.md](margin.md)): at an average R$242 a month per office,
  fixed costs are covered from about 6 paying offices, and **about 75% of
  revenue is left from 50 offices** (66% under Anexo V), before salaries and
  marketing. What decides it is the price and the tax annex, not
  infrastructure.

## Sources

- Google Cloud: [infrastructure.md](../infrastructure.md#costs-approximate-monthly); egress, [cloud.google.com/storage/pricing](https://cloud.google.com/storage/pricing) (network section)
- Support chat: Crisp ([Featurebase](https://www.featurebase.app/blog/crisp-pricing), [Drag](https://www.dragapp.com/blog/crisp-pricing/)); Intercom ([Drag](https://dragapp.com/blog/intercom-pricing/), [Activepieces](https://www.activepieces.com/blog/intercom-pricing-2026-plans-and-ai-fees-explained)); Chatwoot ([eesel](https://www.eesel.ai/blog/chatwoot-pricing), [Featurebase](https://www.featurebase.app/blog/chatwoot-pricing)); Help Scout and Zendesk ([eesel](https://www.eesel.ai/blog/helpscout-vs-zendesk), [Automation Atlas](https://automationatlas.io/answers/zendesk-pricing-explained-2026/)); tawk.to ([Tidio review](https://www.tidio.com/blog/tawk-to-review/), [CostBench](https://costbench.com/software/live-chat/tawk-to/))
- Error tracking: Sentry ([CubeAPM](https://cubeapm.com/blog/sentry-pricing-review/), [CostBench](https://costbench.com/software/developer-tools/sentry))
- Uptime and status pages: [Better Stack](https://betterstack.com/community/comparisons/free-status-page-tools/), UptimeRobot ([Hyperping](https://hyperping.com/blog/uptimerobot-pricing), [Notifier](https://notifier.so/guides/uptimerobot-pricing-2026/))
- PostHog free tier: [Usercall](https://usercall.co/post/posthog-pricing), [CubeAPM](https://cubeapm.com/blog/posthog-pricing-and-review/)
- Resend plans: [Automation Atlas](https://automationatlas.io/answers/resend-pricing-explained-2026/), [resend.com/pricing](https://resend.com/pricing)
- Google Workspace in Brazil: [eesel (pt)](https://www.eesel.ai/pt/blog/google-workspace-pricing), [Guia Ferramentas Digitais](https://guiaferramentasdigitais.com.br/guias/google-workspace-vale-a-pena/)
- Accounting and opening a company: [Meu Contador Online](https://www.meucontadoronline.com.br/blog/quanto-custa-contador-para-me/), [Agilize](https://agilize.com.br/artigos/preco-medio-contabilidade-mensal-microempresa), [Contabilizei](https://www.contabilizei.com.br/contabilidade-online/quanto-custa-abrir-empresa-com-contabilidade-online/)
- Asaas fees: [blog.asaas.com/taxas-asaas](https://blog.asaas.com/taxas-asaas/)
- Simples Nacional annexes and brackets: Lei Complementar 123/2006, annexes III and V as amended by LC 155/2016 ([planalto.gov.br](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm)); confirm with the accountant
- Storage, WhatsApp and AI prices: the sources in each companion analysis
