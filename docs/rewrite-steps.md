# Multi-tenant rewrite: step-by-step plan

**Draft for review · 14 October 2026**

This is the execution breakdown of section 23 ("Implementation slices") of
[`multi-tenant-implementation-plan.md`](multi-tenant-implementation-plan.md).
It does not make product decisions: those stay in the plan's decision register
(section 2). It does make **engineering** decisions (layout, libraries, how
isolation is enforced). Each is marked **Proposed** until you approve it. Once
approved, the ones that matter long-term go into the register too.

## How we work

1. **One step = one pull request into `staging`.** `main` stays the current
   site and keeps deploying production; nothing here touches it.
2. **Decisions before code.** At the start of each step I post that step's
   decisions with the alternatives I rejected. You approve or change them, and
   only then do I write code.
3. **Small and reviewable.** A step aims at a few hundred lines of real code
   plus tests. If one grows bigger, I split it.
4. **Every PR includes:** tests for the change, the full test run, a short
   "what to look at" list for your review, and how to try it locally. A step
   that adds tables also includes a diagram of them (rendered on GitHub) and the
   migration file, so the exact schema is reviewed in that step.
5. **After merge,** `staging` deploys `portal-staging`, and I check it there.
   Production only changes at cutover (step 7), with your explicit approval.

## Decisions needed before step 1.1

These shape every later step, so they are worth settling first.

| # | Question | Proposed | Alternatives and why not |
| --- | --- | --- | --- |
| D1 | Python version | **Agreed: 3.13**, matching production. This Mac has it (`/opt/homebrew/bin/python3.13`); the current app's venv is 3.11 | 3.14 is newer, but Cloud Run's builders and some libraries lag |
| D2 | Dependency management | **Agreed:** **`uv`** with `pyproject.toml` and a committed lockfile (`uv.lock`). One fast tool for the virtual environment, installs and exact versions | `pip-tools` works but is slower and has more moving parts. Plain `requirements.txt` without a lock is not reproducible (the plan already flags this) |
| D3 | Where new code lives | **Agreed:** **`backend/`** is the whole Python app for both audiences: client project pages (their Jinja templates live inside it), the JSON API, login, database, Drive and background work. It is the only thing that runs on Cloud Run. **`frontend/`** is only the React source for the staff screens; it is built into static files that `backend/` serves at `/painel`, and it talks to `backend/`'s API. Both at the repo root, next to the current app, which stays as it is until cutover | A separate repository: harder to share fixtures, the fake Drive and history. Rewriting in place: the current site would break during the rewrite |
| D4 | Test framework for new code | **Agreed:** **pytest**, for fixtures (database per test, fake Google) and readable assertions. The current app's `unittest` tests keep running unchanged | `unittest` everywhere: consistent, but fixtures for the database and fakes get verbose |
| D5 | Sync or async database access | **Async** (SQLAlchemy 2 async with psycopg 3), as the plan's section 3 already says, so file streaming and Drive calls don't block other requests | Sync is simpler to write, but slow Drive calls would hold a worker while waiting |
| D6 | How offices are kept apart in the database | **Both layers:** every query goes through repository functions that require the office (tenant), **and** PostgreSQL row-level security (RLS) refuses rows of another office even if code forgets. The app connects as a restricted role that cannot bypass RLS | Code-only scoping: one missed filter leaks another office's data. RLS-only: harder to read and test, and errors surface late |
| D7 | Database for staging and production | **Agreed: Cloud SQL for PostgreSQL** (plan A16), one small instance in us-east1 with separate staging and production databases and users | Neon: free, but in another cloud (slower queries) with short backups on the free tier. A database inside the container: lost on every restart |
| D8 | Staff login until real Google login (step 6) | **Per-office password login backed by the new users/sessions tables** in staging, the same shape as the final login, so step 6 only adds Google as a way in | A shared staging password: throwaway work. Google login now: needs the OAuth consent setup first, which slows step 1 |
| D9 | Automated checks on GitHub | **GitHub Actions** running the tests on every PR into `staging` (the repo has no CI today) | Local-only testing: depends on someone remembering, and doesn't protect `staging` |

## Slice 1: foundation

Goal: a new app that runs locally and on `portal-staging`, knows which office a
request belongs to, can't leak data between two offices, and serves an empty
React painel. No client-visible features yet.

### Step 1.1: Python skeleton

- **What:** `backend/` package with an app factory (`create_app()`), typed
  settings read from the environment (`pydantic-settings`), and a `/health`
  check (not `/healthz`: Cloud Run intercepts paths ending in "z"). Plus
  `pyproject.toml`, `uv.lock`, linting with `ruff`, and pytest set up.
- **Decisions:** D1, D2, D3, D4. Settings in this step: `ENVIRONMENT`
  (local/test/staging/production, required on Cloud Run) and `LOG_LEVEL`. JSON
  log lines when deployed, plain text locally. API docs at `/api/docs` except in
  production. Test client: `httpx2` (Starlette's preferred client).
- **Environment (agreed):** one shared `.venv` on Python 3.13 managed by `uv`
  for both apps. The current app's libraries are the `legacy` dependency group,
  mirroring `requirements.txt`; its full suite passed on 3.13 before this step.
- **Tests:** the app starts; settings refuse to start in production mode with
  missing required values; the health check answers.
- **Review:** folder layout, settings (what's configurable and what isn't),
  dependency list and versions.
- **Try it:** `uv run uvicorn backend.app:create_app --factory --reload`

### Step 1.2: Database and first migration

- **What:** async SQLAlchemy setup, Alembic migrations, and the first tables:
  `tenants` and `tenant_domains`. A local command creates a separate dev and test
  database on your PostgreSQL. Tests run each test inside a transaction that is
  rolled back, so tests never see each other's data.
- **Decisions:** D5. Plus: IDs are UUIDs, not counters, so they can't be guessed
  and merge safely; every table has `created_at` and `updated_at`; every
  office-owned table has a `tenant_id`.
- **Safety:** the test setup refuses to run against any database that isn't
  local, so it can never touch staging or production.
- **As built:** migrations live in `backend/migrations/` (not the repo root) so
  the whole backend is one folder for the image. `updated_at` is set by a
  database trigger using `clock_timestamp()`, so it also covers changes made
  outside the ORM. A test fails if models and migrations ever disagree.
- **Tests:** migrations apply from empty and roll back; the constraints hold
  (for example, a hostname belongs to one office only).
- **Review:** the schema, naming conventions, migration style.

### Step 1.3: Office from the address

- **What:** every request's hostname is normalised (case, port, trailing dot)
  and looked up in `tenant_domains`. Unknown hostnames get a plain 404, never a
  default office. `www.` redirects to the main hostname. The office is then
  available to every route as an explicit dependency, never a global.
- **Data:** a local seed command creates two fictional offices with their
  hostnames, plus `alineaarquitetos.com` and the staging hostname mapped to the
  first office.
- **Tests:** right host, wrong host, `www`, uppercase, port, an unknown host,
  and spoofed `X-Forwarded-Host` headers being ignored.
- **Review:** how the office is resolved and passed around (this pattern is
  used by every later step).
- **As built:** the whole hostname is matched exactly, never parsed for a slug.
  Aliases and `www.` get a permanent redirect (301, or 308 for non-GET so a POST
  stays a POST) cached for one day. Suspended offices get the same 404 as unknown
  hosts. Plain ASGI middleware (never buffers streamed downloads). Request IDs
  reuse Cloud Run's trace ID; with `GOOGLE_CLOUD_PROJECT` set, log lines link to
  the trace. Real hostnames are added to staging/production data in step 1.7.

### Step 1.4: Isolation enforced by the database

- **What:** row-level security on every office-owned table. Each request sets
  the current office on its database connection; a restricted database role is
  used by the app, and a separate owner role only by migrations. Repository
  functions require the office as an argument.
- **Decisions:** D6.
- **Tests (the important ones):** with two offices holding projects of the same
  name, every repository function, and a raw query that "forgets" the filter,
  only ever returns the current office's rows. A connection reused from the pool
  never keeps the previous request's office.
- **Review:** the RLS policies and the test cases. This is the step most worth
  reading closely.

### Step 1.5: Staff accounts and sessions

- **What:** `users`, `memberships` (which office a user belongs to, owner or
  member), and `sessions` tables; login and logout; a session is bound to one
  office and refused on another office's address; CSRF tokens for every change.
  Passwords hashed with Argon2.
- **Decisions:** D8.
- **Tests:** login on the right office; the same session refused on the other
  office; expired and revoked sessions; CSRF required on changes; slow-down
  after repeated wrong passwords.
- **Review:** cookie settings, session lifetime, what's stored (only a hash of
  the session token).

### Step 1.6: React staff app skeleton

- **What:** `frontend/` (Vite, React, TypeScript) served by FastAPI at
  `/painel`, with a login screen and an empty project list calling `/api/me`.
  API types are generated from FastAPI's OpenAPI schema. Locally, Vite's dev
  server forwards `/api` to the Python app.
- **Decisions:** component approach (proposed: plain React with CSS modules and
  the design prototype's tokens, no UI library yet; revisit if we adopt one for
  the file browser), routing (React Router), data fetching (TanStack Query).
- **Tests:** a component test (Vitest) and one Playwright test against the
  **built** app served by FastAPI: log in, see "Projetos", reload a deep link.
- **Review:** project structure, the generated API client, how the shell is
  served and cached.

### Step 1.7: Container, CI and staging deploy

- **What:** the two-stage `Dockerfile` from plan section 4. The staging trigger
  switches from buildpacks to building this Dockerfile. Migrations run as a
  separate release step before the new revision takes traffic. GitHub Actions
  runs all tests on PRs into `staging`.
- **Decisions:** D7, D9.
- **Needs from you:** approval to create the Cloud SQL instance (a paid change,
  about $9–10/month), and the deploy permission for `portal-staging`.
- **Tests:** the image builds and starts locally; on staging, the staging
  hostname resolves to the first office, an unknown host gets 404, and login works.
- **Review:** the Dockerfile, the build steps, where secrets come from.

**Slice 1 is done when:** both offices are isolated under the restricted role,
staging runs the new app, and you can log in to an empty painel there.

## Later slices (expanded into steps when we reach them)

### Slice 2: the client project page

2.1 Project tables (projects, stages, details, meeting, slug aliases).
2.2 Storage adapter contract plus the fake Drive (reusing `tools/fake_drive.py`).
2.3 Project page at `/{slug}` rendered with the current Jinja templates, data
from the database. 2.4 Optional password on every content route. 2.5 File
streaming and previews through the reader identity. 2.6 Staff bar on the page.
2.7 Read-only import of the current `_project` / `_stage` files (dry run first).

### Slice 3: creating and editing projects

3.1 Office presets (detail fields, stage templates) seeded from the first office.
3.2 Project creation (name, client, template) with durable Drive provisioning
and the share-while-empty rule. 3.3 Painel project list with covers and the
generated fallback. 3.4 Edit mode on the project page: description, details,
meeting. 3.5 Stages: add, rename, reorder, remove, advance, complete. 3.6 Office
settings and Drive connection in the painel.

### Slice 3b: uploads and versions

3b.1 Resumable upload into a stage. 3b.2 Same-name prompt and "Enviar nova
versão" (`vN`, originals never renamed). 3b.3 Covers stored as `_capa` in Drive.
3b.4 "Ocultar do cliente".

### Slice 4: keeping up with Drive

Incremental sync of changes made directly in Drive, version grouping of `vN`
names, repair scans, previews.

### Slice 5: notifications

Email on stage advance and new files, with the 45-minute quiet window (A12),
recipients and unsubscribe.

### Slice 6: real Google login and live checks

Google sign-in for staff; the live read/write capability matrix against real
Drive accounts.

### Slice 7: moving the first office over

Import, comparison against the current site, and switching `alineaarquitetos.com`
to the new app: only with your explicit approval, and with the current site kept
ready to switch back.

## What I need from you to start

1. Approve or change decisions D1–D9 (or tell me which to discuss).
2. For step 1.1 specifically: D1–D4.
3. Run the staging script when you have a moment, since step 1.7 builds on it
   (it isn't needed for steps 1.1–1.6).
