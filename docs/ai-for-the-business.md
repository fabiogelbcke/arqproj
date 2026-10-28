# Using Claude across the business

**28 October 2026 · analysis for discussion, not decisions**

How AI (Claude in particular) can help Unio beyond writing the product's code:
sales, marketing, customer support, and turning feedback into improvements. It
covers what to do, what it costs, and what to keep a human on. Companion to
[pricing-and-trials.md](pricing-and-trials.md) and plan sections 21–22.
Nothing here is decided; adopted pieces go into the
[decision register](multi-tenant-implementation-plan.md#2-decision-register).

## Prices used

Claude API, per million tokens (Anthropic first-party, October 2026):

| Model | Input | Output | Good for |
| --- | --- | --- | --- |
| Claude Opus 5.5 | US$4 | US$20 | Hard reasoning: code changes, analysis, sales research |
| Claude Sonnet 5.5 | US$2 | US$10 | Everyday writing, support replies, summaries |
| Claude Haiku 5.5 | US$0.10 | US$0.50 | High-volume sorting: tag, route, detect language |

Ways to pay less:
- **Batch API:** half price, results within hours. Good for overnight jobs.
- **Prompt caching:** reading a repeated prefix (help docs, product facts) costs
  about a tenth.

A token is roughly ¾ of a word, so 1,000 tokens is about 750 words. These are
API prices. **Interactive use** (Claude Code, the Claude apps) is paid through
the subscription Fabio already has, at no extra cost per use until its limits.

## 1. Customer support

**What it can do**
- **A help center written from the code and docs.** The repo already records
  how every feature works (the plan, rewrite steps, screen text). Claude drafts
  articles in Portuguese, written for architects, not engineers ("Como enviar
  uma nova versão de um arquivo"). Then they're kept in sync: when a PR changes
  a feature, draft the article change in the same PR.
- **Draft replies to support emails**, sent by a person after a quick read.
  Claude gets:
  - the help articles;
  - the office's plan and state (from the operator dashboard, A38);
  - for a support code, the log line it points to (A38 already finds it).

  It answers in the office's language with the steps to fix the problem, and
  never shows log detail to the customer (AGENTS.md "User-facing errors").
- **Sorting the inbox** (Haiku): bug, how-to, billing, feature request; urgent
  or not.
- **Later: an assistant inside the panel** ("Como faço para…?") answering from
  the help center, with a "falar com uma pessoa" button.

**Cost.** A drafted reply is about 6,000 tokens in (help articles cached) and
800 out:
- on Sonnet 5.5, about **US$0.01–0.02 per reply**;
- 300 conversations a month is **US$3–6**;
- the in-panel assistant at 1,000 questions a month is about **US$10–20**.

For comparison, Intercom's Fin charges about **US$0.99 per resolved
conversation**, plus seats and a monthly minimum. Building our own is cheaper per
answer but costs building time; Fin is a reasonable stopgap if support volume
arrives before we have time.

**Keep a human on:** anything about billing or money; complaints; anything
touching a client's files or privacy; the first months of replies, until the
drafts prove reliable.

## 2. Turning feedback into improvements (the loop we already run)

This already works for the product: Fabio describes changes, Claude Code builds
them in PRs, Codex reviews, CI tests, Fabio merges. It can be widened.

1. **Collect.** Support emails, pilot interviews, in-app comments, PostHog
   (where people stop or repeat actions), and errors in the logs.
2. **Weekly digest** (Opus, batch). Cluster what came in:
   - "3 offices couldn't find 'Ocultar do cliente'";
   - "2 upload failures from the same office, same error".

   Each item links to its sources, with a suggested change and its size.
3. **Fabio picks.** The digest suggests; a person decides what goes on the list
   (future-ideas or the plan).
4. **Build.** Claude Code turns a picked item into a PR, with tests and the
   decision records updated, exactly as now.
5. **Close the loop.** When the PR merges, draft a short reply to the offices
   that asked ("O que você pediu já está no ar"). Small offices love this, and
   it costs nothing.

**Also worth automating:**
- a nightly check of production errors (support codes from the logs, grouped,
  with a likely cause), sent as one message, with no action taken;
- a monthly report per office for us: usage, projects stuck in a stage, clients
  who never opened their page. These are signals for support or churn.

**Cost.**
- Weekly digest over a few hundred items: **US$1–3 per run** on Opus at batch
  prices.
- Nightly error check: **cents**.
- Building fixes: through the subscription; heavier use may need a higher plan.

## 3. Marketing

**What it can do**
- **Content for architects in Portuguese:** Instagram and LinkedIn posts, short
  articles (how to share files with clients, organizing a project's stages,
  what to send at each stage), and SEO pages for "portal do cliente para
  arquitetos".
- **Case studies from real projects**, only with the office's written
  permission, from what's already on the page: stages, timeline, a quote from
  the architect.
- **Landing pages and emails:** variants of Unio's page for A/B tests, and a
  welcome sequence for new offices.
- **Visuals:** Claude drafts layouts and copy; images come from real screens
  (`make screenshots` already produces them) rather than generated pictures,
  which look fake to designers.

**Cost:** negligible in API terms (**under US$5/month** for heavy use). The real
cost is review time. Every published piece is read by a person: our brand, and
architects notice generic AI text instantly.

## 4. Sales

**What it can do**
- **Lead research.** Given a list of offices (from Instagram, CAU registrations
  or referrals), Claude summarizes each from public information: size, style,
  whether they show projects online. It then suggests why Unio would help
  *them*.
- **Personalized first messages** for Fabio to edit and send himself (never
  sent automatically: it's personal outreach in a small market).
- **Call preparation and notes.** Before a demo, a one-page brief; after it, a
  summary, the objections heard and the next step, filed in a simple CRM (even
  a spreadsheet at first).
- **Proposals:** a short PDF per office with the plan, price and onboarding
  steps, from a template.

**Cost.** Research with web search is roughly **US$0.05–0.20 per office**
researched on Sonnet or Opus. Even 200 offices a month is **US$10–40**.

**Care:**
- **LGPD:** research only public business information.
- Keep an opt-out on any email sequence.
- Never put personal data into URLs or shared documents.

## 5. Operations and finance

- **Billing while manual** (pricing-and-trials.md: Pix invoices first):
  - a monthly list of who to charge, and how much;
  - matching payments received against offices;
  - drafting the reminder for late ones.

  A person sends and confirms.
- **Onboarding:**
  - a checklist per new office, from what the operator dashboard shows (Drive
    connected? first project? client emails added?);
  - a nudge drafted when an office stalls.
- **Contracts and policies:** first drafts of terms and privacy changes.
  **Always reviewed by a lawyer**; the legal pages are currently drafts.

## What to build first

| Order | What | Effort | Monthly cost |
| --- | --- | --- | --- |
| 1 | Help center articles from the repo, kept in sync in PRs | 1–2 days, then a little per PR | ~0 |
| 2 | Weekly feedback digest and nightly error summary | 2–3 days (scheduled job + prompt) | US$5–15 |
| 3 | Drafted support replies with a person sending | 2–4 days, once there's an inbox with volume | US$5–20 |
| 4 | Sales research and outreach drafts | 1 day of prompts and templates | US$10–40 |
| 5 | In-panel assistant | 1–2 weeks (UI, guardrails, evaluation) | US$10–50 |

Total for all of it at pilot scale: **well under US$100/month in API costs**.
The constraint is review time, not money.

## Rules for all of it

- **Office and client data stays protected.** Don't send an office's files or
  clients' personal data to any AI service unless the office has agreed in its
  terms. Anthropic's commercial API terms say customer data isn't used for
  training by default; confirm the current terms, and mention the provider in
  the privacy policy (section 21) before any feature does this.
- **A person sends** anything external: emails, posts, replies, proposals.
- **No upstream detail in what customers see** (AGENTS.md "User-facing errors").
  This applies to AI-drafted replies too.
- **Measure before scaling:** keep the drafts, and how many were sent
  unchanged, edited or discarded. If most are rewritten, the prompt or the
  sources need work, not more automation.

## Sources

- Claude prices: Anthropic API pricing (models and batch/caching discounts), October 2026
- Intercom Fin: [Gleap, 2026](https://www.gleap.io/blog/intercom-fin-ai-pricing-2026), [Voiceflow](https://www.voiceflow.com/articles/intercom-pricing) (confirm on intercom.com)
