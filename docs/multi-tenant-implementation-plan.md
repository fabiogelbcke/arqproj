# Multi-tenant portal: architecture, implementation and rollout

**Decision draft · 13 October 2026**

Prepared against repository `main` at `8a21b5b`, the supplied
`multi-tenant-plan.md`, and Fabio's subsequent decisions. The newer decisions
below supersede conflicting parts of the attachment. This document proposes a
new backend; it does not apply migrations, create cloud resources, or authorize
deployment. It separates chosen product behavior, recommended implementation,
verified behavior, and work that still needs external verification.

Framework decision updated after discussion: the new backend will use FastAPI
and Pydantic, while retaining Python. Updated 14 October 2026 (A20): client-facing
pages stay server-rendered with Jinja and reuse the existing HTML/CSS/JavaScript;
the staff administration becomes a React + TypeScript app served by the same
service on the same origin. The office address scheme is reopened as an explicit
choice between two options (A21, section 4). References to Flask/Gunicorn in the
current-state inventory and verification history describe the existing
application, not the target backend.

Companion: [infrastructure cost comparison and POC options](infrastructure-cost-comparison.md),
including free-tier assumptions and Cloud Scheduler versus local cron.

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

- Keep Python; use FastAPI and Pydantic for the new backend. Client-facing pages
  stay server-rendered with Jinja and reuse the existing HTML/CSS/JavaScript; the
  staff administration becomes a React app on the same origin (A20).
- Build a clean multi-tenant backend instead of threading tenant parameters
  through the prototype's single-office backend.
- Office URLs: `{office-slug}.{product-domain}` was agreed, and is reopened as of
  14 October 2026 against a single-domain alternative for cost reasons (A21,
  section 4). Either way, display-name changes do not silently change URLs, and
  the choice is made before any client link is shared. Product/domain naming is
  still open. The first office keeps its own domain, `alineaarquitetos.com`, as a
  custom domain of the same deployment (A23); A21 only matters for later offices.
- Project links are simple: `/{project-slug}` on the office's address, as today
  (A22). Optional per-project passwords cover projects that need privacy.
- Creating a project asks only for its name and the client's name (plus an
  optional stage template). Details, stages, meeting, cover image and files are
  edited afterwards, in the painel and in a staff edit mode on the project page
  itself (A24).
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
| A06 | Public or password-protected project access | Agreed; no mandatory client account for the pilot |
| A07 | Atomic DB creation plus recoverable Drive provisioning | Recommended implementation of an all-or-nothing customer experience |
| A08 | Stable document/revision records, not filename-only versioning | Recommended replacement for the prototype's grouping rules. Revised by A25: clear `vN` names still group automatically |
| A09 | Recoverable background work; deployment and dispatch technology open | Revised POC proposal: hourly authenticated endpoint in the web service, with durable application state. Managed queue/separate worker deferred unless needed. See section 4. |
| A10 | Incremental Drive sync, initially polled; reconciliation as repair | Recommended; webhooks can accelerate later without becoming a correctness dependency |
| A11 | Streaming proxy for private Drive content; optional Drive links | Recommended; clients need not have Google accounts or Drive sharing permissions |
| A12 | Email first, trailing "settle" window: send once uploads stop | Revised 14 Oct 2026 from a fixed 60-minute window. 45-minute quiet period, 2-hour maximum hold, configurable per office. See section 14 and the [changelog](decision-changelog.md) |
| A13 | Protected main, staging and approved promotion of one build | Recommended; environments are separate without requiring permanent divergent code branches |
| A14 | Same PostgreSQL engine locally and in production | Recommended; SQLite cannot validate the intended constraints, queue locks or row policies |
| A15 | Cloud Run web with bounded maintenance execution | Proposed hosting continuation; POC can run maintenance in the same service. Actual infrastructure requires separate approval |
| A16 | Managed PostgreSQL: Cloud SQL for PostgreSQL, one small instance in us-east1 holding separate staging and production databases | Agreed 14 Oct 2026, replacing Neon as the candidate. Same region as Cloud Run, so about 1 ms per query instead of roughly 10–15 ms to another cloud; Cloud Run's built-in connector and IAM login instead of a stored database password; daily backups kept 7 days. About $9–10/month for the smallest shared-core instance (verify at creation). Split staging onto its own instance, or upgrade the machine, when load or the number of offices calls for it. See the [changelog](decision-changelog.md) |
| A17 | Resend behind an email adapter | Proposed first provider; choose a plan based on actual volumes and delivery limits |
| A18 | FastAPI + Pydantic + Uvicorn for the new web backend | Agreed framework switch; validated request/response contracts, dependency injection and native async support; Cloud Run remains compatible |
| A19 | Cloud Scheduler preferred within its free allowance; local cron retained as an alternative | User accepts managed scheduling when free. Both call the same protected maintenance endpoint; cadence and deployment shape remain separate decisions. See the [cost comparison](infrastructure-cost-comparison.md). |
| A20 | Client pages server-rendered with Jinja; staff administration as a React + TypeScript app built with Vite, served by the same FastAPI service on the same origin | Agreed direction 14 Oct 2026, replacing "Jinja for all UI, no separate frontend application". Staff screens (file manager, uploads, invitations, settings, connection health) are stateful enough to justify a component framework; client pages stay fast, simple and link-preview friendly. One image, one Cloud Run service, no Node at runtime. See sections 4 and 17 and the [changelog](decision-changelog.md) |
| A21 | Office address scheme | **Open, two options recorded.** A: office subdomains behind a global load balancer (agreed requirement; ~$18.25/month fixed plus processing). B: one domain with office paths (no load-balancer fee, but every no-load-balancer front door has a production caveat). Options and consequences in section 4; decide before DNS/OAuth registration and before any client link is shared |
| A22 | Project links are `/{project-slug}` on the office's address; no random token | Agreed 14 Oct 2026, replacing `/p/{public_token}/{slug}`. Readable and shareable, and the first office's existing links keep working unchanged. Guessable by design; privacy comes from the optional password (A06). Slugs are unique per office and stable once shared. See section 6 and the [changelog](decision-changelog.md) |
| A23 | First office served on its own domain (`alineaarquitetos.com`) as a custom domain of the shared deployment | Agreed 14 Oct 2026. No separate deployment: `tenant_domains` maps the hostname to the office. Custom domains stay deferred for other offices; this one is the exception because it predates the product domain |
| A24 | Minimal project creation; editing in the painel and in a staff edit mode on the project page | Agreed 14 Oct 2026. Creation asks for the project name and the client's name (shown prominently in the painel), plus an optional stage template. Details, stages, stage progress, meeting and files are edited later. Uploads happen per stage on the project page; a full file browser in the painel is optional, not a pilot requirement. See section 10 |
| A25 | File versions named `v1, v2, v3`; "send new version" and same-name upload prompt; automatic grouping of clear `vN` names | Agreed 14 Oct 2026, revising A08. Uploading a file with an existing name asks whether it is a new version; if so it is stored as the next `vN`. Existing files are never renamed (the write scope cannot rename files the app did not create); an unnumbered original is shown as v1. See section 12 |

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
  identity/              staff login, memberships, sessions, invitations
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
frontend/             React + TypeScript staff administration (A20), built by Vite
  src/                   screens, components, API client generated from OpenAPI
  package.json           own lockfile; Node is used to build, never at runtime
```

`backend/` serves both audiences: the client project pages (Jinja templates under
`web/`) and the JSON API the staff app uses, over one shared set of services, so
there is a single copy of rules such as "who may see this file". `frontend/` holds
only the staff app's source and never runs as a server.

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
instead of failing in a browser. Client pages remain Jinja and do not use it.

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
one web deployment with an authenticated maintenance endpoint called hourly. The
worker below is a logical function and need not be a separate deployed service.
The fuller queue and wildcard load-balancer design remains an alternative, not
a prerequisite for the POC. Domain routing is now an explicit open decision with
two recorded options (A21, below); slower refresh timing still needs agreement.
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

Each office is served by the one FastAPI service, from one origin. Under option A
of A21 the layout is:

```text
{office}.{product-domain}/{slug}             client pages: Jinja, server-rendered (A22)
{office}.{product-domain}/painel/...         staff app: React, static files
{office}.{product-domain}/api/...            JSON API used by the staff app
auth.{product-domain}/...                    shared Google login (section 5)
```

Under option B the office moves from the hostname into the first path segment
(`{product-domain}/{office}/{slug}`, `/{office}/painel/...`, `/{office}/api/...`);
everything else in this subsection is the same.

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

Client pages, API and staff app always ship together in one revision, so the
staff app can never run against an API version it was not built for, and a Cloud
Run rollback reverts all three at once. `gcloud run deploy --source` builds from
a root `Dockerfile` when one exists. **Adding that file therefore changes how the
current Flask site deploys**: introduce it with the new entry point at cutover,
or keep it outside the source-deploy path until then (section 19).

Local development: Vite's dev server serves the staff app with hot reload and
proxies `/api` to the local FastAPI process. The release check builds the bundle
and serves it through FastAPI, as production does. Only staff app work needs Node
locally; client pages and backend work do not.

### Office address: two options, decision open (A21)

`{office}.{product-domain}` was the agreed format. It needs a load balancer in
front of Cloud Run, a fixed monthly cost the pilot may not justify. A21 records
both options so the choice is made deliberately, before DNS/OAuth registration
and before any client link is shared. Moving from B to A later means redirecting
every shared link forever.

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

Recommended default if no other information arrives: **A for anything clients
see**, since every B front door either is not production-ready or breaks large
file delivery, and B's main saving is about $18/month. Use the `run.app` URL
with paths for internal testing until real offices are onboarded. This is a
recommendation; the decision stays open until Fabio chooses.

### Scheduling and queue technology: proposal under discussion

The original minute-by-minute scheduler plus PostgreSQL queue was a recommendation,
not an agreed product decision. Separate three responsibilities: a scheduler
decides when recurring work is due, a queue preserves pending work, and a worker
executes it. FastAPI itself does not replace any of these durable responsibilities.

| Option | Technology | Benefit | Main tradeoff |
| --- | --- | --- | --- |
| E: revised POC proposal | One hourly Cloud Scheduler job or local cron → authenticated endpoint in the web service | One deployment; no broker/managed task queue; can let the database sleep | Slower Drive discovery; bounded work shares web resources; retain retryable state and overlap protection |
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

This section assumes option A of A21 (office subdomains). Under option B the
tenant comes from the first path segment instead, the shared `auth.` handoff
becomes unnecessary, and sessions must be bound to a tenant explicitly because
all offices share one origin; revise this section if B is chosen.

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
names. Invitations bind a verified email to an office membership; never grant
membership merely because a user's email has the office's domain.

**Several staff per office, with roles: foundations now, features later.** From
the first version, people (`users`) are separate from offices, a `membership`
links them with a role, every staff action goes through one central permission
check, and audit events record who acted. Each person has their own login; there
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
links already sent to clients do not break.

For password mode, office staff set/reset the password through the panel. This
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
| `users` | identity provider + subject unique, verified email, display name |
| `memberships` | tenant + user unique, owner/member role, active/revoked |
| `invitations` | tenant, intended email, role, token hash, expiry, accepted/revoked |
| `sessions` | opaque token hash, user, tenant, expiry, revocation/version |
| `drive_connections` | tenant, provider account subject, root ID, drive ID/type, read identity, write-token secret reference, separate read/write health, generation |
| `projects` | tenant, title, client name, cover image reference, slug (unique per tenant), status, connection, root/deliverables folder IDs, description, client display name, project type, optional professional, access mode/hash/version, current stage, row version |
| `project_slug_aliases` | tenant, old slug, project; redirects links shared before a slug change or migration |
| `detail_presets` | tenant, label, order, default-on flag; the office's predefined project details (Cliente, Tipo de projeto, Localização, Área do terreno, Área construída…) offered when editing a project |
| `stage_templates` | tenant, name, ordered stage titles with optional explanation/deliverables; the default is the office's standard workflow |
| `project_details` | tenant, project, ordered label/value fields from existing metadata |
| `project_stages` | tenant, project, stable stage key, title, order, status, notes, bound folder ID |
| `meetings` | tenant, project, title, start/end, timezone, location/link; supports current single meeting first |
| `folder_bindings` | tenant, project, connection, provider folder ID, parent ID, path display, classification |
| `storage_items` | tenant, connection, provider file ID, parent, MIME, name, size, checksum/revision metadata, observed capabilities, present/trashed state, last seen |
| `documents` | tenant, project, logical title, stage, current revision ID, publication state |
| `document_revisions` | tenant, document, storage item, application sequence, label, observed content marker, source, published time, availability state |
| `project_recipients` | tenant, project, email, locale, subscription state, unsubscribe-token hash |
| `publication_events` | tenant, project, document/revision, kind, source fingerprint, detected/published times |
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

Use optimistic row versions for simultaneous form edits: a stale update returns
a conflict with the latest values instead of silently replacing someone else's
work. External Google calls happen outside database transactions. Database
constraints, unique request keys and row locks protect concurrency; retries must
not depend on a single worker instance.

## 8. Source-of-truth and synchronization rules

| Data | Authority | Behavior when edited elsewhere |
| --- | --- | --- |
| Project title/client/status/meeting/stages/custom fields | PostgreSQL | Drive `_project` files are imported once, then ignored for product metadata |
| File bytes, physical filename/folder placement, trash | Google Drive | Reconcile into the application's index |
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
and already has foreign content, the share cannot be repaired in place: create a
new folder, share it while empty, and rebind. Record this as a
`needs_attention` outcome rather than retrying the failing call.

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
keep tokens/resumable-session URLs out of logs and browser storage. For local
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
writer cannot modify, offer “Open in Drive” and, where validated, “Authorize this
file” using Picker. Do not advertise universal website rename/move/trash until
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

## 10. Project creation: atomic experience, recoverable external work

**Yes: project creation should be atomic in the database and appear complete to
the customer only when its required setup is complete.** The limitation is that
PostgreSQL and Google Drive do not share a transaction coordinator. A SQL rollback
cannot undo a folder that Google already created, and Google may succeed even
when our connection times out before receiving its response.

Do not hold a database transaction open during a sequence of network calls.
Instead implement a durable provisioning operation:

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
the **client's name** (both required, both editable later), plus an optional
stage template (the office's standard workflow is preselected). The client name
is the main label in the painel, and drives the fallback cover below. The slug is derived from the name and editable; duplicates of an
existing name or slug in the office are refused with the conflicting project
named. Everything else starts empty or from office defaults and is edited later.

Editable after creation, by office staff:

| Content | Editing |
| --- | --- |
| Description | Plain paragraphs and `- ` bullet lines, as today |
| Project details | Chosen from the office's `detail_presets` (Cliente, Tipo de projeto, Localização, Área do terreno, Área construída…) plus custom label/value pairs; reorder, hide empty ones |
| Stages | Add, rename, reorder, remove (only when empty, or with explicit confirmation that its files stay in Drive); per-stage notes |
| Progress | "Advance stage" moves the current-stage pointer; "mark complete" finishes the project. Status (done/current/upcoming) derives from the pointer |
| Meeting | Start, end, subject, location, link; clearing it shows "no meeting scheduled" |
| Files | Upload into a stage, send a new version of a file (section 12) |
| Cover image | Upload, replace or remove; or "set as cover" from an image file in the project. Shown on the painel project card and as a hero at the top of the client page |
| Access | Public or password; change slug (old slug keeps redirecting) |

Where it is edited:

- **Project page edit mode.** A staff session sees a bar on the client page with
  "Painel" (back to the project list) and "Editar". Edit mode shows the page as
  the client sees it, with controls in place: edit details, stages, progress,
  meeting, notes, and upload per stage. This is the main place for day-to-day
  updates and for uploads. Name and slug are not edited here, to keep it safe.
- **Painel.** Project list with status at a glance, project creation, the same
  project settings in one form (including name, slug and access), office
  settings, Drive connection and stage/detail presets.

Without a cover, the painel shows a generated one instead of an empty
placeholder: the client's name set over a blurred, darkened architecture photo,
chosen deterministically per project from a small bundled set so it stays the
same between visits. **Clients only ever see a cover the architect uploaded:** the generated fallback
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
Show an obvious “Open in Google Drive” link. No attempt at copying every Drive
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
- The new file is named with its version (`Planta v3.pdf`). **Existing files are
  never renamed**: the `drive.file` grant cannot rename files the office added
  through Drive. An unnumbered original counts and displays as v1.
- Files added directly through Drive with a clear version token (`v2`, `_v02`,
  and the legacy `rev B` style) still group automatically, as the current site
  does; ambiguous names stay separate and can be grouped by staff.
- Older versions stay downloadable under "Versões anteriores" on the client page. Store a monotonic sequence, optional
human label, date and source. “Current” is a database pointer, not whichever
filename sorts last. Default a successfully published new website revision to
current; staff can select another available revision, with an audit entry.

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
card with download/Open in Drive. Do not invent an image for a real document.

Preview keys include tenant, document/revision, renderer version and size. Async
rendering has memory, file-size, page-count and time limits. Treat filenames and
file contents as untrusted; do not render arbitrary HTML/SVG/scripts in the
portal origin. Keep credentials and provider thumbnail URLs server-side. If
persistent generated previews are introduced, use a private, size-bounded cache
with tenant-aware access and deletion; it is a derivative cache, not custody of
all original files. The initial pilot can use upstream thumbnails and ephemeral
rendering to avoid requiring that extra storage service immediately.

## 13. Sync and durable jobs

Use the read identity's changes feed when coverage is validated. Scope a cursor
to connection generation, identity and Drive corpus; Shared Drives have explicit
configuration. Initial indexing takes a start token, scans the selected tree,
then replays changes from that token to close the scan race. Suppress historical
notification events during this baseline. A reconnect establishes a new baseline
without notifying clients about every old file again.

The fuller design polls active connections approximately every two minutes.
Option E instead proposes an hourly sweep for the POC, or 15 minutes after checking
database usage; this freshness tradeoff needs agreement. UI-triggered sync can
request earlier bounded work with a rate limit. Show the selected freshness expectation
rather than “instant”. Coalesce repeated poll requests. A scheduled daily
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
to impersonate an office's domain before it has configured email authentication.
Resend is the proposed adapter; keep provider-specific behavior out of batching
logic. Configure SPF/DKIM/DMARC, suppression and bounce handling before sending
to customers. Provider quotas count recipients, so a digest to ten people is not
necessarily one billable message. [Resend limits and plans](https://resend.com/pricing)

Default batching: a **trailing "settle" window**. A publication starts a pending
batch; the batch becomes due once **nothing new has been published for 45
minutes**, subject to a **maximum hold of 2 hours** from the first event in the
batch. Example: uploads at 10:00, 10:20 and 10:50 send at 11:35, as one batch;
an upload at 11:40 starts a new one. An office that uploads continuously all
afternoon still gets mail, because the maximum hold closes the batch regardless.

Offer an office setting with a bounded range, initially 5–120 minutes for the
quiet period, and a maximum hold bounded separately. A send-now action can close
a pending batch; it does not create duplicate deliveries.

Why trailing rather than a fixed window from the first event: a drawing set is
uploaded over tens of minutes, and a fixed window splits one delivery session
across two emails whenever the upload straddles the boundary. The architect made
one delivery and the client should get one mail. The cost is unbounded latency
without the hold cap, which is why the cap is not optional.

The window also functions as an **undo window**, which is worth stating because
it changes the risk of automatic notification: an upload into the wrong project,
noticed and removed within the quiet period, never reaches the client. That
argues for erring longer rather than shorter, and against letting an office
configure the quiet period down to 5 minutes without warning them what they are
giving up.

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
published project do not create “new file” mail. A genuinely new visible revision
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
remove download costs either. Offer a direct “Open in Drive” path where suitable,
measure actual usage, then decide whether a separate delivery/storage tier is
worth introducing.

Track monthly per-office original-download bytes, preview bytes, upload handling,
request count, active projects and support time. Budget includes web/worker,
PostgreSQL/backups, domain/TLS/load balancing, email, secrets/keys, logs and
network. Do not price the product from storage alone or advertise unlimited
bandwidth while learning these workloads. Public links need abuse monitoring
and rate controls without forcing legitimate clients to create accounts.

## 16. Branding, accessibility and language

Pilot branding: office name, light/dark logo, accent color, bounded neutral palette,
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
locale arguments; never change global environment variables per request. Timezone
is per office. Long Portuguese labels, accents, duplicate filenames and non-Latin
names belong in fixtures. Template content and default stage descriptions are
versioned: updating defaults does not overwrite an office's edited project stages.

## 17. API and error conventions

Client-facing routes render Jinja pages with progressive JavaScript, as today.
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
| `POST /api/admin/connections/{id}/disconnect` | Disable both application access paths; cancel stale work |
| `GET /api/admin/operations/{id}` | Progress or actionable failure |
| `POST /integrations/drive/events` | Validate registered channel; enqueue sync only |
| `POST /integrations/email/events` | Validate signature; deduplicate delivery update |

Never accept a caller-supplied tenant as authority. Resolve it from the host/session
and verify every resource. Use consistent error codes: validation, conflict,
connection needs attention, quota exceeded, provider unavailable, file unavailable.
Show clear Portuguese messages and a support/request ID. The API returns the
error code and a translated message; the staff app displays the message and never
builds its own text from provider details. Redact provider details
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

Use small end-to-end slices with reviewable PRs. Effort ranges below are planning
hypotheses for AI-assisted work, not a promise about calendar availability.
Several steps can happen in one focused session; permission setup, observation
and external failures do not shrink simply because code generation is fast.

| Slice | Concrete deliverable | Exit evidence | Rough focused effort |
| --- | --- | --- | --- |
| 0. Baseline | This decision doc and repeatable current local tests | Python/browser suite runs without Google; open issues recorded | Current work |
| 1. New foundation | New FastAPI factory and Uvicorn entry point, local PostgreSQL, migrations, tenant routing, fake identity, two offices; staff app skeleton (Vite + React + TypeScript) served at `/painel` from the two-stage image | Wrong-host/ID tests; runtime-role isolation; production image boots locally and serves the staff app shell | 1–2 days |
| 2. First useful vertical slice | Public/password project page at `/{slug}`, DB metadata, reused UI, read adapter and legacy import; staff bar on the page | Two branded offices; password protects every content endpoint; migration dry run; `alineaarquitetos.com` resolves to its office | 2–3 days |
| 3. Project creation + editing | Minimal creation with durable provisioning; painel project list/settings and page edit mode for details, stages, progress, meeting (A24) | Crash/retry matrix; no duplicate creation; edits visible on the client page; row-version conflicts handled | 2–3 days |
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
| Product name/domain and first hosting region | Choose once office URL examples and latency are reviewed | Real DNS/OAuth registration |
| Database instance size/backup retention | Cloud SQL, smallest shared-core instance (A16); confirm price, backups and point-in-time recovery at creation, then prove a restore | Infrastructure purchase |
| Background dispatch technology and refresh interval | Evaluate hourly in-app maintenance first for POC; add a queue/worker when needed | Maintenance implementation |
| Timer setup | Prefer Cloud Scheduler within account-wide free allowance; local cron is the alternative | Confirm allowance and cadence before setup |
| Detail presets and stage templates | Seed from the first office: Cliente, Tipo de projeto, Localização, Área do terreno, Área construída; the seven standard stages | Slice 3 |
| Painel file manager | Not in the pilot unless per-stage uploads prove insufficient (A24) | After pilot feedback |
| Office address scheme (A21) | Two options in section 4: A, office subdomains behind a load balancer; B, one domain with office paths. Recommended default: A for anything clients see, `run.app` paths for internal testing | Before DNS/OAuth registration and before any client link is shared |
| Staff app building blocks | Evaluate SVAR React File Manager, Uppy and the Google Picker (section 11) against a custom screen | Slice 3 |
| Password setter | Office owner/member; viewers cannot change it | Access UI implementation |
| Digest semantics | Trailing 45-minute quiet period with a 2-hour maximum hold; quiet period configurable 5–120 minutes | Notification acceptance tests; confirm both figures with a pilot office |
| External file write limitations | Disable unsupported actions + Open in Drive / explicit authorization | Live Google acceptance |
| Revision retention promise | Separate `vN` files for website revisions (A25); no guarantee for overwritten Drive history | Versioning UI copy |
| Download model | Streaming proxy by default, optional authorized Drive link | Hosting/load test |
| Initial upload cap / large-file target | Establish using the pilot offices' actual files and deployment limits | Upload beta |
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
