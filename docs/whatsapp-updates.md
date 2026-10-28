# WhatsApp updates: what it would take

**28 October 2026 · research for discussion, not decisions**

[`future-ideas.md`](future-ideas.md) lists WhatsApp updates as "potentially
soon", with provider, cost and consent to work out first. This is that first
pass. Today's client updates are emails (decision A32: new files, a stage
completed or reopened, the project completed, a meeting scheduled, changed or
removed; batched 45 minutes, at most 2 hours). Nothing here is decided; a choice
goes into the [register](multi-tenant-implementation-plan.md#2-decision-register).

Prices come from secondary sources checked on 28 Oct 2026. **Confirm them on
Meta's rate card** (linked below). Meta can change prices on the first day of
each quarter.

## How WhatsApp business messages work

- **Templates.** A message to someone who hasn't written to us in the last
  24 hours must be a **template** that Meta approved beforehand: fixed text with
  slots, like "Novidades no projeto {{1}}: {{2}}. Veja: {{3}}".
- **Categories decide the price.**
  - **Utility:** about something the person already did or asked for. Project
    updates fit here.
  - **Marketing:** anything promotional. One promotional line turns a template
    into marketing, at about 8× the price.
  - **Authentication:** one-time codes.

  Meta can recategorize a template.
- **Opt-in.** People must agree to receive WhatsApp messages from us, and be
  able to stop them.
- **Billing per message**, since July 2025. Brazilian accounts are billed in
  BRL from July 2026. From 1 Oct 2026, Meta also charges for utility templates
  and replies sent inside an open 24-hour window (Twilio's notice).

## Cost

Approximate rates to Brazilian numbers (USD per message delivered):

| Category | Meta's price | Through Twilio (+US$0.005) |
| --- | --- | --- |
| Utility (our updates) | ~US$0.008 | ~US$0.013 |
| Marketing | ~US$0.0625 | ~US$0.068 |

A busy office: 20 active projects, 2 clients each, 8 updates a month each,
**320 messages**:

- **~US$2.60/month** sending directly through Meta;
- ~US$4.20 through Twilio;
- R$14–23 at R$5.50 to the dollar.

That's small enough to include in a plan, or to sell as an extra (see
[pricing-and-trials.md](pricing-and-trials.md); its effect on the margin is in
[costs/margin.md](costs/margin.md)).

## Choices to make

### 1. Whose number sends

| Option | Pros | Cons |
| --- | --- | --- |
| **One Unio number**, the office named in each message | One Meta business verification, one set of templates, quick to start | Clients see "Unio", not their architect, in their chat list |
| **Each office's own number** (Meta's Embedded Signup) | Messages come from the office: the brand the client knows | Each office verifies its business and number with Meta, and a number used here can't also be its ordinary WhatsApp app number |

Suggested: **start with one Unio number.** Offices that want their own can move
later.

### 2. Provider

| Option | Fee | Notes |
| --- | --- | --- |
| **Meta Cloud API directly** | Meta's price only | Free hosting by Meta; we handle templates, webhooks and Meta business verification ourselves |
| **Twilio** | + US$0.005 per message, both ways | Mature APIs and docs; same Meta rules underneath |
| **Brazilian providers** (Zenvia, Take Blip and others) | Varies, often a monthly plan | Portuguese support, BRL invoices |

Suggested: **Meta Cloud API directly**, behind the same kind of adapter as
email (A17). Nothing in our volume needs a middleman.

### 3. Consent and choice (LGPD and Meta's rules)

- A client adds a phone number and ticks "Receber pelo WhatsApp" on the project
  page, beside the existing "Novidades por e-mail" (A32). We keep the consent
  time and its source.
- The first message confirms the opt-in, and every message says how to stop
  ("Responda SAIR"). Replying SAIR stops them at once, through Meta's webhook.
- Staff can add a client's number, but the client opts in from the page.
  Unsolicited WhatsApp messages get numbers reported and blocked.
- Each recipient chooses email, WhatsApp or both, so nobody gets everything
  twice unasked.

### 4. What the message says

One utility template per kind of update, in Portuguese, linking to the page.
For example: "Escritório Alinea · Casa Jardim: 3 arquivos novos na etapa
Estudo Preliminar. Veja em alinea.myunio.app/casa-jardim". The same 45-minute
batching applies, so one message covers a burst of uploads. No promotional
text, or it becomes marketing.

## What building it means

About **1–2 weeks** of work:

- a WhatsApp adapter beside email in the notification sender (A17, A32), with
  per-message idempotency;
- the phone number and opt-in on the page and in the Projeto dialog, with
  number validation for Brazil;
- Meta setup: business verification, the number, templates submitted and
  approved (allow a week for Meta's side);
- a webhook for delivery status and "SAIR";
- operator dashboard counts (A38) and the support log lines (section 17).

**Before starting:**
1. Ask pilot offices whether their clients would prefer WhatsApp (likely yes
   in Brazil).
2. Decide one Unio number vs offices' own.
3. Decide whether it's in every plan or a paid extra.

## Sources

- Meta pricing: [WhatsApp Business Platform pricing](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing) (rate cards, BRL billing, quarterly changes)
- Brazil rates: [Message Central](https://www.messagecentral.com/blog/whatsapp-business-api-pricing-in-brazil), [Monty Mobile 2026 guide](https://montymobile.com/newsroom/whatsapp-business-api-pricing-the-complete-2026-cost-guide-for-enterprise-teams/)
- Per-message billing since July 2025: [YCloud](https://www.ycloud.com/blog/whatsapp-api-pricing-update), [respond.io](https://respond.io/help/whatsapp/whatsapp-pricing)
- October 2026 changes and Twilio's fee: [Twilio notice](https://support.twilio.com/hc/en-us/articles/53100462475931-Notice-Changes-to-WhatsApp-s-Pricing-October-2026)
- BRL billing: [Zenvia FAQ](https://zenvia.movidesk.com/kb/en/article/600343/frequently-asked-questions-new-whatsapp-business-pricing-rules-2)
- Template categories: [360dialog](https://docs.360dialog.com/whatsapp-api/template-messaging), [Exotel](https://developer.exotel.com/docs/whatsapp-support/template-categories)
