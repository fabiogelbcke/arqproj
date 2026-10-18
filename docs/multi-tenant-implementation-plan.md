# Multi-tenant portal: architecture, implementation and rollout

**Decision draft · 13 October 2026**

Prepared against repository `main` at `8a21b5b`, the supplied
`multi-tenant-plan.md`, and Fabio's subsequent decisions. The newer decisions
below supersede conflicting parts of the attachment. This document proposes a
new backend; it does not apply migrations, create cloud resources, or authorize
deployment. It separates chosen product behavior, recommended implementation,
verified behavior, and work that still needs external verification.

Framework decision updated after discussion: the new backend will use FastAPI
and Pydantic, while retaining Python. Updated 14 October 2026 (A20), revised 16
October 2026: the client project page and the staff administration are both React
+ TypeScript, built by Vite and served by the same service on the same origin;
the server renders the client page's preview tags and its "not found" answers. Offices
are served at `{office}.myunio.app` behind a load balancer (A21, section 4). References to Flask/Gunicorn in the
current-state inventory and verification history describe the existing
application, not the target backend.

Companion: [infrastructure cost comparison and POC options](infrastructure-cost-comparison.md),
including free-tier assumptions and Cloud Scheduler versus local cron.

[Future ideas](future-ideas.md) collects possibilities outside committed scope,
including templates, finer-grained team permissions, project organization and
WhatsApp updates. This plan remains the source of implementation decisions.

## 1. Product agreement and scope

The product is an architecture office's client portal. Each office keeps its
working files in its own Google Drive. Its staff can continue using Drive, while
clients get a clearer, branded view of deliverables, versions, project progress,
and meetings. Staff also gain a website for creating projects and managing files.

Start with approximately five friendly offices, onboarded personally and probably
free. Aim to put a useful pilot in their hands in the next few weeks. After
feedback, expand to another 10–20 early offices, likely paid. Engineering time is
variable, including nights/weekends. AI assistance should shorten implementation;
release readiness is determined by evidence rather than an assumed coding speed.

Confirmed choices:

- Keep Python; use FastAPI and Pydantic for the new backend. The client project
  page and the staff administration are React apps on the same origin; the
  client page is its own small bundle, and its edit mode is the same page with
  controls switched on (A20).
- Build a clean multi-tenant backend instead of threading tenant parameters
  through the prototype's single-office backend.
- Office URLs: `{office-slug}.myunio.app`, behind a load balancer (A21, section
  4; chosen 17 Oct 2026 over one domain with office paths). Display-name changes
  do not silently change URLs. The product is Unio, on
  `myunio.app` (A33). The first office keeps its own domain, `alineaarquitetos.com`, as a
  custom domain of the same deployment (A23); `{office}.myunio.app` is for later offices.
- Project links are simple: `/{project-slug}` on the office's address, as today
  (A22). Optional per-project passwords cover projects that need privacy.
- Creating a project asks for its name, the client's name and its type, whose
  usual stages come ticked and can be changed (A27). Details, meeting, cover
  image and files are edited afterwards: content in a staff edit mode on the
  project page, settings in the painel (A24).
- Files are versioned as `v1, v2, v3`: "send new version" on a file, and an
  upload with an existing name offers to become its next version (A25).
- PostgreSQL owns project metadata. Drive owns file bytes and physical folders.
- Use office-user OAuth with `drive.file` for writes, and an explicitly shared
  service account for reads. Fabio has tested the essential split successfully.
- Automatically publish files placed in the designated client-deliverables
  folder. A separate manual approval step is not required for the pilot.
- Public project links are supported. Password protection is optional per project.
  Office administration always requires authentication and authorization.
- Start with email update digests, grouping nearby uploads; support other channels
  later through a small delivery interface.
- Start with constrained office branding, then expand templates/customization.
- Keep Drive ownership and familiar workflows as product advantages. Hosting the
  offices' originals ourselves is a possible future option, not pilot scope.
- Preserve the working office's existing site until migration is proven.

Personal Gmail/My Drive is the first account type to validate. Workspace My Drive
and Shared Drives remain intended supported configurations, but each needs a real
acceptance result before we advertise it. Unknown account types are an onboarding
question, not a reason to require offices to purchase Workspace.

## 2. Decision register

“Recommended” means a concrete default for implementation review, not something
already deployed. A change to a recommendation should update this register and
its affected tests before coding proceeds.

| ID | Decision | Status and reason |
| --- | --- | --- |
| A01 | New backend in the same repository, retaining Python and the client-page UI | Agreed direction; replace the Flask backend with FastAPI rather than preserve the prototype's architecture. Staff UI direction revised by A20 |
| A02 | Modular application, one database, shared web deployment | Recommended; independent web/worker processes can use the same code and image |
| A03 | PostgreSQL + SQLAlchemy 2 + Alembic + psycopg 3 | Recommended; relationships, transactions, migrations and local parity |
| A04 | OAuth writes + service-account reads | Product choice, core flow reported tested by Fabio; remaining capability matrix below. **Hard ordering constraint on provisioning** — see section 9 |
| A05 | Tenant and project checks on every resource path | Required even for public projects; public within one office does not mean cross-office access |
| A06 | Public or password-protected project access | Agreed; no mandatory client account for the pilot. Details agreed 16 Oct 2026 (Fabio): staff set the password in the "Projeto" dialog (at least 6 characters, no generator); the client types it once per device and stays unlocked for 90 days; five wrong tries from one device make it wait 15 minutes, with no email to the office; a new password or access mode ends every unlock. See section 6 |
| A07 | All-or-nothing project creation | Pilot (15 Oct 2026): within the request, folders first, then every row in one transaction; on any failure nothing is saved and the new project folder (with its stage folders) is trashed, best effort; a one-time creation key makes retries safe. The durable provisioning operation in section 10 replaces it when there is a worker. See section 10 |
| A08 | Stable document/revision records, not filename-only versioning | Recommended replacement for the prototype's grouping rules. Revised by A25: clear `vN` names still group automatically |
| A09 | Recoverable background work; deployment and dispatch technology open | Revised POC proposal: an authenticated maintenance endpoint in the web service, called every 10 minutes (15 Oct 2026, was hourly), with durable application state. Managed queue/separate worker deferred unless needed. See section 4. |
| A10 | The client page reads Drive live; the sync job only notices changes | Revised 16 Oct 2026 (Fabio): a project page lists its stage folders from Drive on each visit, so a file added in Drive shows at once (staff) or within two minutes (a public page's browser cache). The incremental, polled sync no longer feeds the display; it records what changed, for emails (A12), "Atualizado" and the updates feed (A28), and, once versions arrive, the document index (A25). Reconciliation stays the repair path; webhooks can wake it later without becoming a correctness dependency. For the pilot it finds new files by scanning each published project's stage folders every pass rather than reading Drive's changes feed (Fabio, 16 Oct 2026). See sections 8 and 13 |
| A11 | Streaming proxy for private Drive content; optional Drive links | Recommended; clients need not have Google accounts or Drive sharing permissions |
| A12 | Email first, trailing "settle" window: send once uploads stop | Revised 14 Oct 2026 from a fixed 60-minute window. 45-minute quiet period, 2-hour maximum hold from the first publication, configurable per office. Clarified 15 Oct 2026: a batch becomes *due* by these rules and is *sent* by the next maintenance run (every 10 minutes); the delay prevents an email about withdrawn files, it does not hide them. See section 14 and the [changelog](decision-changelog.md) |
| A13 | Protected main, staging and approved promotion of one build | Recommended; environments are separate without requiring permanent divergent code branches |
| A14 | Same PostgreSQL engine locally and in production | Recommended; SQLite cannot validate the intended constraints, queue locks or row policies |
| A15 | Cloud Run web with bounded maintenance execution | Proposed hosting continuation; POC can run maintenance in the same service. Actual infrastructure requires separate approval |
| A16 | Managed PostgreSQL: Cloud SQL for PostgreSQL, one small instance in us-east1 holding separate staging and production databases | Agreed 14 Oct 2026, replacing Neon as the candidate. Same region as Cloud Run, so about 1 ms per query instead of roughly 10–15 ms to another cloud; Cloud Run's built-in connector and IAM login instead of a stored database password; daily backups kept 7 days. About $9–10/month for the smallest shared-core instance (verify at creation). Split staging onto its own instance, or upgrade the machine, when load or the number of offices calls for it. See the [changelog](decision-changelog.md) |
| A17 | Resend behind an email adapter | Proposed first provider; choose a plan based on actual volumes and delivery limits |
| A18 | FastAPI + Pydantic + Uvicorn for the new web backend | Agreed framework switch; validated request/response contracts, dependency injection and native async support; Cloud Run remains compatible |
| A19 | Cloud Scheduler preferred within its free allowance; local cron retained as an alternative | User accepts managed scheduling when free. Both call the same protected maintenance endpoint; cadence and deployment shape remain separate decisions. See the [cost comparison](infrastructure-cost-comparison.md). |
| A20 | Client project page and staff administration both React + TypeScript, built by Vite, served by the same FastAPI service on the same origin | Agreed 14 Oct 2026 with client pages in Jinja; revised 16 Oct 2026 (Fabio): since the project page is also where staff edit content (A24), one React page serves viewing and editing instead of two copies of every section. The client page is a separate, small bundle (staff editing code loads only on "Editar"). The server still answers before any script runs: the preview tags (title, description, cover) that messaging apps read, "not found" for drafts and unknown addresses, redirects from old addresses, and the password check. One image, one Cloud Run service. See section 4 and the [changelog](decision-changelog.md) |
| A21 | Office address scheme: **office subdomains, `{office}.myunio.app`, behind a global load balancer** (option A) | Agreed 17 Oct 2026 (Fabio), choosing between the two options recorded 14 Oct. Each office is its own origin (cookies, storage and script bugs stay inside one office), addresses read as the office's own, and custom domains fit later. The load balancer (~$18.25/month plus processing; Fabio has credits for the first three months) is a global external Application Load Balancer with a serverless backend for the production service, certificates from Certificate Manager (DNS authorization at GoDaddy) covering `*.myunio.app`, `myunio.app` and each office's own domain (`alineaarquitetos.com`, `www.`) before its DNS moves, and Cloud Run ingress limited to it. It is built before the second office's first client link; `alineaarquitetos.com` and `myunio.app` move behind it then, leaving Cloud Run domain mappings (Preview, "not recommended for production"). Staging keeps its domain mapping (`staging.myunio.app`, one office), so it does not pay for a second balancer. See section 4 and the [changelog](decision-changelog.md) |
| A22 | Project links are `/{project-slug}` on the office's address; no random token | Agreed 14 Oct 2026, replacing `/p/{public_token}/{slug}`. Readable and shareable, and the first office's existing links keep working unchanged. Guessable by design; privacy comes from the optional password (A06). Slugs are unique per office and stable once shared. See section 6 and the [changelog](decision-changelog.md) |
| A23 | First office served on its own domain (`alineaarquitetos.com`) as a custom domain of the shared deployment | Agreed 14 Oct 2026. No separate deployment: `tenant_domains` maps the hostname to the office. Custom domains stay deferred for other offices; this one is the exception because it predates the product domain. Hosting settled 15 Oct 2026: the domain and `www` are already free Cloud Run domain mappings (with managed HTTPS) on the `portal` service; the rewrite ships as a new revision of that same service, so the mapping and its cost do not change |
| A24 | Minimal project creation; content edited on the project page, settings in the painel | Agreed 14 Oct 2026. Creation asks for the project name and the client's name (shown prominently in the painel), plus the project type and its stages (A27). Narrowed 16 Oct 2026: day-to-day content (description, details including project type, stages, progress and completion, meeting, files) is edited only in the staff edit mode of the project page. The painel edits the project's settings in the prototype's "Projeto" dialog: name, client, cover (also from the card's photo button), client link and access (with the client page, slice 2), and archiving. No delete for now. Uploads happen per stage on the project page. Revised 18 Oct 2026 (Fabio): the name can also be changed from the title in the project page's edit mode (the same change as the dialog's; the address stays). See section 10 and the [changelog](decision-changelog.md) |
| A25 | File versions named `v1, v2, v3`; "send new version" and same-name upload prompt; automatic grouping of clear `vN` names | Agreed 14 Oct 2026, revising A08. Uploading a file with an existing name asks whether it is a new version; if so it is stored as the next `vN`. Existing files are never renamed (the write scope cannot rename files the app did not create); an unnumbered original is shown as v1. Refined 15 Oct 2026: the client page shows the clean name with a separate version badge, while the copy in Drive carries the version (`Planta v3.pdf`); grouping only within one folder; clashes are flagged, never merged; current = highest version. See section 12 and the [changelog](decision-changelog.md) |
| A26 | Built-in options live in code and are translated; office-written content is stored as typed | Agreed 15 Oct 2026. Refined the same day: values the code **acts on** (status, access mode, roles, a detail's value type, languages, error codes) are enums stored with a CHECK; **content the app only displays** (project types, detail types, built-in stages with their descriptions, each type's usual stages) lives in reference tables with its texts per language, referenced by foreign key, and the code keeps enums naming the built-in rows (a test keeps them in step). Interface text lives in one translation catalog per language shared by the server and the staff app. Anything an office writes (custom details, custom stages, notes, descriptions) is stored as text and never translated. "Supports a language" means the product's own text and built-in options are translated. See sections 7 and 16 |
| A27 | Typed project details; project type chosen at creation, with its usual stages | Agreed 15 Oct 2026 (prototype review). Details are text, choice, area (m²) or date, formatted per language. Project type is a column with four built-in types: Projeto Arquitetônico, Projeto de Interiores, Projeto de Reforma, Projeto de Paisagismo. Revised 16 Oct 2026 (Alinea's partners): creation asks for the type; all 12 built-in stages are listed in one fixed order, the type's usual ones ticked, and staff tick or untick any. Each type gives its stages its own description; a stage outside its type's list uses a general one. Built-in stages have a description only (no separate deliverables). Stage templates are gone. The pilot offers only built-in details, types and stages; office-defined ones are a later addition. See sections 7 and 10 |
| A28 | One feed of client-visible project events | Agreed 15 Oct 2026 (prototype review). New files and versions, stage notes, stage progress (advanced, project completed) and meeting changes are recorded once as `project_events`; the client page's "latest updates" panel, the project's "last updated" date and email batching (A12) all read it. Which of them email: A32 (not notes). See sections 7 and 14 |
| A29 | A project address (slug), once used, stays reserved for that project | Agreed 15 Oct 2026. Old slugs keep redirecting and can never be given to another project in the office, so an old client link cannot land on someone else's project. See section 6 |
| A30 | Staff app and API stay compatible across a deploy | Agreed 15 Oct 2026, correcting "one revision means the staff app can never run against another API version": an open tab keeps the old code. Fingerprinted assets, a build ID on API responses, a reload prompt that keeps unsaved edits, and API changes compatible with the previous release. See section 4 |
| A31 | Uploads go from the browser straight to Drive | Agreed 16 Oct 2026 (Fabio), first part of slice 3b. Any staff member uploads into a stage from edit mode. The app checks the request (staff, project not archived, the stage's folder, at most 100 MB a file) and opens a Google resumable upload in that folder through the office's grant; the browser sends the bytes to Google, never through Cloud Run. A file with a name already there is kept beside it until versions (A25) arrive. The 100 MB cap settles the upload cap that section 24 listed as open; usage metrics (future ideas) may move it. "Ocultar do cliente" renames a file with a leading `_` (A05's hidden names); the office's grant (`drive.file`) reaches only files the app uploaded, so a file put straight into Drive is hidden by renaming it there. Versions, covers in Drive and usage metrics are later. See section 11 |
| A32 | Client email updates: what, to whom, from where, and how often | Agreed 16 Oct 2026 (Fabio). Staff list the client's addresses in the Projeto dialog, several per project (`project_recipients`). An email goes out for new files on the page, a stage advanced or the project completed, and a meeting scheduled, changed or removed; a stage's note does not email (it still counts for the updates panel). Batching as A12, 45 minutes quiet and 2 hours at most, confirmed for the pilot. Each office sends from its own domain once that domain is verified with the provider (Alinea: `alineaarquitetos.com`); until then, and for every other office, from the product's general domain with the office's name. Replies go to the office's contact email (office settings), else its owner. Locally and in tests a collecting fake records emails; staging sends only to allowlisted addresses. One Cloud Scheduler job calls the maintenance endpoint every 10 minutes (A09, A19), staging first. See section 14 |
| A33 | Product name and domain: **Unio**, `myunio.app` | Agreed 17 Oct 2026 (Fabio). `myunio.app` is the `{product-domain}` throughout this plan, registered at GoDaddy. Alinea keeps `alineaarquitetos.com` (A23); later offices are served at `{office}.myunio.app` (A21). `.app` domains are HSTS-preloaded, so every address on it works over HTTPS only (Cloud Run's managed certificates already do that). Hosting region is still open (section 24). See the [changelog](decision-changelog.md) |
| A34 | Staff change files on the website, not in Drive | Agreed 17 Oct 2026 (Fabio). The project page does not send staff to Drive: no "Abrir no Google Drive" action on a file or stage. (The Drive settings page keeps its link to the office's connected folder: that is about the connection itself, not a way to change a project's files.) Drive keeps working for whoever prefers it, but every everyday change is offered on the project page. Each file's "⋯" menu offers "Definir como capa" (images), "Mover para outra etapa" (a list of the other stages) and "Ocultar do cliente"; dragging a file onto another stage is a later addition doing the same move. A file put straight into Drive can be shown but not changed through the office's grant (drive.file): the site says, in plain words, to make that change in the stage's folder; authorizing such files through the Picker stays a later option (section 9). See section 11 and the [changelog](decision-changelog.md) |
| A35 | No drafts for now: a new project is published at once | Agreed 17 Oct 2026 (Fabio). Creation makes the project `active`, so its client page answers as soon as it exists; there is no "Publicar" step or "Rascunhos" group. The `draft` status stays allowed in the database, unused, so drafts can return without a schema change; existing drafts were published (migration 0024). The publish endpoint and the staff bar's "Publicar" button stay, shown only on a draft: one the previous release creates while a deploy is under way, and its open tabs, still have a way out (A30). Replaces the draft step of 15 Oct (section 10). See the [changelog](decision-changelog.md) |

Explicitly deferred: full billing automation, SMS/WhatsApp, custom customer
domains (except the first office's existing domain, A23), multiple portal templates, SSO, arbitrary custom CSS/HTML, client
accounts, comments/approvals, complex professional-level pricing, hosted
original-file storage, and staff roles beyond owner/member (see section 5).
These are extension points, not parallel pilot projects.

## 3. What to retain and what to replace

The current app is a useful behavior reference, not the architecture to generalize.
It has one global Drive root, office identity, language, timezone and dashboard
password. `ProjectStore` combines Drive traversal, metadata parsing, visibility,
cache management and view models. Office configuration is read from environment
variables, and some branding is hardcoded. Project metadata is parsed from
`_project` and stage text files. The dashboard uses a shared password. Downloads
already stream through Flask. The notification bell is a browser-local recent-file
indicator; it does not provide reliable email notifications.

Retain or selectively adapt:

- The client page layout, timeline, meetings, search, collapsible stages, theme
  toggle and small JavaScript components.
- Portuguese copy and translations, moved into tenant-aware/request-local rendering.
- Parsers as **legacy import tools**, with characterization tests for old inputs.
- Existing fake Drive, editable-folder simulator, generators and local backup flow.
- Small Drive HTTP utilities when their behavior fits the new adapter contract.
- Tests for hidden-file access, previews, stage behavior, mobile layouts and exports.

Replace:

- Global office configuration and in-memory project discovery as the source of truth.
- Shared dashboard passwords and signing keys derived from them.
- Filename matching as authoritative version identity.
- Request-time recursive Drive discovery and process-local background work.
- Bare provider file IDs as the application's only file identity.

Build a separate package such as `backend/` with its own application factory and
entry point. Keep `app.py` available for the legacy site until migration. Reuse
presentation components deliberately; do not maintain two permanently equivalent
products. Transfer the selected UI into the new entry point, establish parity,
then remove legacy runtime code after the rollback period. Old parsers remain
available to imports for as long as supported.

Suggested layout:

```text
backend/
  app.py                 application factory, dependency wiring
  config.py              typed deployment settings; no tenant state in env
  tenancy/               hostname resolution and tenant context
  identity/              staff accounts, sessions, password links
  projects/              project metadata, stages, access policies
  documents/             documents, revisions, publication and previews
  storage/               provider contract, Google adapter, fake adapter
  connections/           OAuth lifecycle, read identities, capabilities
  sync/                  cursors, reconciliation and change normalization
  notifications/         subscriptions, batching, delivery adapters
  jobs/                  leases, retries, durable work and outbox
  branding/              validated themes and assets
  web/                   FastAPI routers, forms, Pydantic request/response models
  db/                    models and repository implementations
migrations/              reviewed Alembic migrations
frontend/             React + TypeScript: staff administration and the client page (A20), built by Vite
  src/                   screens, components, API client generated from OpenAPI
  package.json           own lockfile; Node is used to build, never at runtime
```

`backend/` serves both audiences: the client project pages (the page's shell with
its preview tags, and a public JSON API that returns only what the page may show)
and the JSON API the staff app uses, over one shared set of services, so there is
a single copy of rules such as "who may see this file". `frontend/` holds the
source of both React apps (painel and client page) and never runs as a server.

Modules call explicit services; templates do not call Google or construct SQL.
A service takes tenant context and dependencies explicitly. A background job
constructs that context from its stored tenant, never from ambient HTTP state.
Use ordinary Python classes/functions, not a generic plugin or event framework.

FastAPI dependencies provide explicit tenant, staff and service context to route
handlers; services still enforce authorization and database constraints. Pydantic
validates input and controls response fields. Keep input/output schemas separate
from SQLAlchemy persistence models, especially for credentials, password hashes
and internal IDs. Alembic still manages database schema changes. OpenAPI provides
the API contract for the staff app (A20): generate its TypeScript types from the
schema in CI, so a backend change that breaks the staff app fails the build
instead of failing in a browser. The client page uses the same generated types.

Use asynchronous HTTP calls for Drive streaming and an async SQLAlchemy/psycopg
database path in the new request handlers. Initialize reusable clients/pools
through application lifespan and close them on shutdown. Do not call blocking
legacy `requests` helpers directly inside async handlers; adapt or isolate them
during migration. CPU-heavy preview work belongs in bounded worker jobs. FastAPI
background tasks are not the durable provisioning or notification queue.

Port Flask-specific template helpers, redirects, session handling and CSRF
protection explicitly. FastAPI does not supply the application's complete browser
authentication/access policy just by declaring API models. Retain tests for both
server-rendered pages and JSON routes as these integrations change.

Staff app boundaries (A20): it talks only to the JSON API, never to Google or the
database directly, and holds no credentials in browser storage. Authentication is
the same host-only session cookie as the rest of the site; the app reads a CSRF
token from the session and sends it on every state-changing request. The current
prototype's painel (Jinja templates plus small modal scripts) is the behavioral
reference for its first screens.

## 4. Deployment shape and data flow

**POC simplification under discussion:** following the cost review, first evaluate
one web deployment with an authenticated maintenance endpoint called every 10
minutes (A09; Cloud Scheduler charges per job, not per run, and Cloud SQL is
always on, so a shorter interval costs nothing extra). The
worker below is a logical function and need not be a separate deployed service.
The fuller queue and wildcard load-balancer design remains an alternative, not
a prerequisite for the POC. Offices get subdomains behind a load balancer (A21,
below); slower refresh timing still needs agreement.
The cost comparison records those tradeoffs explicitly.

```mermaid
flowchart LR
  Client[Client or office browser] --> Web[FastAPI web application]
  Web --> DB[(PostgreSQL)]
  Web -->|authorize and stream| Read[Office-scoped Drive reader]
  Web -->|authorized uploads| Write[Office OAuth writer]
  Read --> Drive[Office-owned Google Drive]
  Write --> Drive
  Scheduler[Authenticated scheduler] --> Worker[Worker: sync, provision, notify]
  Worker --> DB
  Worker --> Read
  Worker --> Write
  Worker --> Mail[Email adapter]
```

Use one deployable codebase with web and maintenance handlers. The diagram shows
the logical recurring-work path, not a settled choice of queue technology.
Workers process bounded durable work, checkpoint long tasks, and exit before
their request deadline. Never start untracked in-process tasks and assume Cloud
Run will keep them alive.

### One origin per office: pages, staff app and API (A20)

Each office is served by the one FastAPI service, from one origin. The product
domain is `myunio.app` (A33). With office subdomains (A21) the layout is:

```text
{office}.{product-domain}/{slug}             client pages: React, shell and preview tags from the server (A20, A22)
{office}.{product-domain}/painel/...         staff app: React, static files
{office}.{product-domain}/api/...            JSON API used by the staff app
auth.{product-domain}/...                    shared Google login (section 5)
```

Because pages, staff app and API share an origin, the session cookie works
without CORS, cross-site cookies or tokens in browser storage. State-changing
API calls carry a CSRF token (section 17).

How the staff app is served:

1. `vite build` produces one `index.html` plus JavaScript/CSS files whose names
   contain a content hash.
2. FastAPI serves those files under `/painel`. Any other `/painel/...` path
   returns `index.html` and the app's router shows the screen. Unknown `/api/...`
   paths still return JSON 404s, never the app shell.
3. Hashed files are cached for a year (`immutable`); `index.html` is never cached,
   so a deploy reaches staff on their next navigation.
4. Content Security Policy for the staff app: scripts and styles from `self` only.

The image is built in two stages, so Node exists only at build time:

```dockerfile
FROM node:22-slim AS frontend            # supported Node LTS; pin exact version
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build                        # → /frontend/dist

FROM python:3.13-slim                    # production Python target
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY backend/ backend/
COPY --from=frontend /frontend/dist backend/static/frontend
CMD ["sh", "-c", "uvicorn backend.app:create_app --factory --host 0.0.0.0 --port $PORT"]
```

Client pages, API and staff app always ship together in one revision, and a Cloud
Run rollback reverts all three at once. That does **not** keep an already-open
browser tab in step (A30): it keeps running the previous build's JavaScript, calls
the new API, and may request lazily loaded files the new revision no longer has.
So: built assets have fingerprinted names (Vite's default) and are cached for a
long time, while the app shell is never cached; every API response carries the
build ID; when the staff app sees a newer build, or fails to load one of its own
files, it offers "Nova versão disponível — recarregar" without discarding unsaved
edits; and API changes stay compatible with the previous release (add fields,
do not repurpose or remove them in the same release). Keeping the previous
build's assets available for a few days is a later option if reloads annoy. `gcloud run deploy --source` builds from
a root `Dockerfile` when one exists. **Adding that file therefore changes how the
current Flask site deploys**: introduce it with the new entry point at cutover,
or keep it outside the source-deploy path until then (section 19).

Local development: Vite's dev server serves the staff app with hot reload and
proxies `/api` to the local FastAPI process. The release check builds the bundle
and serves it through FastAPI, as production does. Only staff app work needs Node
locally; client pages and backend work do not.

### Office address: office subdomains behind a load balancer (A21)

Offices are served at `{office}.myunio.app`, behind a load balancer in front of
Cloud Run (A21, decided 17 Oct 2026). The comparison below is the analysis that
decided it; option B is not an available design.

| | A: office subdomains | B: one domain, office paths |
| --- | --- | --- |
| Example client link | `alinea.{product-domain}/casa-jardim` | `{product-domain}/alinea/casa-jardim` |
| Front door | Global external Application Load Balancer with serverless backend, wildcard DNS and Certificate Manager certificate (DNS authorization). Restrict direct Cloud Run ingress | See "B front doors" below; each has a caveat |
| Fixed cost | ~$18.25/month forwarding rule plus data processing, before traffic | None for the front door itself |
| Tenant resolution | From hostname (`tenant_domains`, section 5) | From the first path segment; every route, link builder and test carries it |
| Browser isolation between offices | Each office is its own origin: cookies, storage and any script bug stay inside one office | All offices share one origin. Cookies need tenant-bound sessions; browser storage is shared; a script bug could affect every office |
| Staff login | Shared `auth.` callback plus single-use handoff to the office host (section 5) | One callback on the one domain; simpler |
| Product feel | Each office has "its own" address; custom domains later fit naturally | Reads as a shared platform; custom domains later still need a load balancer |
| Later change | — | B → A needs permanent redirects for every shared link |

B front doors, as documented by Google
([Cloud Run domain options](https://docs.cloud.google.com/run/docs/mapping-custom-domains)):

- **Cloud Run domain mapping:** no extra charge, but Preview, "not recommended
  for production services" because of latency, limited to some regions (including
  `us-east1`), no wildcard certificates, and maps a hostname to the service root.
- **Firebase Hosting rewrite to Cloud Run:** low cost and GA, but every request
  is cut at **60 seconds**, so long file streams (A11) and slow uploads fail with
  504. Only a cookie named `__session` reaches the app, and it becomes part of the
  CDN cache key. It also needs the Blaze plan.
  ([Hosting serverless limits](https://firebase.google.com/docs/hosting/serverless-overview),
  [cookie handling](https://firebase.google.com/docs/hosting/manage-cache))
- **Default `run.app` URL with office paths:** free and GA, but a Google-branded
  address; acceptable only for an internal POC that shares no client links.

**Decided 17 Oct 2026: A** (Fabio), as recommended: every B front door either is
not production-ready or breaks large file delivery, and B's main saving is about
$18/month, covered by credits for the first three months. The balancer is built
before the second office's first client link; until then the one office is served
through Cloud Run domain mappings (`alineaarquitetos.com`, and `myunio.app` for
Unio's own pages). Staging stays on a domain mapping (`staging.myunio.app`).

The balancer's certificate map must cover every hostname moved behind it, each
authorized in Certificate Manager (DNS authorization) before its DNS changes: a
wildcard covers only first-level subdomains, not the apex or another domain. So:
`*.myunio.app` and `myunio.app` (one certificate), and `alineaarquitetos.com` and
`www.alineaarquitetos.com` (another, or one per office domain as custom domains
arrive). `.app` is HSTS-preloaded, so a gap on `myunio.app` would lock browsers out
rather than warn.

### Scheduling and queue technology: proposal under discussion

The original minute-by-minute scheduler plus PostgreSQL queue was a recommendation,
not an agreed product decision. Separate three responsibilities: a scheduler
decides when recurring work is due, a queue preserves pending work, and a worker
executes it. FastAPI itself does not replace any of these durable responsibilities.

| Option | Technology | Benefit | Main tradeoff |
| --- | --- | --- | --- |
| E: revised POC proposal | One Cloud Scheduler job (every 10 minutes) or local cron → authenticated endpoint in the web service | One deployment; no broker/managed task queue | Slower Drive discovery; bounded work shares web resources; retain retryable state and overlap protection |
| A: original proposal | Cloud Scheduler → Cloud Run worker → PostgreSQL jobs | Few services; portable; easy to exercise against local PostgreSQL | We implement leases, retries, recovery and dispatch; minute polling keeps the DB awake and adds dispatch latency |
| B: managed queue alternative | Cloud Tasks → Cloud Run worker, with Cloud Scheduler for recurring checks/recovery | Managed delivery retries, delayed tasks and dispatch limits; enqueue work promptly | Provider-specific adapter and cloud integration tests; SQL idempotency/outbox still required |
| C: established Python queue | Celery with Redis/RabbitMQ, dedicated workers and Beat for recurrence | Mature Python task ecosystem; useful for substantial continuous work | Additional broker and always-running processes to operate and fund |
| D: dedicated scheduler/worker process | APScheduler or cron plus durable PostgreSQL jobs on an always-on host | Reasonable for a small VM deployment | Own process supervision, availability and coordination; does not fit a scale-to-zero web process |

[Cloud Tasks behavior](https://docs.cloud.google.com/tasks/docs/dual-overview),
[Celery](https://docs.celeryq.dev/en/stable/getting-started/introduction.html),
[APScheduler](https://apscheduler.readthedocs.io/en/master/userguide.html).

Evaluate **E first for the POC**, subject to confirming freshness and domain
tradeoffs. Keep cursors, pending batches, provisioning progress and operation IDs
in SQL; prevent overlapping execution and safely resume partial work. No general
queue framework is necessary. Process within the HTTP request and a bounded
deadline; report unfinished work for a subsequent/manual retry. Verify the
scheduler's identity and allowed caller in the endpoint itself, since the web
service also allows public requests. **Prefer Cloud Scheduler when a free job is
available in the billing account; retain local cron as an alternative.** This
scheduling preference does not require Cloud Tasks or a separate worker service.
Use one shared job for all offices. Before setup, confirm the account-wide free
allowance rather than assuming each project receives its own. Local cron calls
the same protected endpoint with an authorized credential outside the repository,
but processing pauses while its host is asleep or disconnected. Enable only one
timer; both options still incur the same endpoint/database work. See the
[cost comparison](infrastructure-cost-comparison.md) for timer pricing and limits.
Record a last-success time so failures are visible. Check database free-tier
limits and restore needs before selecting a paid plan.

If background volume or latency later warrants a queue, **B is the preferred
Google Cloud alternative**, subject to review. In that alternative use
Cloud Tasks for provisioning steps, synchronization and delayed email delivery;
use a small number of shared scheduler jobs for recurring Drive checks, watch
renewal, reconciliation and recovery. Do not create a scheduler resource per
office/project. Queue payloads contain internal IDs, never documents or tokens.
Tasks have at-least-once delivery and no exact execution-time guarantee: show
provisioning progress and interpret an email deadline as earliest eligibility.

Commit business state and an outbox event in one SQL transaction, then attempt
dispatch after commit. A scheduled rescue pass retries undispatched events;
otherwise a crash between database commit and enqueue could lose work. Keep
application-level job state, deduplication, stale-connection rejection and
reconciliation of uncertain external side effects. Cloud Tasks owns transport
retry timing; avoid an independent SQL retry loop scheduling duplicate attempts.
Persist failure/attention state before acknowledging terminal failures, and
detect stale work if the managed queue exhausts retries.

Under A, begin with one scheduler invocation per minute and a roughly 45-second
work budget. Under B, bounded handlers run on task delivery; recurring Drive
polling remains approximately every two minutes initially. A less frequent rescue
scan can be tuned separately. Neither option lets the database sleep while we
continue frequent Drive polling. Do not claim savings from event-driven delivery
until the polling behavior actually changes.

Local tests run the same handlers using a controllable clock and an isolated
queue adapter; exercise duplicate delivery, retries and crashes after commit.
Real-cloud acceptance separately verifies IAM, delivery deadlines and retry
behavior. A local fake cannot prove the provider's configuration. Choose E, A or B
before implementing dispatch; do not build multiple production queue systems.
The [infrastructure cost comparison](infrastructure-cost-comparison.md) records
cost assumptions and free allowances for this decision.

If a separate worker is introduced, use the same immutable image for both entry
points. Maintenance must reject unauthorized calls, whether its HTTP route is
on the public web service or a separate worker. Runtime credentials have only the access needed
for its jobs. Preview processing has explicit byte/time limits so a large file
cannot monopolize synchronization or email.

Cloud Run is a proposed continuation of current hosting. Managed PostgreSQL avoids
making database maintenance a nights-and-weekends responsibility. The provider is
Cloud SQL for PostgreSQL (A16): one small instance in us-east1, next to the Cloud
Run services, with a separate database and database user each for staging and
production. The app connects through Cloud Run's Cloud SQL connector with IAM
database login, so no database password is stored. Confirm the instance price,
backup retention (daily, 7 days by default), point-in-time recovery and
connection limits when creating it, and prove a restore before it holds an
office's only project metadata. The smallest shared-core machines have no uptime
SLA and few connections: keep pools small and upgrade when the pilot grows.
Region and jurisdiction commitments remain an explicit choice; measure latency
from Brazil. A shared-core instance is always on, so frequent polling does not
change its cost the way it would for a serverless database. Later wake-up optimization is possible without
changing the durable-job model.

For the fuller Cloud Run office-subdomain design, use a global external Application Load Balancer
with a serverless backend, wildcard DNS and a Certificate Manager certificate
issued through DNS authorization. Route office hosts to the same application;
do not create a deployment per office. Cloud Run's built-in domain mapping does
not support wildcard certificates. Restrict the web service's direct ingress so
the intended front door cannot be bypassed, while keeping the worker separately
authenticated. Staging uses its own hostname/certificate coverage and services;
`*.product.com` alone does not cover `office.beta.product.com`.
[Cloud Run domain options](https://docs.cloud.google.com/run/docs/mapping-custom-domains),
[DNS-authorized certificates](https://docs.cloud.google.com/certificate-manager/docs/deploy-google-managed-dns-auth).
Quote load-balancer, certificate and transfer costs before approving infrastructure;
one forwarding-rule price is not the total hosting bill.

To avoid that fixed load-balancer cost in the POC, explicitly choose another
domain path first. A temporary `run.app` URL with tenant paths changes the agreed
URL requirement; individual subdomain mappings preserve it but are Preview and
not recommended by Google for production. Neither is approved by this proposal.
The cost comparison distinguishes a near-free constrained POC from the fuller
wildcard deployment; do not describe ~$65/month as the unavoidable pilot minimum.

Start with small connection pools and capped instances. Calculate maximum DB
connections as the sum of every process's pool across every possible instance,
plus maintenance headroom. Request-scoped sessions close promptly; no SQL
transaction or connection remains open while streaming a large file. A database
outage should yield a recoverable application error, not bypass authorization.

### FastAPI deployment and free-tier implications

The existing repository uses Cloud Run source deployment with Python 3.13 and a
Gunicorn `Procfile`. Google also documents a direct FastAPI source-deployment
workflow; Flask is not a requirement for this hosting path.
[Cloud Run FastAPI quickstart](https://docs.cloud.google.com/run/docs/quickstarts/build-and-deploy/deploy-python-fastapi-service)

For the new backend, explicitly replace the legacy WSGI startup command with an
ASGI server. Proposed command, once `backend.app:create_app` exists:

```sh
uvicorn backend.app:create_app --factory --host 0.0.0.0 --port "$PORT"
```

Declare and pin the server dependency. Start with one server process per
container and tune Cloud Run concurrency/max instances and database pools from
measurements. Keep the legacy `Procfile` unchanged until the new entry point is
implemented and release-ready. With the staff app (A20) the new service builds
from the two-stage Dockerfile above rather than buildpacks; the same caveat
applies: a root `Dockerfile` takes over source deploys of the legacy site. Maintain streaming rather than buffering file
responses; test large transfers, timeout and client-disconnect behavior through
the actual deployment path before migration.

Cloud Run free-tier eligibility depends on resource usage and billing settings,
not Flask versus FastAPI. Prefer request-based billing and zero minimum web
instances initially, accepting cold starts. There is no framework surcharge or
need for an always-running server just because FastAPI uses async. CPU/memory
use can differ, so equal application traffic does not guarantee equal cost.
Build/image storage and outbound transfer have separate charging rules. The
database, wildcard-domain infrastructure and scheduled work need their own budget.
[Cloud Run pricing](https://cloud.google.com/run/pricing)

No promise that the complete multi-tenant product stays free follows from keeping
the web service within its allowance. The framework switch itself does not
require abandoning Cloud Run, purchasing a higher hosting tier or introducing a
separate frontend deployment; neither does the React staff app (A20), which is
static files inside the same image. These are planning decisions only; no live billing
settings, deployment configuration or cloud resources were changed for this update.

## 5. Tenant routing and staff identity

Offices are served on their own subdomains (A21, option A).

Resolve the normalized hostname against a `tenant_domains` table. Accept only
configured product suffixes or explicitly verified custom domains. Reject unknown
hosts; never fall back to the first office. Handle casing, ports, trailing dots
and invalid labels deliberately. Reserve names such as `www`, `auth`, `admin`,
`api`, `beta`, `support` and `mail`. Keep office URL slugs stable and unique.

Behind a proxy, trust forwarded headers only from the actual trusted proxy path.
Do not derive OAuth callbacks or password-reset links from an arbitrary Host
header. Construct external links from stored canonical domains.

Recommended staff login: Google OpenID Connect, separate from Drive connection
consent. Someone may administer a portal without being the Google account that
owns its files. Identify users by verified provider subject, not mutable display
names. Invitations bind a verified email to an office's account; never grant
access merely because a user's email has the office's domain.

**Several staff per office, with roles: foundations now, features later.** From
the first version, an office has any number of staff accounts (`users`, each
belonging to one office, with a role), every staff action goes through one central
permission check, and audit events record who acted. A person working for two
offices has an account in each (decided 14 Oct 2026, see the changelog); a shared
identity across offices (users plus memberships) is a later migration if a real
need appears. Each person has their own login; there
is no shared office password. The pilot uses only the `owner` role, and accounts
for additional staff can be created by hand. Deliberately deferred as an add-on
for larger offices: invitation and role-management screens, finer roles (for
example editing projects without access to office settings or the Drive
connection, or read-only staff), and per-project permissions. Do not build these
early; when they come, they extend the permission check and the role values
rather than changing the login or the data model.

Use a maintained OAuth/OIDC library, such as Authlib, with state, nonce, PKCE and
strict callback validation. Centralize Google callbacks on an auth subdomain so
each new office does not require another registered redirect URI. Complete login
on the target office through a short-lived, single-use handoff code. Bind that
code to the initiating tenant and browser flow, store only its hash, and reject
replay, wrong-host and mismatched-browser redemption. Preserve the initiating
browser proof in a host-only cookie. Exact protocol handling gets its own tests
and security review; do not improvise a cross-subdomain token in localStorage.

Staff roles for the pilot:

| Actor | Read public project | Administer project/files | Invite staff / Drive connection / office settings |
| --- | --- | --- | --- |
| Anonymous visitor | Yes, or project password challenge | No | No |
| Office member | Yes, including password-protected projects through staff access | Yes within their office | No |
| Office owner | Yes | Yes | Yes |
| Platform operator | No automatic customer-content browsing | Explicit audited support action only | Operational tools with audit |

Keep roles small. Store an optional responsible professional and later project
assignments without making every office adopt a complex permission hierarchy.
Owner transfer must leave at least one owner. A revoked membership invalidates
sessions or is rechecked on each administrative request.

Use random secret signing material independent of user passwords; server-side
sessions with rotation on login, secure/HttpOnly/SameSite cookies in production,
and **no parent-domain cookie** shared by every office. Staff mutations use CSRF
protection. Password attempts, login handoffs and invitations are rate-limited.
Local test mode uses an explicit fake identity provider and is refused in
production configuration; it must never become a hidden production bypass.

## 6. Public projects and optional passwords

Choose `access_mode = public | password`. Public means a person with the URL can
view and share the page without signing in. Default to unlisted pages with
`noindex`, no public office-wide project directory and no referrer leakage.
These reduce accidental discovery; they are not access control. Explain this
plainly when an office chooses public access. A publicly accessible project need
not make the underlying Drive folder publicly shared.

Route (A22): `https://{office address}/{project-slug}`, as the current site does.
Slugs are unique per office, readable and stable once a link is shared; renaming
a project does not change its slug. Reserved paths (`painel`, `api`, `static`,
`healthz`-style names) cannot be slugs. A slug is guessable by design: public
mode is not a secrecy promise, and projects that need privacy use a password.
Office staff can change a slug deliberately; the old one keeps redirecting so
links already sent to clients do not break. **A slug, once used, stays reserved
for its project (A29):** current and old slugs live in one table (`project_slugs`,
exactly one current per project) and share one namespace per office, so another project can never take an old slug
and receive a client's old link. This holds after a project is deleted too:
projects are soft-deleted and keep their slugs, so an old link answers "not
found" (the same as an unknown address or a draft, so none can be told apart)
instead of showing someone else's project.

For password mode, office staff set/reset the password through the panel (the
"Projeto" dialog; at least 6 characters). A device stays unlocked for 90 days;
five wrong passwords from one device make it wait 15 minutes (kept in memory
per instance, proportional to a shared link's password). As built in 2.4, the
grant is a signed cookie per project carrying its `access_version`. This
interprets “clients can add a password” as the office/customer controlling the
setting; anonymous project viewers cannot change access policy. Store an
adaptive password hash, never recoverable plaintext. A successful challenge
creates a session grant scoped to `(tenant, project, access_version)`. Password
changes and policy changes increment that version. Apply the same policy to the
page, file bytes, thumbnails, revisions, search, calendar exports and API calls.

A tenant ID and project ID on the request are never sufficient authorization.
The resolved host, session membership/access grant, database row, folder boundary
and provider connection must agree. Return a non-disclosing not-found response
for wrong-tenant resources. Cache keys include tenant, project and revision;
private/protected responses cannot enter a shared public cache. On access-mode
changes, invalidate authorization caches and purge generated preview access.
Use no-store for password challenges and protected content where browser caching
would defeat the office's intended change in access.

An office can choose public access while another chooses passwords. Email
subscriptions do not grant administrative or password-protected access. Do not
send the password alongside every notification. A future client-account mode
can extend `access_mode`; it is not required to ship the first pilot.

## 7. Data model and database boundaries

Use UUID identifiers, UTC timestamps, explicit state values, and soft deletion
where recovery/audit requires it. Render dates in each office's IANA timezone.
Use relational fields for core relationships; JSONB is appropriate for bounded
custom project details and provider-specific metadata, not for all business data.

The following is a logical schema specification, not a migration:

| Table | Main fields / purpose |
| --- | --- |
| `tenants` | ID, display name, slug, locale, timezone, lifecycle, plan/feature settings |
| `tenant_domains` | hostname unique, tenant ID, canonical/alias status |
| `users` | tenant, email (unique per tenant), display name, role (owner/member), password hash (none for Google-only accounts), later identity provider + subject |
| `password_links` | tenant, user (same tenant), kind (invite/reset), token hash, expiry, used time; one-time links for people to choose their own password (step 1.5b). Reset links also come from "Esqueceu a senha?" on the sign-in screen (18 Oct 2026): emailed from the office's address, built on its stored domain, with the same answer whether or not the account exists, at most one email every 2 minutes per account and 5 requests per device in 15 minutes |
| `sessions` | tenant, user (same tenant), token hash, CSRF token, last seen, expiry, revoked |
| `drive_connections` | tenant, provider account subject, root ID, drive ID/type, read identity, write-token secret reference, separate read/write health, generation |
| `projects` | tenant, title, client name (≤ 30 characters entered from 18 Oct 2026; the database allows 48), cover image reference, status (`active` from creation, `completed`, `archived`; `draft` unused for now, A35; see section 10), slugs in `project_slugs`, connection, root/deliverables folder IDs, description, project type (built-in enum, A27), optional professional, access mode/hash/version, current stage, last client-visible activity time (A28), row version |
| `project_slugs` | tenant, project, slug, is current, created; every address a project has had, exactly one current. Unique per tenant across current and old, so a used slug stays with its project (A29); old ones redirect. Reserved paths (`painel`, `api`, …) refused |
| `project_types` | key, order, label per language. Built-in rows from a migration (A26) |
| `detail_types` | key, value type (text/area/date), order, label per language. Built-in rows from a migration; offices' own later (A27) |
| `stage_definitions` | key, order, title and a general description, each per language. The 12 built-in stages, from a migration (A27) |
| `project_type_stages` | project type, stage; the type's usual stages (ticked at creation) and the type's own description of each, per language (A27) |
| `project_details` | tenant, project, detail type (foreign key to `detail_types` by key and value type, so the database knows the value's type), order, the value in the column of its type (text, number in m², date). Pilot: built-in detail types only (A27) |
| `project_stages` | tenant, project, stable stage key, **either** a built-in stage key (title and explanations translated) **or** office-written title and explanations, order, status, notes and when they last changed, bound folder ID |
| `meetings` | tenant, project, title (≤ 40), start/end (end after start), timezone, location (≤ 60), link (`http`/`https` only); several per project: the client page shows the next one by date, so a past meeting stops showing on its own (agreed 15 Oct 2026) |
| `folder_bindings` | tenant, project, connection, provider folder ID, parent ID, path display, classification |
| `storage_items` | tenant, connection, provider file ID, parent, MIME, name, size, checksum/revision metadata, observed capabilities, present/trashed state, last seen |
| `documents` | tenant, project, logical title, stage, current revision ID, publication state |
| `document_revisions` | tenant, document, storage item, application sequence, label, observed content marker, source, published time, availability state |
| `project_recipients` | tenant, project, email, locale, subscription state, unsubscribe-token hash |
| `project_events` | tenant, project, kind (file published, new version, file withdrawn, note changed, stage advanced, project completed, meeting scheduled/changed/cleared), document/revision or stage reference, source fingerprint, detected/published times. Client-visible activity (A28): feeds the updates panel, the project's last-activity time and email batching; every kind but "note changed" can start an email (A32) |
| `notification_batches` | tenant, project, start/due time, state; events captured in batch-item rows |
| `notification_deliveries` | tenant, batch, recipient, idempotency key, provider ID, attempt/result timestamps |
| `operations` / `operation_steps` | tenant, type, request key/hash, state, result IDs, provisioning progress |
| `jobs` | tenant, kind, payload version, dedupe key, run-after, attempts, lease token/expiry, last safe error |
| `outbox` | tenant, committed event payload/version, dispatch status |
| `sync_cursors` | tenant, connection/generation, corpus/drive ID, page token, last successful poll/reconcile |
| `audit_events` | tenant, actor, action, resource ID, request/operation ID, safe change summary |
| `theme_settings` | tenant, template version, approved colors, asset references, draft/published version |

Tenant-owned rows have non-null `tenant_id`. Use composite unique keys and
foreign keys such as `(tenant_id, project_id)` so a programming mistake cannot
attach office A's document to office B's project. Every query path requires a
tenant; code review rejects generic `get_project(id)` outside explicitly global
operations. Uniqueness includes tenant where appropriate and provider connection
for file identity. Provider IDs and filenames are not global product primary keys.
Also constrain a document's current revision to belong to that same document,
not merely the same tenant. Prevent different offices from registering identical
or overlapping Drive roots by default; any intentional shared-source arrangement
would need a separately designed ownership/publication contract.

Add PostgreSQL row-level security as a second defense on customer tables. The
runtime role is neither table owner nor a bypass role. Set tenant context locally
inside each transaction and reset it automatically at transaction end. Missing
context denies access. Migration and tightly controlled global scheduling roles
are separate from request roles. Test policies through the **runtime role**, not
only an owner connection. PostgreSQL owners/bypass roles otherwise defeat the
intended test. [PostgreSQL row security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)

**Enums, reference tables and office content (A26).** If the code acts on a
value (status, access mode, role, a detail's value type), it is a Python
`StrEnum` stored as text with a CHECK built from the enum (PostgreSQL enum types
are hard to change). If the app only displays it (project types, detail types,
built-in stages and their descriptions, each type's usual stages), it is content: a row in
a reference table with its texts per language, referenced by foreign key, so the
database describes its own data and offices' own rows can join later. The code
keeps enums naming the built-in rows, and a test keeps enums and rows in step.
Office-written content is plain text shown as typed. Where a row can be either,
it holds exactly one of the two (a built-in key or custom text), enforced by a
CHECK.

Use optimistic row versions for simultaneous form edits: a stale update returns
a conflict with the latest values instead of silently replacing someone else's
work. External Google calls happen outside database transactions. Database
constraints, unique request keys and row locks protect concurrency; retries must
not depend on a single worker instance.

## 8. Source-of-truth and synchronization rules

| Data | Authority | Behavior when edited elsewhere |
| --- | --- | --- |
| Project title/client/status/meeting/stages/custom fields | PostgreSQL | Drive `_project` files are imported once, then ignored for product metadata |
| File bytes, physical filename/folder placement, trash | Google Drive | The client page reads it live (A10); the sync records changes as events, and later into the document index |
| Document grouping, revision labels, selected current revision | PostgreSQL | External files may create new documents/revision observations; do not silently overwrite manual grouping |
| Client visibility | Deliverables boundary plus DB project/access state | Moving out of the boundary removes portal availability |
| Recipients, email preferences, delivery results | PostgreSQL | Drive has no authority over them |
| Office appearance and users | PostgreSQL | Never read another office's environment/global cache |

The database is an authoritative store for some data and a rebuildable index for
other data. Distinguish those roles explicitly. A “rebuild index” must not delete
project descriptions, password hashes, recipient lists or version grouping.

Binding by Drive IDs survives renames. Renaming a stage folder does not
implicitly change the official stage title/order; show its updated physical name
in the file manager and let staff update the portal title deliberately. A deleted
and recreated folder has a new identity; flag the broken binding and offer an
explicit rebind, rather than guessing from its name. Moving a file between stages
updates placement; moving it to another project requires reassessing publication
and document grouping, never merely changing the parent foreign key.

## 9. Google connection and capability contract

Fabio's experiment establishes the useful core: OAuth creates/writes app-managed
files while the service account reads files uploaded through Drive. Build around
that result. The remaining live checks refine exactly which operations to expose;
they are not a prerequisite for coding the database, UI and workflow logic.

### Hard ordering constraint: share the folder while it is empty

Establishing the reader's access is **only possible while the folder contains
nothing the writer cannot see.** `permissions.create` on an app-created folder
succeeds normally, but once a Drive-uploaded file the writer did not create is
inside it, the same call fails with `appNotAuthorizedToChild`. Verified by
experiment: sharing a fresh empty folder returned 200; the same folder with a
user-dropped file inside returned 403.

Therefore the share is part of folder creation, not a later step: create the
folder, grant the reader, and only then expose the folder to the office. A
provisioning sequence that creates folders, reports success, and reconciles
reader access afterwards will pass every test where nobody uploads in between
and fail on the first real office that does.

This also sets the recovery behaviour. If a folder exists without reader access
and already has foreign content, **our** writer cannot repair the share, but the
office owner usually can: ask them to share the existing folder with the reader in
Drive (step-by-step instructions), verify the reader now sees its contents, and
resume. Only if that fails, create a new folder, share it while empty, and rebind;
the original may hold client files, so it is never the first resort. Record this
as a `needs_attention` outcome rather than retrying the failing call. **To verify
live** before writing the recovery screen: does an owner's share of the folder
give the reader access to files others had already put inside?

**Another Google account** (18 Oct 2026, Fabio). Reconnecting keeps the office's
folder when the new grant reaches it, i.e. the same account. Another account
cannot reach anything the app made with the first one (drive.file is per
account), so it is refused unless the owner chooses "Usar outra conta" after a
clear warning that the files stay behind. That choice is offered only while the
office is disconnected (or its grant expired): then nothing else can create or
change folders, so every project and stage moves, none in the meantime. Then the office **starts afresh** in
the new account: a new root folder shared with the reader while empty, a new
empty folder for every project and stage (all-or-nothing: any failure, Drive's
or the database's, rolls back and trashes the new root; an expired old grant is
revoked only once the switch is saved), covers and the logo dropped (they were files in the
old account), and each project's next scan set to only note what is there, so
re-uploaded files don't email clients. Names, stages, notes, details, meetings,
addresses and recipients are kept. The old account's folders are left untouched.
A tool to carry files across is a future idea.

The reader has read-only scope and explicit sharing permission on the office's
designated root. The writer uses the office user's refresh token with
`drive.file`. A read permission does not confer write authorization on the other
identity. Track both health states and capabilities separately. An expired writer
can disable uploads while the reader still keeps an existing portal available.
An explicit product disconnect disables both immediately in our application.
Evaluate write capabilities using the writer identity: capability fields fetched
as the read-only account describe that reader and cannot authorize a writer action.

Prefer an individual reader identity per office during white-glove onboarding,
using short-lived impersonation/managed identity rather than downloaded private
keys in production. This limits accidental cross-office visibility. The runtime
still needs carefully scoped permission to obtain those identities; a compromised
central runtime is not magically isolated by having many service accounts.
One shared reader can be supported as a documented temporary operational choice,
but must not weaken tenant/path checks. Store the reader identity per connection
so this choice does not change domain code.

Encrypt refresh tokens using a managed envelope key, record key version, and
keep tokens/resumable-session URLs out of logs and browser storage. As built
(P1, 15 Oct 2026): AES-GCM with a key derived from each environment's
`APP_SECRET` (Secret Manager), ciphertexts versioned so Cloud KMS can replace it
without re-connecting offices. For local
simulation use non-secret dummy credentials. Local live testing uses dedicated
credentials from ignored files, never committed samples.

Onboarding flow:

1. Create office, owner membership and provisional subdomain.
2. Owner connects the Google account; use incremental consent for file writing.
3. Create an application root or select an existing one through Picker. Confirm
   the root explicitly; do not assume OAuth folder selection authorizes every child.
4. Share that root with the assigned reader. White-glove onboarding can perform
   or guide this step; verify access with the reader rather than assuming it worked.
5. Record personal/Workspace/Shared Drive type, owner account and drive ID.
6. Verify listing, one sample read and an authorized sample write in the sandbox
   or a specifically approved onboarding test folder. Record results.
7. Establish initial sync with historical notifications suppressed.
8. Explain the deliverables boundary and visibility/password setting; preview
   the client page together before enabling notifications.

The file manager presents each item's actual available actions. App-created
files generally have the intended write path. For a Drive-uploaded file that the
writer cannot modify, say in plain words to make the change in the stage's folder
(A34) and, where validated later, offer “Authorize this file” using Picker. Do not advertise universal website rename/move/trash until
that combination is verified. Do not silently broaden OAuth scopes.

`drive.file` is a per-file, non-sensitive scope in Google's documentation; this
does not prove every organizational policy or the entire hybrid product is
exempt from review. Record the actual requested scopes and publishing
requirements. [Google scope documentation](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)

External OAuth apps left in Testing can have seven-day refresh-token expiration
for Drive access. Account/MFA setup, consent-screen publishing and any applicable
review are launch work. Do not mistake a friendly test-user list for a durable
connection strategy. [Google OAuth documentation](https://developers.google.com/identity/protocols/oauth2)

Pending live acceptance matrix:

| Scenario | Verify independently |
| --- | --- |
| Personal My Drive; Workspace My Drive; Shared Drive | Root sharing, ownership, policy restrictions and account health |
| App upload, Drive browser upload, desktop sync, another staff member | Reader discovery/download; writer create/rename/move/trash capabilities |
| Existing folder selected vs root created by app | Nested items and files moved in after connection |
| PDF/image/CAD, Google Docs/Slides, shortcut | MIME/export/preview behavior and content boundaries |
| Same file overwritten; new revision file | Revision markers, duplicate changes, revision retrieval |
| Token revoked, reader unshared, owner leaves | Honest degraded state, reconnect and disconnect |
| Large interrupted upload, quota exhausted, rate limiting | Retry/resume, no duplicate files, useful user errors |
| Shared Drive policies and pagination | `supportsAllDrives`, corpus/drive parameters, changes coverage |

The first personal-Drive pass unlocks an appropriately labeled pilot. Unsupported
account types can wait without redesigning tenant isolation or project metadata.

### Staging and production: same app, separate configuration

Staging runs the same code with no special logic for Drive: as in production,
whoever connects Drive in the painel chooses the account and folder (real
Alinea projects are fine for testing; projects created on staging create real
folders in whatever folder was chosen). Only configuration differs: each
environment has its own database, its own reader identity (`portal-staging@`
on staging) and **its own OAuth client**. That last one matters because
`drive.file` access is per (Google account, OAuth client): with a shared client,
staging's writer could see files production created for the same account. Emails
outside production go only to an allowlist of test addresses (section 14).

## 10. Project creation: atomic experience, recoverable external work

**Yes: project creation should be atomic in the database and appear complete to
the customer only when its required setup is complete.** The limitation is that
PostgreSQL and Google Drive do not share a transaction coordinator. A SQL rollback
cannot undo a folder that Google already created, and Google may succeed even
when our connection times out before receiving its response.

**Pilot, as built (step P2, 15 Oct 2026):** creation runs within the request.
It checks the form and the address first, creates the project folder in the
office's folder (so it inherits the reader's access, section 9) and one folder
per stage, then saves the project, its address and its stages in one database
transaction, which is not held open during the Drive calls. If any step fails, the project
folder is moved to the trash, which takes its stage folders with it, and nothing
is saved. The form sends a one-time creation key, so a double click or a retry
returns the project already created. What this gives up: if the server stops
between the folders and the save, or Drive also refuses the move to the trash,
an empty folder stays in the office's Drive (logged; no project is shown); the
durable operation below is the eventual design.

Do not hold a database transaction open during a sequence of network calls.
Eventually, implement a durable provisioning operation:

```text
submitted → provisioning → ready
                    ↘ retry_wait → provisioning
                    ↘ needs_attention → retry or cancel
```

1. Validate form, membership, connection, quota policy and idempotency key.
2. In **one DB transaction**, create the project as `provisioning`, its stages,
   operation record and an outbox/job record. Repeated submission with the same
   key and body returns the same operation. Same key with different body: conflict.
3. A worker claims the operation with a lease and creates the project folder,
   deliverables folder and stage folders, checkpointing every completed step.
   **Grant the reader on each folder as part of creating it**, before anything
   can be uploaded into it — see the ordering constraint in section 9. Reader
   access is not a step that can be deferred to reconciliation.
4. Tag app-created resources with opaque operation/step identifiers in Drive
   properties as recovery hints. Keep substantive project metadata in SQL.
   Use pre-generated provider IDs where supported and tested; otherwise look up
   the recorded operation marker through the creating OAuth application before
   retrying an ambiguous create response. Do not assume private app properties
   are visible through a different application identity.
5. Confirm bindings and reader access. In one DB transaction set `ready` and
   finalize the operation. Only ready projects appear in the client portal.
6. The panel shows progress or a specific recoverable error. Refreshing the page
   or clicking retry continues the same operation; it does not create a new one.

API shape: `POST /admin/projects` returns `202` and an operation URL;
`GET /admin/operations/{id}` reports progress and the ready project's URL.
Short operations may finish while the form shows progress, but a request timeout
does not erase the durable operation.

Recovery rules:

- If Google creation succeeded but saving its ID failed, reconcile before retry.
- A lease prevents normal duplicate workers; provider idempotency/reconciliation
  protects against crashes, expired leases and ambiguous responses as well.
- Partial folders may exist in Drive during provisioning. This is an explicit
  limitation of cross-system atomicity, hidden from the client portal but not
  falsely described as impossible to observe in Drive.
- Cancellation hides/cancels the pending project and queues careful cleanup.
  Only remove resources proven created by this operation and still safe to remove.
  If staff have added content or ownership is ambiguous, preserve and flag them.
- A final SQL transaction failing after Drive completed is retried; do not delete
  successful user-visible Drive work merely to simulate rollback.

Acceptance: kill the worker after every external side effect and before every
checkpoint; after retry there is one ready project and one intended folder tree.
A fault injected after database commit must not lose the creation job.

### What creation asks for, and what is edited later (A24)

Creating a project must take seconds. The form asks for the **project name** and
the **client's name** (both required, both editable later), the **project
type**, and its stages: all built-in stages listed in order, the type's usual
ones ticked, any of them ticked or unticked (A27). The client name (at most 30
characters for now, so it fits the page on a phone; the database allows 48, and a
name saved before the limit stays) is the main label in the painel. The office's
name follows the same rule at 28 characters (the database allows 80). The slug is derived from the name and editable; duplicates of an
existing name or slug in the office are refused with the conflicting project
named. Everything else starts empty or from office defaults and is edited later.

A new project is published at once (`active`, A35): its client page answers as
soon as it exists. Later `completed` (all stages done) and `archived` (still
viewable; no new uploads or emails, section 22). The `draft` status (staff only,
client page "not found") stays in the schema, unused for now.

Editable after creation, by office staff:

| Content | Editing |
| --- | --- |
| Description | Plain paragraphs and `- ` bullet lines, as today |
| Project type | One of the built-in types (A27), chosen at creation; changing it later leaves the stages as they are |
| Project details | Chosen from the built-in details (Cliente, Localização, Área do terreno, Área construída, Início, Previsão de entrega, Responsável), each with a fixed type (text, choice, area, date); reorder, hide empty ones. Areas and dates are formatted per language. Custom details are a later addition (A27) |
| Stages | Add, rename, reorder, remove (only when empty, or with explicit confirmation that its files stay in Drive); per-stage notes; built-in stages carry a translated description, the project type's own where it has one (A27); custom stages the office's own |
| Progress | "Advance stage" moves the current-stage pointer; "mark complete" finishes the project. Status (done/current/upcoming) derives from the pointer |
| Meeting | Start, end (after start), subject (≤ 40), location (≤ 60), link (`http`/`https` only, so a pasted `javascript:` link can never run in a client's browser); clearing it shows "no meeting scheduled". Clients can add it to their calendar: a Google Calendar link and an `.ics` file generated by the server in the office's timezone |
| Files | Upload into a stage, send a new version of a file (section 12) |
| Cover image | Upload (JPG, PNG or WebP, up to 10 MB), replace or remove, from the project page or directly from the painel project card; or "set as cover" from an image file in the project. Either way the photo is cropped in the browser to **3:2**, the one shape covers show in everywhere (Fabio, 18 Oct 2026), and goes up as a JPEG of at most 2400 px. Shown on the painel project card and at the top of the client page |
| Access | Public or password; change slug (old slug keeps redirecting) |

Where it is edited:

- **Project page edit mode.** A staff session sees a bar on the client page with
  "Painel" (back to the project list) and "Editar". Edit mode shows the page as
  the client sees it, with controls in place: edit details, stages, progress,
  meeting, notes, and upload per stage. This is the main place for day-to-day
  updates and for uploads. Name and slug are not edited here, to keep it safe.
- **Painel.** Project list with status at a glance (current stage of how many,
  project type, client, last client-visible activity), sortable by project type,
  client, project name, creation date or last activity, in either direction
  (sorted in the browser; office project counts are small). Project creation;
  the project's settings in the "Projeto" dialog (name, client, cover, client
  link, access, archive) and the cover from the card's photo button (A24);
  office settings and Drive connection. Office-wide
  problems, such as a lapsed Drive connection, show as an office notice, not on
  each project.

Without a cover, the painel shows a placeholder architecture photo instead of an
empty box, chosen deterministically per project from a small bundled set so it
stays the same between visits (revised 15 Oct 2026: no longer the client's name
over a blurred photo). **Clients only ever see a cover the architect uploaded:** the placeholder
is a painel-only device, and the client page shows no hero without a real cover.
The bundled photos must be licensed for this use and their sources recorded next
to them in the repository; the prototype's set is ten CC0 photos from StockSnap,
found through Openverse. Cover images follow the brand-asset limits in section 16.

The cover is stored in Drive, in the project's root folder as a hidden `_capa`
file (outside the client-visible stage folders). The app creates it through the
`drive.file` grant, so it can replace or remove it later; the reader identity
serves it like any other file. "Set as cover" from an image the office added
through Drive copies its bytes (read by the reader identity) into a new `_capa`
file, because the grant cannot move or rename the original.

The client page also offers, as requirements (layout still being designed): a
"latest updates" panel listing new files, notes and meeting changes from
`project_events` (A28), with read state kept in the client's browser since clients
have no accounts; a short explanation per stage; a search over file and stage
names; and the theme choice remembered per device.

Changing a stage title or order renames/moves its Drive folder only where the
write capability allows; otherwise the change is presentation-only and staff are
told the Drive folder name stays as it was. The client page never reads the Drive
folder name as the source of truth for a stage title once it is in the database.

## 11. Folders, publication and the staff file manager

Proposed default layout, customizable in future through versioned templates:

```text
Office application root/
  Project name/
    Entregas ao cliente/
      01 - Proposta/
      02 - Levantamento/
      ...
```

Private working files may live outside `Entregas ao cliente`. The application
must not expose them merely because the reader can see a parent folder. Existing
offices can bind an established deliverables folder rather than move everything
immediately. Bind by ID and validate ancestry; paths are presentation, not identity.
Shortcuts outside the approved boundary are excluded in the pilot. Cycles,
duplicate sibling names, hidden/config files and missing folders have explicit
handling. Never follow shortcuts recursively without tenant/root validation.

Files publish automatically after discovery, valid in-bound placement, successful
access verification and a stable content observation. For externally changing
files, require a short settling check (proposed 30–60 seconds after the last
observed content change) before notifications. This does not guarantee that a
staff member has finished all work; the folder itself is the publishing action.
UI copy must say that placing files there shares them with project viewers.

Website uploads to the deliverables folder follow the same publication service;
they do not send emails directly from an upload route. Files removed or moved out
are withdrawn on detection. Downloads also validate current access/boundary,
so a stale listing does not authorize arbitrary files. Withdrawal cannot erase
copies someone previously downloaded; avoid promising that it can.

Uploads (A24): the pilot's primary upload path is per stage, in the project
page's edit mode: drag-and-drop or a file picker, upload progress, and the
version prompt in section 12. A painel file manager is optional and only built
if staff need more than that: breadcrumbs, folders, filename/type/size/updated
columns, preview, upload progress, create folder, and capability-dependent
rename/move/trash.
No “Open in Google Drive” link on the project page (A34): changes are offered on the site. No attempt at copying every Drive
feature or matching its branding. Do not offer hard delete. Cross-project moves
are explicit operations with publication consequences, not casual drag/drop in
v1. Within-project moves preserve the logical document unless staff split it.

Build on existing components where they fit rather than from scratch. Candidates
to evaluate in the staff app: SVAR React File Manager (MIT) for the browser view,
Uppy (MIT) for drag-and-drop uploads with progress, and the Google Picker for
adding existing Drive files, which also grants `drive.file` access to the files
the user picks. Uppy's own Google Drive plugins need its Companion server; use
the Picker directly instead. Check maintenance status and licence of each before
adopting it. The prototype's `drive` branch explores the same screen in Jinja.

UI may show cached data with its last-sync time in administration. A public
project should show unavailable content honestly; a missing preview does not
prevent an otherwise authorized original download.

## 12. Document versions and previews

Treat these as three different concepts:

1. **Logical document:** “Planta baixa”, with a stable application ID.
2. **Published revision:** a labeled delivery associated with that document.
3. **Provider content observation:** an observed state of a Drive file, which may
   change without creating another physical file.

A filename such as `Planta_final_v2_final.pdf` is not a reliable identity scheme.
For website uploads, offer “New document” or “New revision of…”; the latter
explicitly binds to the selected document.

Version naming and upload flow (A25):

- The office convention is `v1, v2, v3`: `Planta v2.pdf`. Staff never have to
  type a version number. Each file offers "Enviar nova versão", which uploads
  the chosen file as the next version of that document.
- Uploading a file whose name matches an existing document in that stage asks:
  "É uma nova versão de Planta.pdf?" Yes stores it as the next `vN` and makes it
  current; No keeps both as separate documents (the new one gets a distinct name).
- The client page shows the document's clean name with a separate version badge
  ("Planta.pdf", v3). The copy saved in Drive carries the version in its name
  (`Planta v3.pdf`), so staff working directly in Drive can tell versions apart
  and synced computers do not produce "Planta (1).pdf". **Existing files are
  never renamed**: the `drive.file` grant cannot rename files the office added
  through Drive. An unnumbered original counts and displays as v1.
- Website uploads take the next version number under a lock, so two uploads
  cannot both become v3.
- Files added directly through Drive group automatically when their name carries
  a clear version token (`v2`, `_v02`, and the legacy `rev B` style) or exactly
  matches an existing document's name; ambiguous names stay separate and can be
  grouped by staff.
- Grouping rules (A25): only within the same folder; two files claiming the same
  version (two "v2") are never merged, they are flagged for staff; the current
  version is the highest number, not the latest upload; staff corrections are
  stored and always win over automatic grouping on later syncs.
- Older versions stay downloadable under "Versões anteriores" on the client page. Store a monotonic sequence, optional
human label, date and source. “Current” is a database pointer, not whichever
filename sorts last: by default the highest version, and staff can select another
available revision, with an audit entry.

For external Drive uploads:

- A new file ID creates a new document unless an explicit existing association
  applies or its name carries a clear version token of an existing document in
  the same stage (A25). Other filename similarity can only suggest grouping to
  staff; ambiguous matches never merge documents silently.
- An update to an existing file ID creates a new content observation. Use binary
  checksums and provider revision metadata where available, not just modified
  time. Metadata-only rename/move should not create a content-update email.
- Where Google-native content markers cannot distinguish content from metadata
  precisely, normalize known metadata changes and record the limitation. Validate
  with real Docs/Slides before promising exact content-change notifications.
- Staff can group separate files as revisions or split an incorrect group. That
  changes presentation; it does not rename, delete or rewrite Drive files.

**History metadata is not a backup of historical bytes.** Website revision
uploads should default to a new physical Drive file, preserving earlier files in
the office's Drive. If staff overwrite the same file through Drive, older content
may only be available under Google's revision rules. Preserve metadata but mark
an unavailable historical revision as unavailable; never serve today's bytes
under yesterday's revision label. Pinning provider revisions may require write
capability and has limits. Full immutable archival guarantees are a separate
feature. [Google revision behavior](https://developers.google.com/workspace/drive/api/guides/manage-revisions)

For previews, prioritize predictable originals: image thumbnails, PDF first-page
previews and browser PDF viewing, then Google-native exports where supported.
Use an adapter interface so future renderers for CAD/BIM or image galleries do
not alter project/auth code. A missing/failed preview falls back to a file-type
card with download (no “Open in Drive”, A34). Do not invent an image for a real document.

Preview keys include tenant, document/revision, renderer version and size. Async
rendering has memory, file-size, page-count and time limits. Treat filenames and
file contents as untrusted; do not render arbitrary HTML/SVG/scripts in the
portal origin. Keep credentials and provider thumbnail URLs server-side. If
persistent generated previews are introduced, use a private, size-bounded cache
with tenant-aware access and deletion; it is a derivative cache, not custody of
all original files. The initial pilot can use upstream thumbnails and ephemeral
rendering to avoid requiring that extra storage service immediately.

## 13. Sync and durable jobs

**Pilot (A10, 16 Oct 2026): a scan, not the changes feed.** Each maintenance
pass lists every published project's stage folders, as the client page does
(hidden names, folders still in their project), and compares them with the files
the project has shown before; a file shown for the first time is recorded as
"file published" (A28). A project's first scan only records what is there, so
existing files never email. It costs about one Drive call per stage folder per
project per pass, cannot miss a change, and needs no cursor or repair pass. The
changes feed below replaces it when versions (A25) need a file followed across
renames, or when the number of projects makes scanning costly; the events and
emails built on the scan stay as they are.

Use the read identity's changes feed when coverage is validated. Scope a cursor
to connection generation, identity and Drive corpus; Shared Drives have explicit
configuration. Initial indexing takes a start token, scans the selected tree,
then replays changes from that token to close the scan race. Suppress historical
notification events during this baseline. A reconnect establishes a new baseline
without notifying clients about every old file again.

The fuller design polls active connections approximately every two minutes.
Option E instead runs one maintenance pass every 10 minutes for the POC (A09):
each pass sends due email batches and polls Drive changes for active connections
(incremental, so cheap). The interval delays only notices (emails, "Atualizado",
the updates feed), never what a page shows: pages read Drive live (A10).
UI-triggered sync can request earlier bounded work with a rate limit. Coalesce
repeated poll requests. A scheduled daily
reconciliation compares the complete in-scope tree with indexed state and repairs
missed moves/deletes or cursor errors. For larger trees, paginate and checkpoint
scans; mark missing files only after a complete successful reconciliation.

Apply each page and persist its next cursor in the same DB transaction. A crash
before commit replays safely; a crash after commit continues from the saved token.
Deduplicate by provider identity/content marker and normalized event kind. Drive
change records reflect resource changes, not a perfect immutable business audit.
Our own publication/audit events provide the product history.
[Google changes guide](https://developers.google.com/workspace/drive/api/guides/manage-changes)

Later, push notifications can wake the same sync job. They are hints to fetch
changes, not the complete file payload. Watch registrations expire and require
renewal; duplicated or missing callbacks must not break correctness. Verify
channel/resource identifiers and secret tokens, then enqueue work and return
quickly. Periodic polling/reconciliation remains the repair path.
[Google push notifications](https://developers.google.com/workspace/drive/api/guides/push)

Job mechanics (PostgreSQL queue option A; adapt transport ownership for option B
as described in section 4, retaining the business-level guarantees):

- Claim eligible jobs with row locks and `SKIP LOCKED`, setting lease owner,
  expiry and a fencing token. Commit before work starts.
- Heartbeat/checkpoint long work. Completion checks the current lease token.
- Retry transient errors with bounded exponential backoff and jitter; honor
  provider retry hints. Treat permission/reconnect errors as actionable states.
- Store attempt count, next run time and a safe error class; no tokens/documents
  in error logs. Exhausted jobs enter an attention queue.
- Enforce dedupe keys and resource constraints in SQL. At-least-once execution
  is expected; side effects must be idempotent or reconciled.
- Queue only committed business events via the transactional outbox. An outbox
  dispatcher can be retried without creating a second logical event.
- Fair scheduling and per-office concurrency limits prevent one large office
  from delaying everyone else's notifications.
- A disconnect increments the connection generation, cancels work and makes
  workers reject stale queued jobs before making provider calls.

## 14. Notifications and recipient privacy

Email is the first delivery channel. Use a verified product sender domain, with
an office-specific display name and a validated reply-to address. Do not attempt
to impersonate an office's domain before it has configured email authentication. An
office whose own domain is verified sends from it (A32: Alinea, from
`alineaarquitetos.com`); the reply-to is the office's contact email.
Resend is the proposed adapter; keep provider-specific behavior out of batching
logic. Configure SPF/DKIM/DMARC, suppression and bounce handling before sending
to customers. Provider quotas count recipients, so a digest to ten people is not
necessarily one billable message. [Resend limits and plans](https://resend.com/pricing)

Default batching: a **trailing "settle" window**. A publication starts a pending
batch; the batch becomes due once **nothing new has been published for 45
minutes**, subject to a **maximum hold of 2 hours** from the first publication in
the batch (when the file became visible on the page, which can be later than the
upload if Drive reports it late). A due batch is *sent* by the next maintenance
run, which runs every 10 minutes (Cloud Scheduler charges per job, not per run,
so this stays free). Example: uploads at 10:00, 10:20 and 10:50 make the batch
due at 11:35; it is sent by the run at or after 11:35, at the latest about 11:45,
as one email; an upload at 11:40 starts a new batch. An office that uploads continuously all
afternoon still gets mail, because the maximum hold closes the batch regardless.

Offer an office setting with a bounded range, initially 5–120 minutes for the
quiet period, and a maximum hold bounded separately. A send-now action can close
a pending batch; it does not create duplicate deliveries.

Why trailing rather than a fixed window from the first event: a drawing set is
uploaded over tens of minutes, and a fixed window splits one delivery session
across two emails whenever the upload straddles the boundary. The architect made
one delivery and the client should get one mail. The cost is unbounded latency
without the hold cap, which is why the cap is not optional.

The window also prevents an **email about a mistake**: an upload into the wrong
project, noticed and removed within the quiet period, produces no email. It is
**not** an undo window for the file itself: files publish as soon as they are
found, so a client already viewing the page can see or download it in the
meantime. Do not describe it to offices as one. It still argues for erring
longer rather than shorter, and against letting an office configure the quiet
period down to 5 minutes without warning them what they are giving up.

45 minutes and 2 hours are both guesses. Ask a pilot office how long a typical
upload session runs before treating them as settled. Initial recipients share a
project batch, but delivery and subscription state are individual.

Pipeline:

1. Publication and outbox event commit together.
2. Batch worker deduplicates and attaches eligible events under a project lock.
3. When due, freeze the batch and create one delivery per active recipient.
4. Immediately before sending, recheck project/tenant status, subscription and
   file visibility. Remove withdrawn items; drop an empty digest.
5. Send using a stable provider idempotency key per logical delivery. Record
   provider ID and outcome. Unknown timeout outcomes are reconciled where the
   provider permits; do not promise mathematical exactly-once email delivery.
6. Signed provider callbacks update delivery/bounce state idempotently.

Email contains a short summary and portal links, not attachments or passwords.
Send recipients separately to avoid exposing the client list. Offer an
unguessable unsubscribe link scoped to that recipient/project and an office
preference control. Disabled recipients remain suppressed on retries. Initial
imports, rename-only changes, previews, metadata edits and moves within the same
published project do not create “new file” mail. What does email (A32): new files, a stage
advanced or the project completed, and a meeting scheduled, changed or removed.
A stage's note does not; it is recorded for the updates panel only. A genuinely new visible revision
does. Repeated edits in a batch are summarized once per document with the latest
still-visible state.

Local tests use a collecting fake email provider and virtual clock; no waiting
an hour and no SMTP credentials. Staging uses an allowlisted recipient sink even
when realistic data is used. SMS and WhatsApp can consume the same publication
batches later, with separate consent, templates, provider costs and preferences.

## 15. Downloads, uploads and costs

The existing app already streams downloads: it forwards chunks instead of
loading the entire file into memory. Keep that principle. It reduces memory and
time-to-first-byte; **it does not remove outbound bytes from our hosting**.
Cloud Run documents outbound network transfer separately from compute.
[Cloud Run pricing](https://cloud.google.com/run/pricing)

Pilot default: authenticated server-to-Drive stream after tenant/project/file
checks, for both public and password projects. This supports clients without
Google accounts while leaving original ownership with the office. Forward
supported byte ranges and relevant validators for binary files, close upstream
connections on client disconnect, bound timeouts and never buffer an entire
large file. Handle export-specific limits separately. Do not hold a database
connection open for the stream.

A `webContentLink` redirect can avoid our transfer path when the viewing user
already has Drive download access. It is not a transferable service-account
credential. Never put an OAuth token in a URL or browser response. Making a Drive
file public solely to enable redirects would change its sharing policy and could
bypass a portal password; that needs an explicit separate product choice.
[Google download methods](https://developers.google.com/workspace/drive/api/guides/manage-downloads)

Uploads use resumable sessions so a network interruption need not restart a
large file. Prefer bounded chunks through the backend initially. Do not let the app
parse a whole multi-GB multipart request into memory or temporary disk. If a
direct browser-to-Google session path is validated, it can reduce our transfer
work; the session URL is a capability and must be scoped, protected and verified
at completion. Never expose the office's broad access/refresh token to the
browser. Constrain destination and MIME/size policy and reconcile the finished
provider file before publication. [Google upload guide](https://developers.google.com/workspace/drive/api/guides/manage-uploads)

Transfer is not inherently cheaper than storage. Storage is charged per unit
**per month**; transfer is charged for bytes delivered, potentially many times.
For illustration only, using hypothetical rates of $0.02/GiB-month storage and
$0.12/GiB outbound transfer: keeping 100 GiB costs $2/month in storage, while
serving those 100 GiB three times costs $36 in transfer. These are arithmetic
assumptions, not a Google quote. Real rates depend on provider, region,
destination, allowances and other services. Compare current
[storage pricing](https://cloud.google.com/storage/pricing) and
[network pricing](https://cloud.google.com/vpc/network-pricing) for the selected setup.

Drive remains a sensible choice because ownership, workflow and avoided original
storage all matter. Moving originals into our own storage would not inherently
remove download costs either. Downloads stay on the site (A34, no “Open in Drive”);
measure actual usage, then decide whether a separate delivery/storage tier is
worth introducing.

Track monthly per-office original-download bytes, preview bytes, upload handling,
request count, active projects and support time. Budget includes web/worker,
PostgreSQL/backups, domain/TLS/load balancing, email, secrets/keys, logs and
network. Do not price the product from storage alone or advertise unlimited
bandwidth while learning these workloads. Public links need abuse monitoring
and rate controls without forcing legitimate clients to create accounts.

## 16. Branding, accessibility and language

Office details (P1b, 15 Oct 2026): name, contact email and logo live in a
per-office `office_profiles` table (not the shared `tenants` registry, which the
app only reads); the logo is stored in the office's Drive (`_marca`) and served
so nothing in it can run. Built (18 Oct 2026): a chosen logo opens a crop dialog
with its empty margins already trimmed, any shape, and "Remover fundo" when it has
a plain background; it goes up as a PNG. The pages size a logo by area, not height
(a 4:1 wordmark at the bar's usual height, squarer ones taller up to a cap, so the
bar never grows). An optional dark mode logo ("Usar o mesmo logo no modo escuro"
until one is chosen) shows when the page is dark. Pilot branding: office name, light/dark logo, accent color, bounded neutral palette,
contact details and one versioned portal template. Keep the current Alínea design
as one office configuration. Provide a preview and publish action for theme edits.
Validate colors and contrast; do not accept arbitrary script, CSS or markup.
Brand assets need size/type limits and safe rendering. Tiny uploaded brand assets
can live in a designated office Drive folder and be indexed like other approved
assets; avoid coupling them to publicly listed deliverable folders.

Use CSS variables/design tokens and component boundaries so another layout is
possible later without replacing backend services. Template version is explicit
per tenant. Theme choice must not change authorization, semantic document IDs or
file URLs. Support mobile, keyboard navigation, meaningful empty/loading/error
states, readable filenames and accessible focus/contrast from the first pilot.

Brazilian Portuguese is the default. Preserve English capability through explicit
locale arguments; never change global environment variables per request. Each
office has a language (`tenants.locale`, an enum of the languages the product is
translated into: `pt-BR`, `en`). **Supporting a language (A26)** means translating
the product's own text (buttons, headings, messages, error codes) and its built-in
options (project types, standard details, built-in stages and their
explanations; their texts are stored per language in the reference tables, see
section 7). What an office writes itself is shown exactly as typed and never
translated: an office writes in its own language. One translation catalog per
language is shared by the server (client pages, emails, calendar files) and the
staff app; no visible text is written directly into screens. Tests fail if any
interface text or built-in row lacks a translation in a supported language, and
the database refuses a built-in row without every language. Dates and
numbers format per language (17/10/2026 and 1.240 m² in Portuguese). Before
launch, audit a fully English test office for leftover Portuguese. Timezone
is per office. Long Portuguese labels, accents, duplicate filenames and non-Latin
names belong in fixtures. Template content and default stage descriptions are
versioned: updating defaults does not overwrite an office's edited project stages.

## 17. API and error conventions

Client-facing routes serve the client page's shell, with its preview tags and
status (A20); the page reads a public JSON API (`/api/pages/...`) that returns
only what that page may show, behind its password.
Staff administration is the React staff app (A20), which uses JSON endpoints under
`/api/` for everything: project editing, file browsing, uploads, operation
progress and settings. Administrative endpoints require a staff session and a
CSRF token on every state-changing request, even when a project is public.
Staff-app routes under `/painel` only return the app shell; they never carry data
or authorization decisions of their own.

Representative contract:

| Endpoint | Behavior |
| --- | --- |
| `GET /{slug}` | Resolve tenant from host and project from slug (or alias → redirect); render or password challenge. Staff sessions also get the edit bar (A24) |
| `POST /{slug}/unlock` | Verify project password; issue project-scoped grant |
| `GET /{slug}/documents/{id}/revisions/{revision}/download` | Check membership in project, access, availability and stream |
| `GET /{slug}/documents/{id}/preview` | Same boundary checks; safe thumbnail/fallback |
| `POST /api/admin/projects` | Validate + create durable provisioning operation |
| `PATCH /api/admin/projects/{id}` | Tenant-bound edit with row-version conflict detection: description, details, meeting, access, name/slug (painel only) |
| `PUT /api/admin/projects/{id}/stages` | Add, rename, reorder, remove stages in one versioned change |
| `POST /api/admin/projects/{id}/progress` | Advance the current stage or mark the project complete |
| `GET /api/admin/projects/{id}/folders/{id}` | Indexed listing and current capabilities |
| `POST /api/admin/projects/{id}/uploads` | Create scoped resumable upload operation |
| `POST /api/admin/projects/{id}/sync` | Deduplicated, rate-limited sync request |
| `POST /api/admin/documents/{id}/revisions` | Explicit version association / upload ("Enviar nova versão", A25) |
| `POST /api/admin/projects/{id}/stages/{stage}/uploads/check` | Before an upload: report name matches so the UI can ask "nova versão de…?" |
| `PUT /api/admin/projects/{id}/cover` | Upload or replace the cover (JPG, PNG, WebP, ≤ 10 MB; specific error codes); stored in Drive as `_capa` |
| `GET /{slug}/updates` | Client-visible events (A28) for the "latest updates" panel; same access checks as the page |
| `GET /{slug}/reuniao.ics` | The meeting as a calendar file in the office's timezone; same access checks |
| `POST /api/admin/connections/{id}/disconnect` | Disable both application access paths; cancel stale work |
| `GET /api/admin/operations/{id}` | Progress or actionable failure |
| `POST /integrations/drive/events` | Validate registered channel; enqueue sync only |
| `POST /integrations/email/events` | Validate signature; deduplicate delivery update |

Never accept a caller-supplied tenant as authority. Resolve it from the host/session
and verify every resource. Use consistent error codes: validation, conflict,
connection needs attention, quota exceeded, provider unavailable, file unavailable.
Show clear messages in the office's language and a support/request ID. The API
returns only the error code (`{"error": "<code>"}`, every code listed in the
OpenAPI schema) and the request ID in `X-Request-ID`; the staff app translates the
code and never builds its own text from provider details. Redact provider details
that contain credentials or private filenames from shared logs.

## 18. Local testing now and in the new architecture

### Current repository: runnable without Google

The current suite has 80 Python tests and eight browser test files. The initial
review found the local environment missing declared PyMuPDF and undeclared
Playwright/browser setup. This work adds pinned Playwright tooling, a lockfile,
and a combined isolated runner:

```bash
.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt
npm ci
npm run browsers:install
.venv/bin/python -m tools.test_local
```

The runner ignores `.env`, uses fictional in-memory data and temporary folders,
and starts/stops its browser-test servers on available ports. Python integration
fixtures also select available ports. It preserves manually running servers and
`local-test-data/`. Browser tests include a realistic in-progress standard project
and custom office logo. Subsets: `--python-only` and `--browser-only`.

Manual UI testing still follows `run_local.py test --reuse-data` or authorized
`--regenerate-data`. Existing data is backed up before regeneration. This manual
workflow and its Portuguese/English intent instructions remain in `AGENTS.md`.
Automated tests never prompt for regeneration or alter a developer's dataset.

The suite is for the **current** app. It does not yet test a multi-tenant database,
Google user OAuth writes, job queue or real email delivery because those features
have not been implemented. Browser tests deliberately block external webfonts
and test fallback layout. Live-font rendering is a separate visual check.

### Target: all application behavior locally, real provider proof separately

Use PostgreSQL of the selected production major version in a local container
(or a dedicated local installation), migrations, fake Google/OIDC endpoints,
collecting email adapter, virtual clock and deterministic worker drain command.
The first backend slice adds a single local orchestration command. Do not claim
that proposed command exists until implemented. Local environments have unique
DB names/volumes; a test safety check refuses a production URL or a nonlocal DB
unless an explicitly designated disposable-test configuration is provided.

Staff app (A20): component tests with Vitest, type checks against the generated
OpenAPI client, and Playwright tests against the **built** bundle served by
FastAPI, not only Vite's dev server. The local orchestration command starts both.

Run the actual FastAPI services, SQL repositories and worker code against those
local components. Mock at provider boundaries, not every internal service call.
The fake should implement both read and write identities and deliberately deny
external-file writes when the selected capability scenario requires it. Include
pagination, duplicate/out-of-order events, quotas, token refresh errors, timeouts
before/after provider side effects, moved-out files and missing revision bytes.

A local fake proves our behavior under a stated Google contract. It cannot prove
that Google's servers grant a scope, emit a particular change, permit a download,
or enforce an organization's sharing policy. Keep those live tests clearly
separate and opt-in, with dedicated sandbox accounts and folders. Fabio's current
account/MFA delay blocks those tests, not the local design/implementation stream.

Required acceptance matrix for the new backend:

| Area | Local scenarios and assertions |
| --- | --- |
| Tenant boundary | Two offices, same project/file names; wrong host/IDs/cookies, API, download, thumbnail, export, search, worker and cache all deny cross-office access |
| PostgreSQL | Runtime-role RLS, composite FKs, missing context, connection reuse, migrations from empty and prior schema, constraints and concurrent updates |
| Public/password | Public works anonymously; password applies to every content path; rotation/revocation, CSRF and rate limits |
| Staff login | Fake OIDC state/nonce/PKCE, invitation match, replay, wrong tenant, revoked member, multiple offices |
| Provisioning | Failure after each side effect/checkpoint; retry, double submit, cancellation with user-added files, lease expiry |
| Drive capabilities | Reader sees external upload but writer denied; shared-drive flags; reconnect; both paths disabled on disconnect |
| Sync | Baseline race, pagination, cursor replay, partial scan, move/rename/delete, shortcut escape, daily repair |
| Versions | Explicit upload revision, external grouping suggestion, duplicate names, old bytes unavailable, current pointer and concurrent edits |
| Preview/download | Range requests, large streams, client disconnect, unsafe MIME, upstream timeout, unavailable preview and authorized fallback |
| Notifications | Virtual-hour batching, dedupe, withdrawn file, unsubscribe before retry, ambiguous provider response, bounce, import suppression |
| UI | Two different brands/locales, mobile 320px+, keyboard, upload progress/errors, reconnect banner, public/password forms; staff app deep links and reload on any `/painel` path, stale-bundle behavior after a deploy |
| Recovery | DB restore to isolated environment, job replay, kill worker, retry without duplicate published project/mail |
| Operations | Spending/usage metrics, failure redaction, no real credentials/recipients in test mode |

Keep generator scripts as the source of fictional defaults. Add two visibly
different offices and edge-case projects as the architecture is introduced.
Update generator, exporter, regeneration version inputs, folder adapter and tests
when required. Do not copy real customer documents into fixtures or recorded HTTP
responses. Contract fixtures derived from real sandbox tests must be sanitized.

## 19. Build, review and release process

Recommended flow:

```text
feature branch → reviewed pull request → protected main
             → immutable build → isolated staging verification
             → Fabio approval → promote same build to production
```

Use `codex/` branches for implementation. Require PR approval from Fabio for
changes authored by his friend or an AI agent, and required status checks before
merge. Add CODEOWNERS for tenancy, identity, migrations, storage and deployment.
Verify that the repository's GitHub plan actually supports the required private
repository/environment approval features. A label saying “protected” is not a
substitute for configured protections and permissions.

Permanent beta/release branches are optional, not necessary for beta and live
websites. Prefer a production tag or release record pointing to the approved
artifact. If a separate release branch is useful organizationally, it should
point to the already-tested commit; avoid merging new changes during promotion.
Staging fixes return through main. Never build a different artifact for release
and assume staging's test result applies to it.

CI for every PR: dependency install from reviewed lockfiles, Python tests,
Chromium tests, target PostgreSQL integration tests, migration checks and a
production-image build/start smoke test. Pin Python to the production 3.13 line
and use a supported Node LTS for test tooling. Introduce a Python dependency lock
as the new backend is scaffolded; the current broad requirements are not yet a
fully reproducible production dependency set. Node builds the staff app (A20)
and runs browser tests; it is never part of the production image. CI also runs
the staff app's lockfile install, type check, unit tests and production build,
and fails when the generated API client is out of date. Build/start checks must
exercise the new Uvicorn entry point, the served staff app bundle and streaming
behavior rather than reuse a passing legacy Gunicorn check as evidence for the
FastAPI deployment. The new service's `Dockerfile` must not change how the legacy
site deploys before cutover (section 4).

Staging is a distinct service, database, Google connection and email sink.
It must not share production refresh tokens, Drive roots or job queues.
Use explicit environment identifiers in configuration and visible staff banners.
Database migrations run once in a release step, never opportunistically in every
web process. Use additive expand/migrate/contract changes and keep the previous
application version compatible during the rollback window. Destructive migration
steps require separate review and a verified recovery plan.

Tests, approvals and staging verification can be automated. Deploying, merging
and pushing still require the user's explicit authorization under `AGENTS.md`.
No direct ad-hoc Google Cloud deployment from a development session.

## 20. Migration of the existing office

1. Inventory legacy folders, `_project` metadata, stage notes, meeting fields,
   public URLs, file IDs and current visibility. Produce a read-only dry-run report.
2. Resolve duplicate slugs, missing configuration, broken shortcuts and incomplete
   stage definitions with the office. Do not guess away meaningful data.
3. Create the tenant, map `alineaarquitetos.com` to it (A23) and bind its existing
   Drive folders. Import metadata; current `/{slug}` links keep their slugs (A22),
   so they work unchanged. Keep original files in place for the first migration.
4. Import filename-based grouping as proposed document associations; review
   ambiguities. Preserve old labels but do not fabricate historical file contents.
5. Run initial indexing with all historical notifications suppressed. Compare
   project/file counts and a sample of actual authorized downloads/previews.
6. Run new backend as a shadow/staging view, with its own DB and no customer email.
   For real data, obtain an explicitly approved read-only test connection.
7. Agree a short metadata-edit freeze; import final changes and check parity.
   Do not dual-write `_project` files and SQL indefinitely.
8. Switch the office only after owner review. Preserve/redirect old URLs, keep a
   snapshot of imported metadata and retain the old deployment temporarily.
9. Observe sync/download/auth/notification health; enable real notifications only
   after baseline is established and recipients confirmed.

Rollback has two cases. Before any new-backend writes, reverting traffic to the
old deployment is relatively simple. After SQL-only metadata or new revision
associations have changed, the old app is no longer a lossless representation.
Freeze mutations, export/reconcile those changes or roll back to a compatible
new-backend build; do not blindly point customers to stale metadata. Raw Drive
files remaining intact does not mean the whole product is safely rolled back.

## 21. Operations, privacy and recovery

Expose office-facing read/write connection health, last successful sync, pending
creation operations, notification failures, and storage/quota information when
Google supplies it. Missing quota data means “unavailable”, not zero or unlimited.
A 403 may be permissions, policy or quota; show a useful action without claiming
every failure is an expired login. Office owners can reconnect, pause notifications
or request support. Platform operators can inspect redacted operational state.

Track request/operation IDs, tenant IDs, job age/retries, sync lag, downloads,
email acceptance/bounce, errors and bandwidth. Do not log file bytes, passwords,
OAuth/session tokens, entire provider responses or unnecessary client names.
Audit sensitive actions and explicit support access. Start with short documented
log retention and review it before paid onboarding.

Managed DB backups and point-in-time recovery must be enabled on a suitable plan.
Initial proposed objectives: recover at most 24 hours of metadata loss for the
friendly pilot and restore within one working day; tighten to at most one hour
of metadata loss and four hours recovery before paid rollout if the chosen
provider/configuration and staffing can support it. These are internal targets,
not customer SLA promises. Prove restoration into an isolated environment before
first customer migration. Encrypt backups and include project/access/version data,
not just the rebuildable file index.

Drive is the office's file store, not an application-controlled backup guarantee.
Document what an office should retain and what happens if it deletes files,
loses its Google account or removes sharing. Export project metadata and folder
bindings in a usable format so an office can leave without losing product-owned
information. Avoid claims that we “never process customer files”: streaming and
previewing still process their content.

Disconnect immediately blocks our application access and cancels queued work;
revoking OAuth and removing the reader's sharing grant are distinct cleanup
steps. Offboarding must not delete office-owned originals by default. Define
retention and removal of metadata, previews, logs, tokens and backup copies;
explain delayed backup expiry. Have a human-reviewed privacy/data-processing
agreement suitable for the actual customers and jurisdictions, including Brazil.

Unio's public homepage is at `/`, with the product logo, a description of the
project portal and an explanation of its Google Drive access. It is served as
static HTML and CSS without sign-in, JavaScript, tracking or a tenant lookup
(`backend/web/home.py`). Its two named assets also bypass tenant resolution;
staff and project routes still require it. The page links to the existing legal
pages and contact address. Before submitting Google's OAuth verification,
publish it on `https://myunio.app/`, verify domain ownership, and set that exact
homepage and `https://myunio.app/privacidade` on the consent screen. The public
page alone does not configure OAuth, publish a deployment or guarantee approval.

Unio's privacy policy and terms of use are at `/privacidade` and `/termos` on every
address, `myunio.app` included (`backend/web/legal.py`; Google's OAuth consent
screen links them). Each office is the controller of what it publishes about its
clients and Unio processes it on the office's behalf; Unio is the controller of
staff accounts, logs and the Google grant. Unio is run informally for now (no
company); the texts still need the human review above before more offices join.

Operational runbooks should cover: revoked writer, unshared reader, missing root,
quota full, sync lag, stuck provisioning, duplicate-send investigation, provider
outage, compromised token, restore, tenant suspension and migration rollback.
Include a system-wide and per-tenant pause for notifications/writes while preserving
safe reading where possible. Make those operational controls audited and explicit.

## 22. Pricing and pilot feedback

Start with a small number of understandable project-count tiers. Define an active
project as one that accepts new work and updates; archived projects remain
viewable under their existing access policy but cannot upload/send updates until
reactivated. Confirm this definition with pilot offices before tying it to billing.
Archive is not deletion, and it should not surprise clients with broken links.

Store plan entitlements centrally and enforce them in services, not scattered
UI conditions. Keep manual plan assignment and invoicing for the pilot. Track
responsible professionals from the start if useful, but defer charging separately
for that dimension until demand makes it worthwhile. Do not build billing,
seat management and a complex permission product merely to support hypothetical
tiers. Bandwidth/support may influence margins even if project count remains the
customer-facing price axis.

Measure time to onboard, reconnect incidents, weekly active staff, client visits,
repeat project use, uploads from website versus Drive, support minutes, download
volume and willingness to pay. Friendly free users are useful for usability and
reliability; they do not alone validate pricing. The 10–20 paid early users provide
that next experiment. Ask what caused confusion, what work the portal replaced,
and whether the office would be disappointed to lose it.

## 23. Implementation slices and rollout gates

Use small end-to-end slices with reviewable PRs. The step-by-step breakdown of
these slices, with each step's engineering decisions, is
[`rewrite-steps.md`](rewrite-steps.md); product decisions stay in section 2. Effort ranges below are planning
hypotheses for AI-assisted work, not a promise about calendar availability.
Several steps can happen in one focused session; permission setup, observation
and external failures do not shrink simply because code generation is fast.

| Slice | Concrete deliverable | Exit evidence | Rough focused effort |
| --- | --- | --- | --- |
| 0. Baseline | This decision doc and repeatable current local tests | Python/browser suite runs without Google; open issues recorded | Current work |
| 1. New foundation | New FastAPI factory and Uvicorn entry point, local PostgreSQL, migrations, tenant routing, fake identity, two offices; staff app skeleton (Vite + React + TypeScript) served at `/painel` from the two-stage image | Wrong-host/ID tests; runtime-role isolation; production image boots locally and serves the staff app shell | 1–2 days |
| 2. First useful vertical slice | Public/password project page at `/{slug}`, DB metadata, reused UI, read adapter and legacy import; staff bar on the page | Two branded offices; password protects every content endpoint; migration dry run; `alineaarquitetos.com` resolves to its office | 2–3 days |
| 3. Project creation + editing | Minimal creation (pilot: within the request, A07); painel project list/settings and page edit mode for details, stages, progress, meeting (A24) | Crash/retry matrix; no duplicate creation; edits visible on the client page; row-version conflicts handled | 2–3 days |
| 3b. Uploads + versions | Per-stage upload on the project page, resumable upload, version prompt and "send new version" (A25), capability-aware listing | Same-name upload becomes next `vN`; originals untouched; progress and failure UI | 1–2 days |
| 4. Sync + revisions | Incremental index, repair, explicit versioning, preview fallback | External upload/overwrite/move scenarios; old-content honesty | 2–3 days |
| 5. Notifications + operations | Outbox, batching, recipients, email sink, health panel, restore runbook | Virtual-clock/retry tests; restore exercise; no historical spam | 1–2 days |
| 6. Live Google + staging | Real OIDC/OAuth, read/write matrix, sandbox files, build promotion | Documented pass per supported account type; correct degraded modes | 1–3 days plus account wait |
| 7. First office then five | Migration, monitored first office, sequential friendly onboarding | Owner approval, stable behavior, feedback addressed before broadening | Observation-dependent |

These total roughly 9–16 focused engineering days after the baseline if most
assumptions hold. They can compress with effective AI and overlap where safe;
re-estimate after slices 1–2 using actual progress. At variable part-time capacity,
calendar duration may differ substantially. Prefer an earlier read-first pilot
if the useful client experience is ready before website editing of external
Drive files. That is a conscious scope choice, not hiding unfinished management.

Design input: a clickable prototype of the painel and the page edit mode
(14 Oct 2026, carte-blanche design pass) is the reference for slices 2–3b;
record its decisions here once reviewed.

Immediate implementation order while Google access is blocked:

1. Review this decision register and choose any changes to product defaults.
2. Scaffold new backend and real local PostgreSQL; establish two-tenant tests.
3. Port a single client project page using DB metadata and the fake storage adapter.
4. Add optional-password access across every resource path.
5. Implement project provisioning with fault injection, then explicit revisions.
6. Add sync/publication and the virtual-clock email pipeline.
7. Once Google access returns, run the live matrix and adjust only the adapter or
   unsupported UI capabilities where possible.

Release gates:

- **Local foundation:** both offices isolated under realistic DB roles; no hidden
  production credentials; current UI parity and happy/failure paths automated.
- **First office:** one supported real Google configuration, verified client
  download flow, approved migration, backups/restoration, notification sink,
  clean build and reviewed release.
- **Five friendly offices:** demonstrated stable sync/reconnect, usable support
  diagnostics, correct digest behavior and known download cost per office.
- **Paid early users:** measured usage/pricing, repeatable onboarding, retention
  terms, stronger recovery target proven, billing process, release protections,
  support ownership and no unresolved tenant-boundary defects.

## 24. Remaining decisions that should stay explicit

The architecture can proceed without reopening the agreed core. These smaller
choices need an owner before their corresponding feature ships:

| Question | Proposed default | Needed by |
| --- | --- | --- |
| First hosting region | Choose once latency is reviewed (the name and domain are settled: Unio, `myunio.app`, A33) | Real DNS/OAuth registration |
| Database instance size/backup retention | Cloud SQL, smallest shared-core instance (A16); confirm price, backups and point-in-time recovery at creation, then prove a restore | Infrastructure purchase |
| Background dispatch technology and refresh interval | In-app maintenance every 10 minutes for the POC (A09); add a queue/worker when needed | Maintenance implementation |
| Timer setup | Prefer Cloud Scheduler within account-wide free allowance; local cron is the alternative | Confirm allowance and cadence before setup |
| Detail presets and stages | Built in (A26, A27): Cliente, Localização, Área do terreno, Área construída, Início, Previsão de entrega, Responsável; 12 stages, each project type ticking its usual ones, with descriptions per type | Slice 3 |
| Custom project details and types | Not in the pilot (A27). Before migrating the first office, list the detail labels its existing `_project` files use; any outside the built-in list becomes a built-in or is mapped, so migration drops nothing | Before migration (section 20); custom details after pilot feedback |
| Editing on the project page and in the painel | Build editing components once in React and load them onto the client page for signed-in staff only, sharing the painel's components and API validation, rather than implementing both editing experiences separately | Step 1.6 (affects how `frontend/` is built) |
| "Precisa de você" (projects needing staff action) | Left out of the pilot; re-evaluate project-level triggers later (broken folder binding, bounced client email, version clash, unreadable file). Office-wide problems such as a lapsed Drive connection are an office notice, and failed creation is part of the creation flow (A07) | After pilot feedback |
| Office tagline | Optional office setting (e.g. "Do primeiro traço ao espaço vivido."); can be left out at first | Branding settings |
| Painel file manager | Not in the pilot unless per-stage uploads prove insufficient (A24) | After pilot feedback |
| Staff app building blocks | Evaluate SVAR React File Manager, Uppy and the Google Picker (section 11) against a custom screen | Slice 3 |
| Password setter | Office owner/member; viewers cannot change it | Access UI implementation |
| Digest semantics | Trailing 45-minute quiet period with a 2-hour maximum hold; quiet period configurable 5–120 minutes | Confirmed for the pilot by Fabio, 16 Oct 2026 (A32); revisit with the first office's real upload sessions. The per-office setting is deferred: the pilot uses 45 minutes and 2 hours for every office (`QUIET`, `HOLD` in `backend/notifications/digest.py`) |
| External file write limitations | Say where to make the change (A34); explicit authorization through the Picker later | Live Google acceptance |
| Revision retention promise | Separate `vN` files for website revisions (A25); no guarantee for overwritten Drive history | Versioning UI copy |
| Download model | Streaming proxy by default, optional authorized Drive link | Hosting/load test |
| Cloud identity operations | Reader per office via managed credentials where practical | White-glove onboarding |
| Account configurations officially supported | Personal My Drive first, add each Workspace type after proof | Each office onboarded |
| Paid tier limits and archive behavior | Active projects primary; manual billing initially | Paid rollout |

A completed plan is not proof of these features. Keep a release checklist with
links to test results, live sandbox evidence, migration reports and approval for
the exact build being promoted.

## 25. Verification of this planning/local-test change

Completed locally on 13 October 2026:

- Combined runner: **80 Python tests passed; eight Chromium browser tests passed**.
- After replacing fixed Python fixture ports with available ports, the 80 Python
  tests passed again. Temporary servers were stopped; manual datasets preserved.
- Gunicorn configuration check and startup/project-page smoke check passed using
  fictional Drive data. No real Google request was required for these checks.
- Browser checks exposed and verified a small CSS correction for custom office
  logos overflowing the header at 320px. Existing fictional logo data was
  sufficient; default dataset generation did not need to change for that fix.
- GitHub `main` remained at `8a21b5b` at the end of this work; no incoming change
  or merge conflict was detected. Work remains uncommitted for review.

Verification used the existing Python **3.11.6** environment and Node **21.5.0**
with pinned Playwright **1.64.0**. The repository's production target is Python
**3.13**. That interpreter and a local container builder were not available in
this session, so a target-runtime/container production build was **not** performed.
There is no frontend bundle build in the current Flask application. Use the
production Python target and a supported Node LTS in the planned CI setup.

No real OAuth-write integration, live Google account-policy matrix, customer
email delivery, migration, deployment or infrastructure change was performed.
Those are named rollout gates, not results implied by the local test pass.
