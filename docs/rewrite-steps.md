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
| D3 | Where new code lives | **Agreed:** **`backend/`** is the whole Python app for both audiences: client project pages (it serves their shell and preview tags), the JSON API, login, database, Drive and background work. It is the only thing that runs on Cloud Run. **`frontend/`** is the React source of the staff screens and the client page (A20, revised 16 Oct 2026); it is built into static files that `backend/` serves (`/painel` and `/{slug}`), and it talks to `backend/`'s API. Both at the repo root, next to the current app, which stays as it is until cutover | A separate repository: harder to share fixtures, the fake Drive and history. Rewriting in place: the current site would break during the rewrite |
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
- **As built:** settings `DATABASE_URL` (the app's login), `MIGRATION_DATABASE_URL`
  (the owner) and `DATABASE_RUNTIME_ROLE`. Policy `tenant_isolation` compares
  `tenant_id` with `current_tenant_id()`, which reads a per-transaction setting
  (NULL when unset, so no rows). RLS is FORCEd. Sessions opened with
  `get_tenant_session` set the tenant at the start of every transaction.
  `tenants`/`tenant_domains` are the routing registry: protected by grants
  (read-only for the app), not by the policy, because they are read before an
  office is known. No office-data table exists yet: projects (step 2.1) is the
  first; tests use a stand-in table set up the same way, and a schema test
  makes every future `tenant_id` table enable isolation. After Codex review:
  privileges go to a per-database group role (`<database>_app`), not a login;
  `backend.commands.provision` (release step after migrations) makes the configured
  login its only member, so rotating the login needs no migration. Migrations
  inline their SQL instead of importing app helpers; a schema test compares
  `current_tenant_id()` between the migrated database and the code's definition.

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
- **As built:** each person belongs to exactly one office, so there is no
  `memberships` table: `users` carries `tenant_id` and `role` (owner/member),
  unique per (office, email); the same email in two offices is two separate
  accounts. `users` and `sessions` are tenant-isolated like any office data
  (the app may only read users and manage sessions). Sessions are database rows:
  the cookie `portal_session` (HttpOnly, SameSite=Lax, Secure when deployed,
  host-only) holds a random token, the table stores only its SHA-256 hash; 30 days
  since last use, `last_seen_at` updated at most hourly; sign-out revokes the row.
  API: `POST /api/session` (sign in), `DELETE /api/session` (sign out),
  `GET /api/me`; dependencies `current_staff` and `require_csrf` (token per
  session, sent back in `X-CSRF-Token`). A wrong email and a wrong password get
  the same answer after the same work (a dummy hash) plus a fixed 1-second delay,
  and at most 4 password checks run at once per instance (each takes 64 MiB).
  The cookie is re-sent with the session's current expiry on each signed-in
  request. Errors return only a code (`{"error": "invalid_credentials"}`,
  listed in `ErrorCode`); the screens translate it. Values from a fixed set are
  Python `StrEnum`s (`Role`, `TenantStatus`, `Locale`, `ErrorCode`), stored as text
  with a CHECK constraint (`backend/db/types.py`) because PostgreSQL enum types
  are hard to change; the API schema lists them, so the screens' generated types
  do too. `/api/me` includes the office's language. Passwords: at least 8
  characters. **Still open:** limits on attempts per account and per source
  (plan section 5), deliberately deferred; needed before offices other than the
  first can sign in. Accounts are created with
  `backend.commands.staff add`, without a password: people choose their own
  through a one-time link (`password_links`, kind `invite` for 7 days or `reset`
  for 1 day; `reset-link` makes one). Only a hash of the link's token is stored,
  the token travels in the URL fragment, a new link cancels older ones, and
  choosing a password ends the account's other sessions. API: `POST
  /api/password-link` (whose link is this), `POST /api/password` (choose, then
  signed in). The app may change only `users.password_hash` and
  `password_links.used_at`. Account rules live in `backend.identity.accounts`
  and `links`, for the painel and a sign-up page to reuse.

### Step 1.6: React staff app skeleton

- **What:** `frontend/` (Vite, React, TypeScript) served by FastAPI at
  `/painel`, with a login screen, the "choose your password" screen for invite
  and reset links (step 1.5b) and an empty project list calling `/api/me`.
  API types are generated from FastAPI's OpenAPI schema. Locally, Vite's dev
  server forwards `/api` to the Python app. Every visible text goes through the
  translation catalogs from the start (plan A26; Portuguese written first), error
  codes included. Deploy compatibility (plan A30): fingerprinted assets, the app
  shell never cached, a build ID on API responses and a reload prompt that keeps
  unsaved edits.
- **Decisions:** component approach (proposed: plain React with CSS modules and
  the design prototype's tokens, no UI library yet; revisit if we adopt one for
  the file browser), routing (React Router), data fetching (TanStack Query),
  and how editing components are shared with the client page (plan section 24:
  proposed, build once in React and load them onto the client page for staff).
- **Tests:** a component test (Vitest) and one Playwright test against the
  **built** app served by FastAPI: log in, see "Projetos", reload a deep link.
- **Review:** project structure, the generated API client, how the shell is
  served and cached.
- **As built:** Vite 8, React 19, TypeScript 5.9 (strict; 7 is out but the type
  generator needs 5's compiler API), React Router 8, TanStack Query 5,
  openapi-fetch with types from `openapi-typescript`, i18next reading
  `backend/i18n/*.json`, React Aria Components for accessible base pieces in
  `frontend/src/ui/`, CSS modules with the prototype's tokens, Hanken Grotesk
  self-hosted. Screens: sign-in (`/painel/entrar`), choose password
  (`/painel/definir-senha#token=…`, token removed from the address bar), Projetos
  (empty), not found; sign-out; light/dark per device. Served by
  `backend/web/painel.py`: shell never cached, `assets/` cached a year, a missing
  asset is a 404 (not the shell). `X-Build-Id` on every response; a different
  release build or a failed file load shows a reload prompt. `GET /api/tenant`
  gives the office's name and language before sign-in. A `Makefile` wraps setup,
  dev, test, e2e and API-type generation. Tests: Vitest + Testing Library for the
  screens (fake API), pytest for serving, translations (every language has every
  text; every error code, role and language is translated) and API-description
  freshness, Playwright against the built app served by Python on a fresh database
  (`backend.commands.e2e`). Editing components shared with the client page: the
  `ui/` folder is ready; the second bundle comes with project editing.

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
- **As built:** `deploy/Dockerfile` (two stages; kept out of the repo root so
  the current site's buildpacks build on `main` is unaffected). Merging into
  `staging` runs `deploy/staging/cloudbuild.yaml` as `portal-staging-deploy@`:
  build, push, migrate and provision through the Cloud SQL Auth Proxy, then
  `gcloud run services replace deploy/staging/service.yaml`. Cloud SQL
  `arqproj-db` (PostgreSQL 17, `db-f1-micro`, backups 7 days, deletion
  protection) with IAM database logins: no database passwords anywhere. The app
  reaches the database through a proxy sidecar. No deploy scripts: admin
  commands (`make tenant|staff|reset-link ENV=staging`) go through the proxy as
  the deploy identity. GitHub Actions (`.github/workflows/ci.yml`): backend
  tests and lint on PostgreSQL 17, frontend checks, Playwright, image build.
  Everything created is recorded in `docs/infrastructure.md`.

**Slice 1 is done when:** both offices are isolated under the restricted role,
staging runs the new app, and you can log in to an empty painel there.

## Later slices (expanded into steps when we reach them)

### Order changed (15 Oct 2026): painel before the client page

Agreed with Fabio: the painel's design is settled (UI reference: the prototype
in [arqprojprototypes](https://github.com/fabiogelbcke/arqprojprototypes)) while
the client page's is still changing, and there is no rush to move the first
office. So the painel comes next, then the client page once its design settles:

1. **P1 Drive connection** (moved first, 15 Oct 2026: creation needs Drive,
   so it is built once with folders) and the painel's **first steps** checklist.
   **As built:** Configurações → Google Drive (owners connect and disconnect;
   members see), `drive.file` sign-in through **one shared return address**
   that forwards to the office that started (signed `state`, a one-time nonce
   cookie, only to addresses registered to that office); the "Portal Clientes"
   folder is shared with the reader **before** anything else, and trashed if
   sharing fails; reconnecting keeps the folder; the refresh token is stored
   encrypted with a key derived from `APP_SECRET` (Cloud KMS can replace it).
   `storage_connections` gains account, encrypted token, writer and reader
   health (migration 0009; the app may now change its own office's row).
   `/api/onboarding` and the "Primeiros passos" list; the painel notice when
   Drive is missing or expired.
   **P1b Office details** (as built): Configurações → Escritório (name, contact
   email, logo; owners edit, members see), in a new isolated `office_profiles`
   table (migration 0010) rather than the shared `tenants` registry. The logo
   (PNG, JPG, WebP or SVG up to 5 MB, type read from the bytes) goes to a
   `_marca` folder in the office's Drive (or the local folder in development),
   replacing the previous one, and is served with a policy that lets nothing in
   it run. The checklist item ticks once the email and logo are set.
2. **P2 Creating a project and the project list** (as built, combined with the
   list): "Novo projeto" asks for the name, client (up to 48 characters), stage
   template (Padrão, Interiores, Sem etapas; replaced by the project type and
   its ticked stages in P3b) and the page address, suggested from the name and
   editable; an address in use names the project that has it. The project
   starts as a draft with the template's stages and default type. Its folder goes into the office's folder, with one
   "01 - <stage>" folder per stage in the office's language (a local folder in
   development); all or nothing within the request (A07), with a one-time
   creation key. Needs the office's Drive connected; members can create too.
   Migration 0011 gives the app INSERT on projects, project_slugs and
   project_stages. The list (read-only): groups in progress (x/y), drafts
   (tagged) and completed (folded), accent-insensitive search on name and
   client, sorting by last update, creation date, name, client or type in
   either direction (remembered on the device), cards with a placeholder photo
   (10 CC0 photos, `frontend/src/projects/covers/LICENSES.json`), the current
   stage "N / total", the next meeting and the last update in the office's time
   zone. Copying the client link waits for the client page (slice 2).
3. **P3 Project settings in the painel** (A24, narrowed 16 Oct 2026): the
   prototype's "Projeto" dialog with name, client and cover, and "Arquivar"
   (undo from the toast); the card's photo button ("Trocar foto"); covers stored
   in a `_capa` folder in the project's folder; simultaneous edits detected by
   row version; the toast component. Client link and access join the dialog in
   slice 2. Until the project page exists, a card's title opens the dialog.
   Slice 2 must leave `_capa` out of the client's file list, and serve the cover
   to clients (staff only for now).
   **P3b Project types and their stages** (A27 revised 16 Oct 2026): "Novo
   projeto" asks for the type; the 12 built-in stages from Alinea's partners are
   listed in one order, the type's usual ones ticked, any ticked or unticked.
   Descriptions per type, a general one otherwise. Migration 0013 replaces the
   old stages and the templates and deletes the projects made with them (tests).
4. **P4 Folders for older projects**: moved into the import of existing
   projects (slice 2).
5. Then **slice 2** below (client page, password, downloads, import), whose edit
   mode reuses the painel's editing pieces (plan section 24), then slices 3b–7.

Steps 2.1, 2.2 and 2.2b (tables, storage, reference tables) are done and stay
the base for both.

### Slice 2: the client project page

2.1 Project tables (projects, stages, details, meeting, slug aliases).
**As built:** `backend/projects/` with `projects`, `project_slugs` (every slug a
project has had, one current, one namespace per office), `project_stages`
(built-in key or office-written title and explanations), `project_details`
(built-in key, value stored by type), `meetings` (a list; next by date). Enums
for status (`draft`/`active`/`completed`/`archived`), access mode, project type,
stage template (removed in P3b), built-in stage and detail key, all translated in
`backend/i18n`. Migration 0006 isolates every table and grants the app read
access only. The local seed adds fictional Portuguese projects covering the edge
cases (draft without stages, completed with a password, changed address,
office-written stage, past and upcoming meetings).
2.2 Storage adapter contract plus the fake Drive (reusing `tools/fake_drive.py`).
**As built:** `backend/storage/`: a read-only `Storage` interface (list a
folder, get an item, download, thumbnail; failures as `StorageProblem`, never the
provider's text) with three stores: Google Drive (the server's own Google
identity, no key files; retries with growing waits on throttling and server
errors; ids checked before they reach Drive's search), a local folder (`make
dev`, the fictional dataset; refused when deployed) and in-memory (tests).
Instead of reusing the Flask fake Drive, tests imitate the Drive endpoints
in-process (`httpx2.MockTransport`). `storage_connections` (one per office,
isolated, read-only for the app) and a `folder_id` on projects and stages
(migration 0007); the seed links its projects to the dataset's folders. Names sort
ignoring case and accents. Until slice 4's sync, pages will list files live from
the store.
2.2b Built-in content as reference tables (A26 refined). **As built:**
migration 0008 creates `project_types`, `detail_types`, `stage_definitions`,
`stage_templates` and `stage_template_stages` with the built-in rows and their
texts in Portuguese and English (moved out of `backend/i18n`), replaces the
CHECKs on the columns that use them with foreign keys, and gives each detail row
its value type (composite foreign key, so its value column is checked by the
database). The enums stay as names for the built-in rows; `test_reference_content`
keeps them and the rows in step. Since P3b (migration 0013) the templates are
gone: `project_type_stages` lists each type's usual stages instead.
2.3 Read-only project page at `/{slug}`, after the fresh prototype (A20
revised: React, its own bundle; the server sends preview tags, "not found" for
drafts and unknown addresses, redirects from old addresses). **As built:**
`backend/web/pages.py` serves `/{slug}` (the shell from `frontend/client.html`
with title, description and cover preview tags, `noindex`; 404 for drafts,
deleted and unknown addresses alike; 301 from an old address) and the public
`/api/pages/{slug}` (only what the page shows: no ids or folders), its cover and
`meeting.ics`. A password-protected project shows only "Página protegida" until
2.4, and its name stays out of previews. `frontend/src/client/` is the page,
styled by the prototype's own stylesheet (`prototype.css`, replaced wholesale
when the design moves to Figma); Vite builds it as a second app. Stages show
the project type's description under "Sobre esta etapa"; files come in 2.5.
2.4 Optional
password on every content route; client link and access in the "Projeto"
dialog. **As built:** the "Projeto" dialog gains "Link do cliente" (a new or
earlier address; the old one keeps redirecting; another project's, current or
old, is refused with its name) and "Acesso" (public, or a password of 6+
characters; an empty field keeps the current one). A protected page asks for
the password; `POST /api/pages/{slug}/unlock` sets a signed cookie per project
for 90 days, tied to `access_version`; 5 wrong tries per device, then 15
minutes (`backend/web/attempts.py`). Protected pages' responses are private,
no-store. Migration 0014 grants the columns this changes. 2.5 Each stage's files, downloads and previews through the reader
identity. **As built:** each stage lists its folder live
(`backend/web/page_files.py`): the files directly in it, and each subfolder as a
titled group (one level; Fabio, 16 Oct 2026). Names starting with "_",
shortcuts and Google formats that can't be exported stay hidden; Docs/Sheets
come as PDF. A file is named by a signed key (project, `access_version`, item;
12 hours), never its Drive id, so a key opens only what that page listed and a
new password ends it. Images and PDFs open in the browser, everything else only
downloads; nothing runs on the office's address (`nosniff`, a sandbox except for
the PDF viewer). Drive's previews where it has them. A stage whose folder can't
be read says so, and the rest of the page stays. The database connection is
released before any file or cover streams. Deferred: byte ranges and
validators for downloads (plan section 15; resumable downloads and seeking in
large PDFs), with slice 4's sync. 2.6 Staff bar on the page ("Painel", "Editar"); a card's title opens
the page; "Copiar link". **As built (with "Publicar", ahead of 2.4 and 2.5):**
the whole painel card links to `/{slug}`; the office's signed-in staff see
their drafts and protected pages there, with the prototype's dock ("Painel",
status, "Copiar link", "Publicar" for a draft; `POST /api/projects/{id}/publish`);
clients still get "not found" for a draft. "Editar" comes with edit mode. Then
the page's edit mode. **Part 1 as built:** the staff bar's "Ver como cliente |
Editar" switch; in Editar, the prototype's inline editors for the description,
the details (built-in ones: add, change, remove; areas and dates typed), the
next meeting (set in the office's time zone, or removed) and each stage's note
("Recado para o cliente"). Every save carries the page's `row_version`
(`project_changed` if someone saved meanwhile). "Atualizado" moves for notes and
the meeting only. Migration 0015 grants these columns and tables. **Part 2 as
built:** in Editar, each stage has the prototype's controls (rename, move up or
down, remove with a confirmation that its folder stays), "Adicionar etapa" (a
built-in stage not yet in the project, or the office's own), and the progress
rail ("Avançar para NN …", "Voltar etapa", "Concluir projeto", "Reabrir").
Folders follow in Drive: renames and moves rename the "NN - title" folders,
adding creates one, removing renumbers the folders after it and leaves its own;
Drive goes first and, if it fails, the names it changed are put back (to their
real earlier names) and nothing is saved. A folder deleted by hand is skipped.
A built-in stage renamed becomes the office's own, keeping its description.
Progress moves "Atualizado". Migration 0016 grants these columns. ~~2.7 Import of the
current `_project` / `_stage` files~~: dropped 16 Oct 2026, Alinea has no real
projects yet.

### Slice 3: creating and editing projects

3.1 Office presets (detail fields; each type's default stages, "Etapas padrão")
seeded from the first office. 3.2 ~~Project creation~~: done in P2/P3b (type and
ticked stages; within the request, A07). 3.3 Painel project list with covers and the
generated fallback. 3.4 Edit mode on the project page: description, details,
meeting. 3.5 Stages: add, rename, reorder, remove, advance, complete. 3.6 Office
settings and Drive connection in the painel.

### Slice 3b: uploads and versions

3b.1 Resumable upload into a stage. 3b.2 Same-name prompt and "Enviar nova
versão" (`vN`, originals never renamed). 3b.3 Covers stored as `_capa` in Drive.
3b.4 "Ocultar do cliente". **3b.1 and 3b.4 as built (A31):** in Editar, each stage
has the prototype's drop area ("Solte arquivos aqui ou escolha no computador").
Any staff member uploads, at most 100 MB a file: the app opens a Google resumable
upload in the stage's folder and the browser sends the file straight there, with
a progress bar; local folders get the app's own stand-in, never when deployed. A
same-name file is kept beside the other. Each file's "⋯" menu has "Ocultar do
cliente", which renames it with a leading `_`; a file put straight into Drive
says to rename it there (the grant is `drive.file`). No migration: pages list
Drive live (A10).

### Slice 4: keeping up with Drive

Incremental sync of changes made directly in Drive, version grouping of `vN`
names, repair scans, previews.

### Slice 5: notifications

Email on new files, a stage advanced or the project completed, and a meeting
scheduled, changed or removed (not a stage's note), with the 45-minute quiet
window and 2-hour hold (A12), recipients in the Projeto dialog and unsubscribe
(A32).
**5.1 (#41), 5.2 (#42) and 5.3 as built:**
- **The maintenance pass** (`backend/notifications/scan.py`, run by hand with `backend.commands.maintenance`, by the scheduler from 5.4) handles each published project in one transaction under its lock: it records new files, gathers changes into the project's open batch, and sends the batch once due.
- **A batch that came due** is sent with what it had; changes made after it start the next batch. A project archived with an email waiting has it dropped.
- **Just before sending** (`backend/notifications/digest.py`), it checks again that:
  - the project is still published;
  - the files are still on the page and unchanged for a minute;
  - the addresses are still subscribed, and outside production belong to staff;
  - a stage advance or a completion still holds, not taken back since.
  Otherwise the batch is dropped, or waits if a file is still changing.
- **One email per address,** each with an idempotency key, recorded in `notification_deliveries`. A failure is retried on the next pass, up to 5 times.
- **The email** is HTML and text, in the office's language. It shows the office's logo. Email programs don't show SVG, so an SVG logo is also stored as a PNG the painel draws in the browser when it's uploaded (migration 0020). An older SVG logo gets its PNG the next time an owner opens the painel; until then, the email shows the office's name.
- **Unsubscribe** is a link that asks for confirmation (`/api/emails/unsubscribe/{token}`) plus the one-click headers of RFC 8058.
- **Sending:** through Resend (`RESEND_API_KEY`), or to `local-test-data/outbox/` without a key.
- **Sender:** each office's domain from `EMAIL_OFFICE_DOMAINS`, else `EMAIL_DOMAIN`, else Resend's test sender.

5.4: the `/internal/maintenance` endpoint and the Cloud Scheduler job.

### Slice 6: real Google login and live checks

Google sign-in for staff; the live read/write capability matrix against real
Drive accounts.

### Slice 7: moving the first office over

Switching `alineaarquitetos.com` (no projects to import: Alinea starts fresh)
to the new app: only with your explicit approval, and with the current site kept
ready to switch back.

## What I need from you to start

1. Approve or change decisions D1–D9 (or tell me which to discuss).
2. For step 1.1 specifically: D1–D4.
3. Run the staging script when you have a moment, since step 1.7 builds on it
   (it isn't needed for steps 1.1–1.6).
