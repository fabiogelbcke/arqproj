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

## 2026-10-20 — A36 (new), section 5: owners invite staff from the painel

**Was:** section 5 deferred invitation screens as an add-on for larger offices;
staff accounts were made with the `staff` command, which prints a one-time link
to pass on.

**Now:** Configurações → Equipe. An owner invites a person (name, email, role),
and the app emails the one-time link, with "Copiar link" too. An owner can also
turn on a shared office link, for 24 hours: joiners give a name and an email and
get the same emailed link, so they always prove the email is theirs, and they join
as members.

**Why:** Fabio (20 Oct 2026): offices should add their own people rather than us
doing it for them, and asked for both a personal invite and a shared link.
**Considered and set aside:** a shared link that creates the account on the spot
with a password typed there. Section 5 requires invitations to bind a verified
email, and a link passed around a group would let anyone claim any address.
**Kept for later:** removing active staff and changing roles.

---

## 2026-10-19 — Plan section 16: the example project at the top of Primeiros passos; a painel tour

**Was:** the example project's entry was an optional line at the bottom of
Primeiros passos ("Ver um projeto de exemplo"), and "the painel explains
itself": no tour in the painel.

**Now:** an invitation at the top of Primeiros passos, with the example's cover,
leads to the example before the first steps. "?" in the painel's top bar starts
a short painel tour on demand whose last step opens the example. A "?" button is
how any area offers its tour.

**Why:** Fabio, 19 Oct 2026: a new office's first project page looks empty, so
"we'd like them to look at the example project first". On a phone the steps
fill the first screen, so a line below them (or an empty projects list) isn't
seen. He liked the tour "as a button somewhere", reusable, rather than a tour
that starts by itself; an empty projects list was dropped because the steps are
on screen whenever it is.

## 2026-10-19 — A24: the card's pencil opens a menu; A35: nothing about publishing in the staff bar

**Was:** in the painel, a card's pencil opened the "Projeto" dialog straight away,
holding the name, client, cover, client link, access, client emails and
"Arquivar" (which archived at once, with "Desfazer"). On the project page, the
staff bar said "Publicado" under the name, and offered "Publicar" on a draft
left over from before A35.

**Now:** the pencil opens a short menu: "Trocar foto" (the photo picker and
cropper, saved on its own), "Remover foto" when there is one, "Configurações do
projeto" (the dialog, now without the cover or archiving) and "Arquivar projeto",
which asks for confirmation first ("Desfazer" stays). The staff bar has no
"Publicado" and no "Publicar"; the publish endpoint stays, unused, for when
drafts return.

**Why:** Fabio, 19 Oct 2026, reviewing the painel: the dialog was "getting too
big", so the edit button should show "a little pop up menu with a few options:
change photo, project settings, archive project for now", with archiving
confirmed. And since there are no drafts for now, "there shouldn't be anything
about publicar anywhere".

## 2026-10-18 — Plan section 9: another Google account may replace the office's folder

**Was:** reconnecting never replaced the office's folder. A grant from another
Google account was refused ("Esta conta Google não acessa a pasta do
escritório"), so an office could not move to another account at all.

**Now:** after a clear warning that the projects' files stay in the old account,
the owner may connect another account: the office starts afresh there (new root
and empty project and stage folders; covers and logo dropped; no emails for
files re-uploaded). The same account still keeps its folder.

**Why:** offices do change accounts (a personal Gmail to Workspace, a partner
leaving), and being stuck is worse than starting the files afresh. The app's
Drive grant (drive.file) cannot reach the old account's files, so nothing can
move across automatically; a migration tool is a future idea. Fabio, 18 Oct
2026: "just warning that they'll lose everything, very clear and bold warning,
is fine".

## 2026-10-18 — A24: the project's name also editable from its title; shorter client names

**Was:** A24 had the painel's "Projeto" dialog alone edit the project's name; the
client name took up to 48 characters, the office's name up to 80.

**Now:** in the project page's edit mode the title has its own edit button (the
same change as the dialog's; the page's address stays). Client names take up to
30 characters and office names up to 28, checked only when a name changes, so
names saved before stay; the database keeps 48 and 80.

**Why:** Fabio, 18 Oct 2026, reviewing the client page: "Let's make the title
editable in the project page", and "We can make it 30 chars for clients, and if
there's a problem we will expand" (and 28 for the office's name), so names fit
the page on a phone without being cut off.

## 2026-10-17 — A35: no drafts for now; a new project is published at once

**Was:** a new project started as a draft ("Rascunho", 15 Oct): staff saw it,
its client page answered "not found" until staff pressed "Publicar".

**Now:** creation makes it `active`; no publish step or drafts group. The
`draft` status stays allowed in the database, unused, and existing drafts were
published. "Publicar" stays on a draft's staff bar, for one left over by the
previous release during a deploy (A30).

**Why:** Fabio, 17 Oct 2026: "Another thing I think we wanna drop for now is the
Draft projects. We wanna publish them straightway". Kept in the schema because
"for now" leaves room to bring drafts back.

## 2026-10-17 — A21 decided: office subdomains behind a load balancer

**Was:** open between A, `{office}.{product-domain}` behind a global load
balancer (~$18.25/month fixed), and B, one domain with office paths, with A
recommended for anything clients see.

**Now:** A, on `{office}.myunio.app` (A33). The balancer is built before the
second office's first client link, and `alineaarquitetos.com` and `myunio.app`
move behind it then. Staging stays on a free Cloud Run domain mapping.

**Why:** Fabio, 17 Oct 2026: "let's do the load balancer, I have some credits for
the first 3 months anyway". The cost that reopened the question is covered for
now, and every B front door had a production caveat (Preview, or a 60-second cut
on file streams).

## 2026-10-17 — A34 added: staff change files on the website, not in Drive

**Was:** sections 9 and 11 had the site offer an obvious "Open in Google Drive"
link, and "Open in Drive" for files the office's grant cannot change; the
prototype's file menu had "Abrir no Google Drive".

**Now:** no link to Drive from the project page (the Drive settings page keeps
its link to the connected folder, which is about the connection). The file menu offers "Definir como capa", "Mover para
outra etapa" (a list of stages) and "Ocultar do cliente"; dragging onto a stage
comes later as another way to move. For a file put straight into Drive, the site
says where to make the change.

**Why:** Fabio, 17 Oct 2026: "We don't wanna forbid them from using google drive
but as much as possible we should allow changes in the website really". Dragging
is the nicest way to move, he added, but can follow later.

## 2026-10-17 — A33 added: the product is Unio, on myunio.app

**Was:** the product name and domain were open (section 24); the plan wrote
`{product-domain}` throughout, and A23 kept the first office on
`alineaarquitetos.com` partly because there was no product domain yet.

**Now:** the product is Unio and its domain is `myunio.app`, registered at
GoDaddy. Alinea stays on `alineaarquitetos.com`; later offices go on
`myunio.app`. Whether they get subdomains or paths there (A21) is still open, as
is the hosting region.

**Why:** Fabio, 17 Oct 2026: "Unio and myunio.app".

## 2026-10-16 — A10: new files found by a scan for the pilot, not the changes feed

**Was:** section 13 had the sync job read the reader identity's Drive changes
feed from a stored cursor, with a daily reconciliation scan as repair.

**Now:** each maintenance pass lists every published project's stage folders,
as the client page does, and records a file it shows for the first time as "file
published". A project's first scan records what is there without emailing. The
changes feed comes later, when versions need it or scanning gets costly.

**Why:** with a handful of offices the scan costs a couple of hundred Drive calls
a pass, reuses the page's tested listing (hidden names, folders that left their
project), works the same on local folders, and cannot miss a change, so it needs
no cursor or repair pass. The feed needs all of that plus a scan as repair
anyway. Fabio, 16 Oct 2026: "we can start with the scan for now".

## 2026-10-16 — A32 added: client email updates

**Was:** section 14 described batching and privacy for email, and A12 set the
45-minute quiet period with a 2-hour hold "to confirm with a pilot office"; the
recipients, what triggers an email, and the sender were open.

**Now:** staff list several client addresses per project in the Projeto dialog.
Emails go out for new files, a stage advanced or the project completed, and a
meeting scheduled, changed or removed, not for a stage's note. 45 minutes and 2
hours stay for the pilot. Each office sends from its own domain once verified
(Alinea: `alineaarquitetos.com`), otherwise from the product's general domain
under its name; replies go to the office's contact email. One Cloud Scheduler job
runs the maintenance pass every 10 minutes, on staging first.

**Why:** Fabio, 16 Oct 2026: recipients in the Projeto dialog, "yes"; triggers,
"not for notes, but meetings yes and files/stages"; timing, "yes"; the scheduler,
"sure". On the sender, a general domain is being set up for the product: Alinea
keeps its own, other offices use the general one.

## 2026-10-16 — A31 added: uploads go from the browser straight to Drive

**Was:** slice 3b listed "resumable upload into a stage" and "Ocultar do
cliente" with no decisions on who, how large, or how.

**Now:** any staff member uploads from the project page's edit mode; at most
100 MB a file; the browser sends the file to a Google resumable upload the app
opens in the stage's folder, so Cloud Run (32 MB a request) never carries it.
Hiding renames the file with a leading `_`. A same-name file is kept beside the
other for now.

**Why:** Fabio, 16 Oct 2026: "for now, any staff members"; files straight to
Drive "even better"; 2 GB is large, "let's say like 100MB for now"; `_` is fine;
same names don't matter for the short time before versions. The `drive.file`
limit on hiding is Google's: the office's grant sees only what the app created.

## 2026-10-16 — A10: pages read Drive live; the sync job only notices changes

**Was:** a polled sync (about every 10 minutes in the POC) indexed Drive into the
database, and the client page showed that index, so a new file appeared only
after the next pass. The plan asked to show that delay rather than promise
"instant".

**Now:** the project page lists each stage folder from Drive on every visit
(built in step 2.5), and a file opens only while Drive still lists it there. A
public page's browser keeps the list for at most two minutes; staff and
password-protected pages are never cached. The sync job remains, but only to
notice changes: emails (A12), "Atualizado" and the updates feed (A28), and the
document index once versions (A25) arrive.

**Why:** live reads were already needed so a removed or moved file stops
opening at once (A05). With them, a stored copy for display adds a delay and a
second source of truth for nothing. At a handful of offices the extra Drive
calls per visit are cheap. Fabio agreed, 16 Oct 2026, and chose a short browser
cache of two to three minutes over none.

## 2026-10-16 — A28 (interim): what moves "Atualizado" until the updates feed exists

**Was:** A28's feed of client-visible events (`project_events`) decides the
project's "last updated"; that feed isn't built yet.

**Now:** until it is, edit mode moves `last_activity_at` for the changes a
client notices: a stage's note, the meeting (set, changed or removed) and stage
progress. Fixing the description or details doesn't. In edit mode's part 2,
stage folders follow the stages in Drive: renaming or reordering renames the
"NN - title" folders, adding creates one, removing keeps the folder and its
files (the confirmation says so), and a Drive failure saves nothing.

**Why:** Fabio's choices before the overnight run (16 Oct 2026).

## 2026-10-16 — A06 detailed: how the client password works

**Was:** public or password-protected access, details open.

**Now:** staff set the password in the "Projeto" dialog (at least 6
characters, no generator). The client types it once per device, which stays
unlocked for 90 days. After five wrong tries a device waits 15 minutes; the
office gets no email. A new password, or a change of access mode, ends every
earlier unlock. Changing the page's address there keeps the old link working
(A29).

**Why:** Fabio's choices before the overnight run (16 Oct 2026): fewer retypes
for clients, a simple form for staff, and a limit proportional to a shared
link's password.

## 2026-10-16 — A20: the client page is React too

**Was:** client project pages server-rendered with Jinja (fast, simple, good link
previews); only the staff administration in React.

**Now:** the client page is a React app as well: a separate, small bundle served
by the same service. The server still renders what must not wait for scripts: the
preview tags (title, description, cover) that WhatsApp and other apps read, "not
found" for drafts and unknown addresses, redirects from old addresses, and the
password check. Staff editing code loads only when staff press "Editar".

**Why:** A24 (narrowed 16 Oct 2026) made the project page the main place staff
edit content, in an edit mode that shows the page as the client sees it with
controls in place. With Jinja, every section would exist twice (template for
viewing, component for editing) and drift; one React page avoids that and reuses
the painel's pieces. Cost accepted by Fabio: the page needs JavaScript and a first
visit loads slightly slower.

Also recorded the same day: Alinea has no real projects yet, so importing the
current site's projects (step 2.7) is dropped.

## 2026-10-16 — A27: the project type is chosen at creation and ticks its usual stages

**Was:** creation offered three stage templates (Padrão, 7 stages; Interiores, 6;
Sem etapas), and the template set the project type. Built-in stages had two
texts: what happens and what the client receives.

**Now:** creation asks for the project type (Projeto Arquitetônico, de
Interiores, de Reforma, de Paisagismo). All 12 built-in stages are listed in one
order; the type's usual ones come ticked, and staff tick or untick any. Each type
describes its stages in its own words; a stage outside its type's list uses a
general description. One description per stage, no deliverables text. The old
stages (Proposta, Projeto 3D, Layout, Entrega Final, Serviços extras…) and the
templates are removed, and so are the projects made with them. The general
descriptions were drafted from the partners' per-type texts, for them to confirm.

Migration 0013 deletes data and removes columns, tables and an API route in one
release: a deliberate pre-pilot exception to plan section 19 (expand, migrate,
contract) and A30 (compatible API changes). Nothing needs recovering: production
has no projects, and staging's were tests.

**Why:** Alinea's partners wrote the stages each type of project goes through
(Fabio, 16 Oct 2026). The lists overlap heavily and share one order, so a single
list with defaults per type is simpler than templates and lets staff fit each
project. The old stages belonged to the current site's way of working; the
projects using them were tests, so removing them keeps the data clean.

## 2026-10-16 — A24 narrowed: the painel edits settings only

**Was:** details, stages, progress, meeting and the other project content could
be edited in two places: a painel form and the project page's staff edit mode.

**Now:** content is edited only on the project page (edit mode). The painel
edits the project's settings, following the prototype's "Projeto" dialog: name,
client, cover (also from the card's photo button), client link and access (once
the client page exists, slice 2), and archiving. Project type is one of the
details, so it moves to the page. No delete for now; the prototype has none.

**Why:** Fabio, reviewing the P3 proposal: editing belongs where the client sees
the result; two editors for the same content means twice the work and two
places to keep consistent. The cover stays in the painel too, as in the
prototype's cards.

## 2026-10-15 — A07: project creation within the request for the pilot

**Was:** creation as a durable provisioning operation: the project saved as
`provisioning`, a worker creating the Drive folders with checkpoints and leases,
`202` plus an operation URL the painel polls.

**Now:** for the pilot, creation runs within the request: folders first, then
every row in one transaction; any failure saves nothing and trashes the new project folder (best effort). A one-time creation key makes a retried or double-sent request
return the project already created. The durable operation stays the eventual
design (plan section 10).

**Why:** there is no worker yet (A09's maintenance endpoint is not built), a
creation is about eight Drive calls that finish in seconds, and a handful of
offices create a few projects a month. The remaining gap, a crash between the
folders and the save, leaves only an empty folder in the office's Drive, which
nobody sees as a project. Agreed with Fabio for step P2.

## 2026-10-15 — A26 refined: built-in content moves from code enums to reference tables

**Was:** project types, detail types, built-in stages (with their explanations)
and stage templates were enums in code; columns stored their keys with a CHECK,
and their texts lived in the translation files.

**Now:** the code keeps enums only for values it **acts on** (status, access
mode, roles, a detail's value type…). Content the app **only displays** is rows
in reference tables (`project_types`, `detail_types`, `stage_definitions`,
`stage_templates` + `stage_template_stages`), each with its texts per language,
referenced by foreign keys; a detail row also carries its value type so the
database alone guarantees an area is a number. The code keeps enums naming the
built-in rows (Fabio likes them), kept in step with the rows by a test.

**Why:** Fabio questioned the database storing references whose meaning lives
only in code. CHECKs kept data and code from drifting, but content belongs with
the data: the database describes itself, foreign keys give real integrity, and
offices' own details, stages and templates (slice 3 and later) must be rows
anyway. Cost: translations live in two places (interface text in files, content
in the database), with tests covering both.

## 2026-10-15 — project status gains "draft"; meetings become a list; one slug table

**Was:** project `status` unspecified beyond a field; one current meeting per
project ("supports current single meeting first"); old slugs in a separate
`project_slug_aliases` table next to `projects.slug`.

**Now:** status `draft` (unpublished; the client page is not found until staff
publish), `active`, `completed`, `archived`. Meetings are a list per project and
the client page shows the next by date. Every slug a project has had is a row in
`project_slugs`, exactly one current, one namespace per office (A29).

**Why:** the prototype has a "Rascunhos" group for unpublished projects (Fabio
confirmed). A list of meetings costs nothing extra and removes stale past
meetings from client pages by design. One slug table enforces A29 with a single
unique constraint instead of keeping two places in step.

## 2026-10-15 — prototype review and Codex review of the plan: A12, A23, A24, A25 refined; A26–A30 added

Two inputs: the staff/client prototype as iterated in
[`arqprojprototypes`](https://github.com/fabiogelbcke/arqprojprototypes) (its
functionality, not its layout, which is still in flux), and a Codex review of the
plan that Fabio relayed.

- **A12 (email batching).** *Was:* the quiet period described as an "undo window"
  in which a mistaken upload "never reaches the client", with an example sending
  at 11:35. *Now:* it prevents an email about withdrawn files, not exposure,
  since files publish as soon as they are found; a batch becomes due by the
  rules and is sent by the next maintenance run, now every 10 minutes instead of
  hourly (A09 updated to match); the 2-hour hold counts from the first
  publication. *Why:* the old wording promised something the
  design does not do, and the timing ignored when maintenance actually runs.
- **A23 (first office's domain).** *Was:* hosting of the custom domain left
  implicit. *Now:* it stays on the existing free Cloud Run domain mappings of the
  `portal` service; the rewrite deploys as a new revision of that service.
  *Why:* checked how the domain is served today; this costs nothing extra.
- **A24 (editing).** *Was:* cover changed on the project page or in project
  settings; painel fallback cover showed the client's name over a blurred photo.
  *Now:* also changeable from the painel card; the fallback is a plain
  placeholder photo. *Why:* prototype review.
- **A25 (versions).** *Was:* new files named `Planta v3.pdf` everywhere; grouping
  by "clear version token" without collision rules. *Now:* clean name plus a
  version badge on the client page, versioned name only for the Drive copy;
  exact same-name uploads also group; grouping within one folder only; clashes
  flagged, never merged; current = highest version; staff corrections persist.
  *Why:* Codex found the grouping rules underspecified; Fabio preferred showing
  the version separately.
- **A26 (new): built-in options in code, translated; office text as typed.**
  *Was:* "preserve English capability" with no rule for what is translated, and
  detail presets seeded as Portuguese text. *Why:* stored Portuguese labels
  cannot be translated; Fabio scoped translation to the product's text and its
  standard options.
- **A27 (new): typed details and a project type field, built-ins only for the
  pilot.** *Was:* project type and details were free label/value pairs, with
  office-defined presets. *Why:* the prototype sorts and labels projects by type,
  and formats areas and dates. Office-defined details and types were deferred
  (Fabio): they add a definitions table, a "built-in or custom" rule and an
  options editor, and can be added later without converting existing rows.
- **A28 (new): one feed of client-visible events.** *Was:* `publication_events`
  for email only. *Why:* the prototype's "latest updates" panel and "last
  updated" date need the same events, including notes and meeting changes.
- **A29 (new): used slugs stay reserved.** *Was:* old slugs redirect, but nothing
  stopped another project taking one. *Why:* an old client link could land on
  the wrong project (Codex). Deleted projects are soft-deleted and keep their
  slugs too.
- **A30 (new): staff app/API compatibility across deploys.** *Was:* "one revision,
  so the staff app can never run against another API version". *Why:* false for
  tabs already open during a deploy (Codex).
- **Section 9, unshared folder recovery.** *Was:* always create a new folder and
  rebind. *Now:* ask the owner to share the existing folder first; new folder only
  as fallback; to be verified live. *Why:* our writer's limits do not bind the
  owner, and the original folder may hold client files (Codex).

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
