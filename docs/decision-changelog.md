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
