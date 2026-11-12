# WhatsApp: client updates and a file bot

**28 October 2026, file bot and October prices added 1 November 2026 · research
for discussion, not decisions**

Two separate features share one WhatsApp setup (a Meta business account, a
number, a webhook):

1. **Client updates by WhatsApp**, beside today's emails. [`future-ideas.md`](future-ideas.md)
   lists them as "potentially soon".
2. **A file bot**: staff forward files they received in other WhatsApp chats
   to a Unio number, and the bot saves them into a project stage, in the
   office's Drive. That is how clients and suppliers send files in Brazil.
   Raised by Fabio, 1 Nov 2026.

Today's client updates are emails (decision A32: new files, a stage completed or
reopened, the project completed, a meeting scheduled, changed or removed;
batched 45 minutes, at most 2 hours).

**Client updates by WhatsApp were agreed on 2 Nov 2026 as decision A47** (in the
[register](multi-tenant-implementation-plan.md#2-decision-register)) and built
behind the `whatsapp_updates` feature: one Unio number, Meta directly, each
client choosing email, WhatsApp or both, staff-added numbers confirmed by the
client with a button, SAIR for every project, offices' own numbers left out. The
register is the source for those (the texts were revised on 9 Nov 2026 after
Fabio's answers); this page stays the research behind them.
The file bot is still undecided.

Prices come from Meta's pricing page and secondary sources checked on 28 Oct and
1 Nov 2026. **Confirm them on Meta's rate card** (linked below). Meta can change
prices on the first day of each quarter.

## How WhatsApp business messages work

- **Templates.** A message to someone who hasn't written to us in the last
  24 hours must be a **template** that Meta approved beforehand: fixed text with
  slots, like "Novidades no projeto {{1}}: {{2}}. Veja: {{3}}". A slot can't
  hold line breaks, so a multi-stage summary becomes one line.
- **The 24-hour window.** Once someone writes to us, we may reply freely
  (text, lists, buttons) for 24 hours: these are **service messages**. The file
  bot only ever replies, so it needs no templates.
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
  sent inside an open 24-hour window, and each number gets **1,000 free service
  messages a month**, then pays from the 1,001st.
- **Messages people send us are free**, files included.

## Cost

Approximate rates to Brazilian numbers (USD per message delivered):

| Category | Meta's price | Through Twilio (+US$0.005) |
| --- | --- | --- |
| Utility (our updates) | ~US$0.007–0.008 (Meta's page showed 0.68¢ on 1 Nov) | ~US$0.012–0.013 |
| Marketing | ~US$0.0625 | ~US$0.068 |
| Service (bot replies) | First 1,000 a month per number free; then the rate card's price (not checked; assume about the utility price) | + US$0.005 each way, inbound files too |

**Updates.** A busy office: 20 active projects, 2 clients each, 8 updates a
month each, **320 messages**:

- **~US$2.20–2.60/month** sending directly through Meta;
- ~US$4.20 through Twilio;
- R$12–23 at R$5.50 to the dollar.

**File bot.** About 3 replies per forward (which project, which stage, done; one
more when the project isn't among the suggestions). All offices share the Unio
number's 1,000 free replies: 20 offices forwarding 20 times a month is ~1,200
replies, **~US$1.40/month for everyone**. The files themselves cost nothing to
receive.

**Cloud.** Downloading a file from Meta is inbound traffic (free) and uploading
it to Drive goes to a Google API. A 100 MB file is about 20 seconds of Cloud
Run; 1,000 files a month stay inside Cloud Run's and Cloud Tasks' free
allowances. The number costs ~R$17–50 a month (see [the number](#the-number)). Meta business
verification is free.

That's small enough to include in a plan, or to sell as an extra (see
[pricing-and-trials.md](pricing-and-trials.md); its effect on the margin is in
[costs/margin.md](costs/margin.md)). The real cost is building it (below).

## Choices to make

### 1. Whose number sends

| Option | Pros | Cons |
| --- | --- | --- |
| **One Unio number**, the office named in each message | One Meta business verification, one set of templates, quick to start; the file bot can tell offices apart by who is writing | Clients see "Unio", not their architect, in their chat list |
| **Each office's own number** (Meta's Embedded Signup) | Messages come from the office: the brand the client knows | Each office verifies its business and number with Meta, and a number used here can't also be its ordinary WhatsApp app number |

Suggested: **start with one Unio number** for both features. Offices that want
their own can move later.

### 2. Provider

| Option | Fee | Notes |
| --- | --- | --- |
| **Meta Cloud API directly** | Meta's price only | Free hosting by Meta; we handle templates, webhooks and Meta business verification ourselves |
| **Twilio** | + US$0.005 per message, both ways | Mature APIs and docs; same Meta rules underneath. Charges for every file forwarded to the bot too |
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
- The privacy policy (a draft today) names Meta as a processor of these
  messages and of files forwarded to the bot.

### 4. What the message says

One utility template per kind of update, in Portuguese, linking to the page.
For example: "Escritório Alinea · Casa Jardim: 3 arquivos novos na etapa
Estudo Preliminar. Veja em alinea.myunio.app/casa-jardim". The same 45-minute
batching applies, so one message covers a burst of uploads. No promotional
text, or it becomes marketing.

## Setting up with Meta (outside the code)

Both features share this setup. No setup or monthly fee and no App Review (we
send as our own business; App Review is for companies that connect other
businesses' numbers, which offices' own numbers would need later).

| Step | What it is | Time |
| --- | --- | --- |
| Meta business portfolio | business.facebook.com account for Unio | ~15 min |
| Developer app with WhatsApp | Asks for a privacy policy URL; ours mentions WhatsApp first | ~30 min |
| Phone number | A number not on WhatsApp, confirmed once by SMS or voice call (below) | ~10 min |
| Display name | "Unio", reviewed by Meta | Usually 1–2 days |
| Payment method | A card in WhatsApp Manager, or BRL billing | ~5 min |
| Templates | `unio_atualizacao` (button "Abrir o projeto"), `unio_atualizacao_reuniao` (also "Adicionar à agenda"), `unio_boas_vindas`, `unio_convite` (buttons "Quero receber" / "Não quero"), in the approved Portuguese texts. Each link button's address is `https://myunio.app/w/{{1}}` (staging's test templates: staging's own address) | Minutes, at most ~24 h |
| Access token and webhook | A permanent token in Secret Manager, our webhook registered with Meta | Part of the coding |
| Business verification (later) | Below | A few days to ~2 weeks |

**Building needs no number yet.** Meta's free test number, created with the
app, messages up to 5 numbers we register, which is enough to build and test
both features.

### The number

Meta doesn't sell numbers: we bring one. Anything that can receive one SMS or
voice call works, if it isn't on WhatsApp already.

| Option | Cost | Notes |
| --- | --- | --- |
| Brazilian mobile SIM on a controle or postpaid plan | ~R$30–50/month | Simplest. Not prepaid: an unused prepaid line is cancelled and its number given to someone else, and with it our WhatsApp account |
| Brazilian landline or VoIP number | ~R$10–30/month | WhatsApp verifies by voice call; no chip to keep |
| A number bought through Twilio | ~US$1–15/month | Twilio registers the sender. A Brazilian number needs regulatory documents; a US one shows clients a foreign +1. Plus US$0.005 a message |

Suggested: the test number while building, then a **Brazilian VoIP/landline
number or a controle SIM** in Unio's name before going live, kept for good: the
number is the WhatsApp account, and losing it loses every client's chat.

**Brazilian virtual-number providers** (their own sites' prices, checked
2 Nov 2026; none of this is an endorsement):

| Provider | Kind | Price | Notes |
| --- | --- | --- | --- |
| [Salvy](https://salvy.com.br/numerovirtualmovel) | Virtual **mobile** number | R$29.90/month | Sold for WhatsApp through Meta's official API; the code arrives by SMS and webhook. No calls or data. No lock-in advertised |
| [Numio](https://numio.com.br/) | Virtual landline | R$25.90 monthly, R$16.90 a month paid yearly | Anatel-licensed numbering (TIP Brasil); pick the DDD; verification by call, the code shown in their panel. Sells for the WhatsApp Business app, also links an "API oficial" page |
| [Avoip](https://avoip.com.br/numeros-virtuais) | Virtual landline | R$17/month (receiving), R$57 with unlimited calls | DDD of our choice; sold for WhatsApp Business |
| [Voipi](https://www.voipi.com.br/) | Virtual landline + SIP account | R$25 monthly, R$19.90 a month yearly | Outgoing calls charged per minute |
| [Center](https://www.cent3r.com/planos-e-precos) | Virtual landline | R$19.90/month, R$149.90 every 6 months | Sold for WhatsApp Business |
| [Directcall](https://directcall.com.br/produtos/numero-fixo-ou-virtual-para-whatsapp/) | Virtual landline | R$25/month plus activation | **36-month lock-in**; any DDD; delivered in 3 business days |
| [Vono](https://www.falevono.com.br/servicos/numero-fixo/) | Virtual landline | From R$29.90/month | All 67 DDDs; also 0800 and virtual PBX |

Most of these sell for the WhatsApp Business **app**. Meta's API only needs
the number to receive one verification SMS or call, so a landline should work,
but **ask the provider before signing**: Meta can refuse a particular number.
Prefer no lock-in, a DDD of our choice and the number in Unio's name. Salvy is
the one built for the API; Numio has licensed numbering and no lock-in.

### Business verification and the CNPJ

Not needed to start. Without it the API works the same, limited to **250
different people a day** and 2 numbers, plenty for the pilot. (Still to check:
whether clients see "Unio" or the bare number before verification, until they
save the contact.)

Verification needs a registered business: Meta compares the name with official
documents (in Brazil, the CNPJ card and a proof of address in the company's
name) and with our website. A CPF doesn't qualify. It raises the limit to 1,000
people a day, rising as long as people don't block or report us, and is needed
for more numbers or offices' own numbers. Done later on the same account and
number. Unio needs a CNPJ anyway to charge offices (Asaas, invoices); whether
a MEI can hold this activity is for the accountant.

### Rules that can cost us the number

- **Quality rating.** Many blocks or reports lower our limits, then block the
  number. Hence opt-in by the client and "Responda SAIR" in every message.
- **Templates stay utility.** One promotional line gets a template
  recategorized as marketing, at about 8× the price.

## Client updates: how it fits the app

A second delivery channel on the existing pipeline (plan section 14):

```
File uploaded / stage completed
        │
        ▼
ProjectEvent ──► NotificationBatch (45 min quiet, 2 h max)       ← exists
        │
        ▼  batch due (maintenance, every 10 minutes)
For each recipient:
   ├── email     ──► Resend                                      ← exists
   └── WhatsApp  ──► Meta Cloud API, approved template           ← new
                          │
                          ▼
                 Meta's webhook: delivered / failed, or "SAIR"   ← new
```

Batching, the summary, the recheck before sending and the one-delivery-per-
recipient rule (`backend/notifications/digest.py`) stay as they are. New: a
phone number, consent and channel on the recipient, a WhatsApp sender beside
`backend/notifications/email.py`, the one-line form of the summary for the
template, and the webhook.

## The file bot

### What staff see

1. **Once, in the painel:** "Conectar WhatsApp" shows a link
   (`wa.me/<Unio number>?text=Unio K7QF-2MXR-9TCD`; a QR code on a computer).
   Tapping it opens a chat with Unio with the code typed; sending it links that
   phone number to the staff account and saves Unio in their chats. Nobody types
   the code, so it can be long: random, at least 60 bits, single use, expiring
   in 15 minutes, only its hash kept (as owner links are). Wrong codes are
   limited per sending number, and the painel shows which number was linked.
2. A client sends them a PDF in another chat. They tap **Encaminhar** and pick
   Unio, several files at once if they like.
3. The bot: "Recebi 3 arquivos. Para qual projeto?", with a list of their
   recent projects (below).
4. "Salvar em Projeto Executivo?" with the project's current stage and "Outra
   etapa" (then a list of the project's stages).
5. "Pronto: 3 arquivos salvos em Casa Jardim › Projeto Executivo." The files
   are in the office's Drive, the page shows them on its next load (A10), and
   the client update goes out through the usual batch.

### Choosing the project and the stage

Staff never name a project or stage from memory: the bot offers choices to tap,
and typing only narrows a list. A WhatsApp list holds at most 10 rows and three
buttons fit beside a message, which shapes each step.

- **Office.** Only for someone in two or more offices, and asked first. Every
  list after it shows that office's projects only.
- **Repeat the last choice.** If the same person saved to a stage in the last
  2 hours, the bot starts with "Salvar também em Casa Jardim › Projeto
  Executivo?" and the buttons "Sim" and "Outro projeto". Files for one project
  tend to come in bursts.
- **Their projects, not the office's.** The list is this person's recent
  projects (ones they uploaded to, changed or forwarded to lately), then the
  office's most recently changed, so two architects in one office see different
  lists: 7 projects, then "Ver mais" (the next 7), "Buscar projeto" and
  "Escolher no site" (below), which fills the 10 rows.
- **Search.** After "Buscar projeto", or after one "Ver mais", the bot asks for
  part of the name. The search ignores accents and case, matches part of a word,
  and looks at the project's name, its client and its address
  (Localização). It answers with the matches to tap, never picking one itself:
  one match is still confirmed, none gets "Não encontrei. Tente outra palavra."
  It is ordinary database search, no AI.
- **On the site.** "Escolher no site" sends a link that opens
  a small mobile page, for that conversation only, with the office's projects,
  a search box and the stages. The choice made there continues the chat, so an
  office with 50 active projects isn't paged through 7 at a time.
- **Stage.** The project's current stage as a button, "Outra etapa" for a list
  of the project's stages by their page names. More than 10 stages: the 9
  around the current one and "Ver todas".

Guessing the project from the file name or caption, with or without AI, would
only add a suggestion at the top ("Parece ser Casa Jardim: salvar lá?"),
confirmed with a tap like the rest.

### How it works

A bot is a phone number connected to our server instead of a phone. Meta sends
every message the number receives to a web address of ours (a webhook), and we
answer through Meta's API.

```
Staff's WhatsApp ──► Meta ──► POST /api/whatsapp/webhook   (Meta's signature checked)
                                 │  store the message, keyed by its id: a repeat is harmless
                                 │  answer 200 at once
                                 ▼
                          Cloud Tasks queue                ← new infrastructure
                                 │  ~10 s after the last file, so a forward of five is one group
                                 ▼
                          Worker (same Cloud Run service, an authenticated endpoint)
                            ├─ phone number ──► staff member ──► office (tenant)
                            ├─ conversation step: choosing the project / the stage
                            ├─ replies with lists and buttons through Meta
                            └─ stage chosen: for each file
                                 download from Meta ──► resumable upload into the stage's
                                 Drive folder with the office's grant (drive.file)
```

- **Why a queue.** Meta wants a quick answer, and Cloud Run barely runs a
  request's work once it has answered. The 10-minute maintenance run (A09) is
  too slow for a chat. Cloud Tasks calls our worker back within seconds, with
  retries, and is free at this volume. A09 already allows "a queue when
  needed"; adding it changes that row, so it is recorded before coding.
- **Uploads go through our server.** Page uploads go from the browser straight
  to Google (`backend/web/page_uploads.py`); here the bytes come from Meta, so
  the worker streams them to Drive in chunks, never holding a whole file. Same
  rules as page uploads: any staff member, at most 100 MB a file, which is also
  the most a bot can receive. A larger file (people can send 2 GB in the app)
  gets "Arquivo grande demais: envie pelo site".
- **Nothing is kept.** No copy of the file stays with us. Meta lets us download
  a received file for 7 days; files waiting for an answer are dropped after
  24 hours, with a message saying so.
- **Names and versions.** A document keeps its name. A photo has none: it gets
  the caption, else `Foto WhatsApp 2026-11-01 14h32.jpg`. A name matching a
  document in the stage gets the page's question, "É uma nova versão de
  Planta.pdf?" (A25).
- **Who may use it.** Only linked numbers; anyone else gets one reply saying
  the number isn't linked to an account. Removing someone from the office, or
  "Desconectar" in the painel, unlinks their number. Someone in two offices is
  asked which.
- **Quality.** Forwarding passes on the file the person received, not a
  recompressed copy. A file sent as "Documento" (usual for PDFs and DWGs)
  arrives original, name and all; a photo arrives as compressed as it already
  was in their chat. Still to test: whether an "HD" photo reaches the bot at HD
  size.
- **Errors.** As everywhere (AGENTS.md, plan section 17): the reply says what
  failed and what to do, in Portuguese, with a support ID; the detail goes to
  the log with the office and the step.

### What building it means

About **3–5 weeks**, after the client updates (they set up the Meta account,
the number and the webhook):

- linking a phone number in the painel, and unlinking;
- the webhook, the queue and the worker, with the conversation state (a table:
  sender, office, waiting files, step, expiry);
- project and stage choice (recent lists per person, search, the site picker),
  grouping of forwarded files, the server-side upload into Drive, names and
  versions;
- operator dashboard counts (A38) and the support log lines (section 17);
- tests with a fake Meta, as the email tests use a collecting fake.

## Client updates: what building it means

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
   in Brazil), and whether their staff would forward files to a bot.
2. Decide one Unio number vs offices' own.
3. Decide whether each is in every plan or a paid extra.
4. For the bot: approve Cloud Tasks (a change to A09), and record in the
   register that the bot's uploads pass through Cloud Run (A31 says page
   uploads never do; the bot's bytes come from Meta, not a browser).
5. Get the number (above) in Unio's name; verification waits for the CNPJ.

## Sources

- Meta pricing: [WhatsApp Business Platform pricing](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing) (rate cards, BRL billing, quarterly changes, the 1,000 free service messages and the October 2026 changes)
- Received files: [WhatsApp media](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/media) (100 MB inbound, 7 days to download, downloads need our token)
- Brazil rates: [Message Central](https://www.messagecentral.com/blog/whatsapp-business-api-pricing-in-brazil), [Monty Mobile 2026 guide](https://montymobile.com/newsroom/whatsapp-business-api-pricing-the-complete-2026-cost-guide-for-enterprise-teams/)
- Per-message billing since July 2025: [YCloud](https://www.ycloud.com/blog/whatsapp-api-pricing-update), [respond.io](https://respond.io/help/whatsapp/whatsapp-pricing)
- October 2026 changes and Twilio's fee: [Twilio notice](https://support.twilio.com/hc/en-us/articles/53100462475931-Notice-Changes-to-WhatsApp-s-Pricing-October-2026)
- BRL billing: [Zenvia FAQ](https://zenvia.movidesk.com/kb/en/article/600343/frequently-asked-questions-new-whatsapp-business-pricing-rules-2)
- Messaging limits and verification: [Uptail](https://uptail.ai/blog/whatsapp-business-message-limits-2026-broadcast-caps-tier-progression-what-happens-when-you-hit-the-ceiling), [Wassenger](https://wassenger.com/blog/whatsapp-business-api-without-verification), [Green API](https://green-api.com/en/blog/2025/wa-buisness-change-its-messaging-limits/), [Meta: about the platform](https://developers.facebook.com/documentation/business-messaging/whatsapp/about-the-platform)
- Number providers: the links in their table; [Zavu's guide](https://www.zavu.dev/pt/blog/comprar-numero-virtual)
- Template categories: [360dialog](https://docs.360dialog.com/whatsapp-api/template-messaging), [Exotel](https://developer.exotel.com/docs/whatsapp-support/template-categories)
