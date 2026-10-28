# Project Instructions

## Git workflow

Before starting any new task:

1. Check the current Git status and branch.
2. Fetch the latest changes from origin.
3. If on main with a clean working tree, pull the latest
   main using fast-forward only.
4. If there are uncommitted changes, conflicts, or a
   different working branch, explain the situation
   instead of overwriting anything.
5. Never discard local changes without permission.

Before finishing:

- Check whether main has changed since work began.
- Warn about any conflicts or outdated code.
- Never push, merge, or deploy without explicit approval.

## Making changes

- Prefer small, focused changes.
- Follow existing code conventions.
- Avoid unnecessary refactoring.
- Explain significant architectural changes before making them.
- Keep safeguards proportional to the real risk in our setup (Cloud Run,
  Cloud SQL, a handful of offices, a small team). Prefer one simple check that
  covers the real failure over many checks for unusual configurations.

### Naming: tenant

An office using the product is a **tenant**. Code says "tenant" everywhere:
classes, functions, variables, database objects, settings, tests and code
comments (e.g. `Tenant`, `CurrentTenant`, `current_tenant`, `TenantOwned`,
`tenant_isolation`). Text users see says "escritório". Plans and docs for people
may say "office", meaning a tenant.

### Searching code

When Jev is available (the `jev` command, for example in Claude Code or the
Codex CLI):

- **First step of a task whose files you don't already know:** run
  `jev find "<the task in plain words>" backend frontend/src` before searching or
  opening files, then read the files and lines it returns. A fresh session knows
  no files, so this is most tasks. One search takes about 15 seconds and costs
  under a cent.
- **Checking a property across many files** ("does every route check the
  tenant?"): `jev ask "<yes/no question>" <files or directory>`.
- Use ordinary text search for exact names you already know, and for the docs:
  Jev reads code by its declarations, so it does not find things in prose.
- In Claude Code, open files with the Read tool, not `cat` or `sed`: Jev's hook
  narrows a large file to the part that answers the request only on a Read.

Read enough surrounding code to make edits safely. If Jev fails, report it.

### Runtime code vs one-off code (`backend/`)

Code the running app executes lives apart from code that runs once or only by
hand, so a reader of the app's code sees only what actually runs:

- **Runtime** (loaded by the app): `backend/app.py`, `settings.py`, `db/`,
  `tenancy/`, `web/`, and later feature packages.
- **Migrations** (`backend/migrations/`): Alembic versions, plus
  `snippets.py` (SQL to paste into new migrations) and `registry.py`.
  A migration writes its SQL out in full and never imports helpers from app
  code, so it replays exactly as it first ran.
- **Commands** (`backend/commands/`): run by a developer or a release step,
  e.g. local database setup, seeding, provisioning.

One-off code may import runtime code, never the reverse. A test fails if the app
loads anything from `backend/migrations/` or `backend/commands/`.

## Testing

- Add or update automated tests for changed functionality. Be thorough about
  behaviour: what the code does, its edge cases and failure paths, and the rules
  that later changes could break (for example "every office table is isolated").
- Do not test fixed values for their own sake: constants, default literals,
  exact copies of SQL or strings that merely restate the implementation. Such
  tests break on harmless edits and catch nothing. Test the behaviour that
  depends on them instead.
- A regression test for a bug should fail on the code before the fix; check it.
  A test of a safety rule should include a self-test showing it catches a
  violation, so it cannot silently stop working.
- Locally, run only the tests the change affects, plus `make lint`: for
  example `uv run pytest backend/tests/test_x.py`, `npm test -- <file>`, or one
  browser test with `npx playwright test -g "<name>"` (after `make build`).
  CI runs the full suite (backend, staff app, browser tests, image) on every
  pull request into `staging`; it takes minutes, the full local run much longer.
- Push to the pull request and ask Codex for its review right away, while CI
  runs (Fabio, 23 Oct 2026: waiting doubled each round); fix what either finds.
  Hand the pull request to Fabio only once CI has passed: never a red one.
- Run the full suite locally (`make test`, `make e2e`) only when there is no
  pull request to run CI on, or when asked.
- Fix any test failures introduced by the changes.
- If tests cannot run, explain why.
- After an API change, run `make api-types` and commit the regenerated files.
- The old app (outside `backend/` and `frontend/`) is no longer in use and CI
  does not test it. Before changing it, read `docs/old-app.md` (its tests, local
  data modes and test data workflow).

## Local development

- Use the project's documented development commands (`make help`, README.md).
- Start the application locally when testing UI changes.
- Verify that the local server starts successfully.
- Provide the localhost URL to the user.
- If browser testing is available, verify the changed UI.
- Never claim that something was tested if it wasn't.
- Demo and manual test data is fictional and in Brazilian Portuguese. Never copy
  real client documents, credentials or private information into fixtures.

## Decisions and shared context

Several people and agents work on this repository: Claude Code, Cowork, Codex,
and chat sessions with no repository attached. **The repository is the only thing
all of them can see.** A decision discussed in a chat is not recorded until it is
committed here.

- `docs/multi-tenant-implementation-plan.md` is the architecture and rollout
  plan, and **section 2 is the decision register** — the current position on
  every settled question, with IDs (A01, A02, …). Section 24 lists the decisions
  deliberately left open and who needs them. Before starting, read the register
  entries for the area you change (search it for the feature's terms), and
  section 24 when the task may touch an open question.
- **A change to a register entry must update the register and its affected tests
  before coding proceeds.** This is the plan's own rule; follow it.
- `docs/decision-changelog.md` records what each decision *was* and why it
  changed. The register cannot hold a rejected alternative, so without the
  changelog the same argument gets re-litigated. Before reopening a settled
  question, read its changelog entry; if there is none and you are changing a
  register row, add one. Newest at the top, never edit a past entry.
- `docs/infrastructure-cost-comparison.md` holds the hosting and provider cost
  analysis.
- `docs/pricing-and-trials.md`, `docs/storage-strategy.md`,
  `docs/ai-for-the-business.md` and `docs/whatsapp-updates.md` are analyses for
  discussion (pricing and trials, own storage versus more providers, AI across
  the business, WhatsApp updates), not decisions.
- `docs/future-ideas.md` is the user-requested collection of uncommitted product
  ideas. Add possibilities there; promote agreed scope into the existing plan
  and record changed decisions in the changelog before implementing them.
- Don't start a parallel planning or decision document. If something doesn't fit
  the plan's structure, say so rather than creating a second source of truth.
- Any copy of these documents outside the repository — for example in a claude.ai
  project — is a stale mirror. Read the repo.

## Pull requests

Before opening, updating or handing over a pull request, read
`docs/pull-requests.md`: Codex review rounds and which findings to fix, the
description's **Context** section, and screenshots for UI changes. Pull requests
for the rewrite go into `staging`; Fabio reviews and merges.

### Review guidelines

Whoever reviews (Codex, Claude or a person) reads the linked sections first and
checks the change against them, in addition to looking for bugs:

- It does what the linked documentation calls for, and does not take on work it
  assigns elsewhere or later.
- It does not contradict a recorded decision. A change of decision updates the
  decision's record, its changelog entry and its tests in the same pull request.
- Anything the documentation requires for this area is present, unless the
  description or the documentation records it as deferred.
- Documentation that describes the changed behaviour still matches the code.

Report a mismatch with the documentation as a finding like any other, citing
the section.

## User-facing errors

Never surface backend or upstream error detail in the UI. No HTTP status codes,
no API response bodies, no exception text, no stack traces, no provider names —
not in a flash message, not on an error page, not in form validation. This
applies to the staff panel exactly as much as to client-facing pages.

Two reasons, and both matter: upstream bodies leak implementation detail, and
sometimes identifiers or fragments of credentials, to whoever is looking at the
screen; and they are meaningless to the reader (see Communication below — the
user may not be a software engineer).

Instead: a short message in the user's language saying what failed and what to do
next; where the user can fix it, say what to fix in their terms, not the API's;
log the full detail server-side at ERROR with route, operation and tenant; show a
short support/request ID that the log line also carries. Keep the detail on the
exception for logging and translate at the boundary where it becomes
user-visible.

Section 17 of the implementation plan holds the error-code and support-ID
conventions this belongs to.

## Safety

- Never deploy directly to Google Cloud.
- Never modify production data during testing.
- Never expose or commit credentials or secrets.
- Do not modify infrastructure or database schemas
  without explicit approval.

## Communication

The user may not be a software engineer.

- Explain problems in simple language.
- Handle technical steps yourself whenever possible.
- Give clear instructions for manual steps.
- After each task, summarize what changed, what was
  tested, and how to view the result locally.
