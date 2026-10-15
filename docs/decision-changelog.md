# Decision changelog

Companion to the decision register in section 2 of
[`multi-tenant-implementation-plan.md`](multi-tenant-implementation-plan.md).

The register says what each decision **is**. This file says what it **was**, and
why it changed. Kept separate so the plan stays readable for humans.

**Why bother:** a current-state table cannot record a rejected alternative, so
nothing stops the same argument being had again in three months by a different
person or agent. Every entry below is an argument that has already been
resolved. If you want to reopen one, read its entry first and say what new
information you have.

**How to add one:** newest at the top. Record the register ID, the date, the old
position, the new position, and what actually changed the answer. Never edit a
past entry — add a new one. If a decision reverts to a previous position, that is
a new entry too.

---

## 2026-10-15 — staff accounts: users + memberships → one account per office

**Was:** people (`users`) separate from offices, linked by `memberships` carrying
the role (plan sections 5 and 7), so one account could work in several offices.

**Now:** each staff account belongs to one office (`users.tenant_id`, with the
role on the user); an email is unique within an office. Someone working for two
offices has two accounts.

**What changed the answer:** for the pilot nobody belongs to two offices, and the
cases that might (freelance consultants, our own support access) are better served
by project collaboration and a separate admin mechanism. Without memberships,
`users` is an ordinary office table under the same isolation rule as every other,
instead of needing its own "visible through a membership" policy, and managing an
office's staff is one list in one table.

**What it costs:** a person in two offices has two logins. Moving to users +
memberships later is a routine migration; merging duplicate accounts of the same
person is the only awkward part.

---

## 2026-10-14 — A16: Neon (candidate) → Cloud SQL for PostgreSQL

**Was:** managed PostgreSQL with Neon as the initial candidate, mainly for its
free tier and scale-to-zero; the cost comparison budgeted the POC on Neon Free.

**Now:** Cloud SQL for PostgreSQL, one smallest shared-core instance in us-east1,
with separate databases and users for staging and production.

**What changed the answer:** the money involved is small (about $9–10/month)
next to what it buys for an app holding a paying office's data. Neon runs on
AWS or Azure, so from Cloud Run in us-east1 every query would cross clouds,
adding roughly 10–15 ms each; a page with ten sequential queries loads
noticeably slower. Cloud SQL sits in the same region, connects through Cloud
Run's built-in connector with IAM login (no stored password), keeps 7 days of
daily backups, never sleeps, and keeps hosting on one bill and one permission
system.

**What it costs:** the monthly fee instead of free; the smallest machines have
no uptime SLA and few connections. **Lost:** Neon's instant database branching,
convenient for testing but not required.

---

## 2026-10-14 — A25 (revises A08): explicit revisions only → `vN` naming, automatic grouping kept

**Was:** A08 and section 12 replaced filename-based versioning with explicit
document/revision records. Files added through Drive would only be *suggested*
as versions of each other; staff confirm, otherwise each file is its own document.

**Now:** the office convention is `v1, v2, v3`. Each file has "Enviar nova
versão", and uploading a file whose name already exists in the stage asks whether
it is a new version; if so it is stored as the next `vN`. Clear version tokens in
names added through Drive still group automatically, as the current site does.
The database records of A08 remain the underlying model.

**What changed the answer:** the office asked for it. Architects should not type
version numbers, and automatic grouping is how the current site already behaves,
so taking it away would be a regression they notice. Explicit records still
matter for ambiguous names, which stay separate unless staff group them.

**Rejected:** renaming the existing file to `v1` when a second version arrives.
The `drive.file` grant cannot rename files the office added through Drive, so it
would only work sometimes. The unnumbered original is *shown* as v1 instead.

---

## 2026-10-14 — A23: custom domains deferred → first office keeps alineaarquitetos.com

**Was:** custom customer domains explicitly deferred; every office on the product
domain (`{office}.{product-domain}`, A21).

**Now:** the first office is served at `alineaarquitetos.com` by the shared
deployment, through a `tenant_domains` row. Other offices still wait for the
product domain, and A21 can be decided then.

**What changed the answer:** there is no product domain yet, the first office's
clients already use links on that domain, and for the next weeks it is the only
office. The tenant-by-hostname design already supports it, so it costs no
separate deployment.

---

## 2026-10-14 — A22: `/p/{random token}/{slug}` → `/{slug}`

**Was:** section 6 recommended `https://office.product/p/{public_token}/{optional-slug}`:
a stable random token so URLs are harder to guess, with old URLs aliased.

**Now:** `/{project-slug}` on the office's address, exactly like the current site.
Slugs are unique per office and stable once shared; a deliberate slug change
keeps the old one redirecting. Privacy for a project comes from the optional
password (A06), not from an unguessable link. Also dropped from the current
site: the painel warning that a link taken from the folder name is easy to guess.

**What changed the answer:** readable links are part of the product the office
shares with clients, and the existing links must keep working. The token never
made a public page secret anyway; the plan already said public mode "does not
turn into a secrecy promise". Offices that need privacy have passwords.

---

## 2026-10-14 — A21: office subdomains (agreed) → reopened as an explicit choice

**Was:** office URLs use `{office-slug}.{product-domain}`, listed as a confirmed
choice in section 1. The cost comparison already noted that this needs a load
balancer and that a cheaper POC route "needs agreement", but no decision existed.

**Now:** open, with two options recorded in section 4: A, office subdomains behind
a global load balancer; B, one domain with the office in the path. The plan
recommends A for anything clients see and the `run.app` URL with paths for
internal testing, pending Fabio's decision. Section 1, register row A21, section 5
(which assumes A) and section 24 updated.

**What changed the answer:** cost visibility, and a correction. The load balancer
is a fixed ~$18.25/month before traffic, which is most of the pilot's hosting
bill. B looked free because Cloud Run has its own domain mapping, but Google marks
that feature Preview and "not recommended for production services". The other
cheap front door, Firebase Hosting, cuts every request at 60 seconds, which
breaks streaming large files to clients (A11), and forwards only one cookie named
`__session`. So B's saving comes with a production caveat whichever way it is
done, and that tradeoff deserves an explicit choice rather than a silent default.

**What it costs to defer:** nothing until a client link is shared. After that,
changing scheme means redirecting every shared link permanently.

---

## 2026-10-14 — A20: Jinja for all UI → Jinja client pages + React staff app

**Was:** keep Jinja, HTML, CSS and small JavaScript for the whole UI (A01, section 1),
with "a wholesale SPA rewrite is unnecessary" (section 17) and OpenAPI-generated
frontend types as optional tooling, "not a requirement to replace Jinja with a
separate frontend application" (section 3).

**Now:** client-facing pages stay server-rendered with Jinja. Staff administration
becomes a React + TypeScript app built with Vite, served as static files by the
same FastAPI service on the same origin, talking to a JSON API under `/api/`. One
two-stage image (Node only at build time), one Cloud Run service, one deploy.
Sections 1, 3, 4, 11, 17, 18, 19, 23 and 24 updated; register row A20 added and
A01 narrowed to client pages.

**What changed the answer:** the staff side outgrew forms. Building the prototype's
Drive panel on the `drive` branch (connect flow, new-project modal, settings,
duplicate checks) showed how quickly modal state, validation and live feedback
pile up in hand-written JavaScript, and the next screen, a file manager with
drag-and-drop uploads, progress and multi-select, is exactly what component
frameworks and their ready-made components exist for. The best open-source file
manager found (SVAR, MIT) is React-only. Multi-tenancy itself did not force this;
the planned staff features did.

**Why not React everywhere:** client pages are read-only, opened from a shared link,
usually on a phone. Server-rendered HTML is faster there, simpler to brand per
office and straightforward for link previews. **Why not Next.js:** it adds a Node
server runtime next to Python for little benefit to this app. **Rejected for now,
not forever:** htmx/Alpine on Jinja; reconsider only if the staff app turns out
to need little more than forms.

**What it costs:** a JSON API with CSRF protection for every staff action (largely
needed anyway for uploads and progress), a build step, a second test toolchain,
and npm dependencies to keep updated.

---

## 2026-10-14 — A12: fixed batching window → trailing settle window

**Was:** a fixed 60-minute window starting with the first eligible publication.
Uploads at 10:00, 10:20 and 10:50 send at 11:00; an 11:05 upload starts the next
window.

**Now:** a trailing window — the batch is due once nothing new has been published
for 45 minutes, with a 2-hour maximum hold from the first event. Register row
A12, section 14, and the digest-semantics row in section 24 all updated.

**What changed the answer:** a drawing set is uploaded over tens of minutes, so a
fixed window splits one delivery session across two emails whenever the upload
straddles the boundary. The architect made one delivery; the client should get one
mail. The plan had already anticipated this alternative ("if offices prefer 'one
hour after the last upload', add a trailing window with a maximum wait cap") — this
promotes it from alternative to default.

A second property argued for it: the quiet period doubles as an undo window. An
upload into the wrong project, noticed and removed within 45 minutes, never
reaches the client. That matters more under automatic notification than it would
under a manual send.

**What it costs:** unbounded latency if the hold cap is ever removed or
misconfigured. The cap is not optional. The fixed window's one real advantage was
bounded latency by construction.

**Still open:** 45 minutes and 2 hours are guesses. Confirm with a pilot office.

---

## 2026-10-14 — notifications: architect-triggered → automatic

**Was:** the architect presses a button — a "publicar e avisar o cliente"
checkbox on publish, plus a standalone notify button. Recorded as decided in an
earlier planning document, before this register existed.

**Now:** detection is automatic, debounced by the window in A12 above.

**What changed the answer:** the product promise is that the architect keeps
working in Drive. A notify button means they finish in Drive and then go to a
second website to tell the client, so the step the client actually experiences is
the one most likely to be forgotten — and worse, the office then believes the
client was told. The argument *for* a button had been that automatic detection
spams, one drawing set being dozens of file events; that turned out to be a
batching problem, not a reason for manual control.

**Also rejected, and still rejected:** web push as the client channel. iOS Safari
will not deliver push to a browser tab — the user must add the site to their Home
Screen and open it from that icon, and the installed app and the browser are
separate subscription contexts with no workaround. A homeowner who visits twice a
month will not do that, so iOS clients would silently get nothing. Push also only
reaches people who have already visited and opted in, so it cannot announce a
first delivery. Email reaches everyone and needs no permission.

---

## 2026-10-13 — project metadata: Drive `appProperties` → PostgreSQL

**Was:** an earlier draft proposed moving project metadata out of a hand-edited
text file in Drive and into Drive `appProperties`.

**Now:** metadata lives in PostgreSQL (A03). Drive stays authoritative for files
and for the existence of folders. `appProperties` keeps one narrow job: opaque
operation and step markers written as recovery hints during provisioning
(section 10), never substantive metadata, never read in the hot path.

**What changed the answer:** two things. `appProperties` have tight size limits
and stage notes and project descriptions are free text that will outgrow them.
And a database exists anyway for tenants and auth — once it does, metadata there
costs nothing extra and buys ordering, filtering and cross-office admin views
that Drive cannot give without N API calls.

**Worth keeping straight:** the original fragility was never "metadata lives in
Drive". It was "metadata lives in a hand-edited text file keyed by folder name".
Both halves were the problem, which is why the fix is also two-part: a real
database, and keying by folder ID rather than by name.
