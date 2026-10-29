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

## 2026-10-28 — A40: owners may update the office's details from a proposal

**Was:** saving a proposal only filled in the office details the office lacked;
changing ones already set was done in Configurações → Escritório.

**Now:** the empty ones are still filled in for anyone. When an owner saves a
proposal whose details differ from the office's, they are asked whether to update
the office too ("Atualizar escritório" / "Só nesta proposta"). Members are not
asked; their changes stay in the proposal.

**Why:** Fabio, reviewing the branch: an owner who corrects a phone or address
while writing a proposal usually means it for the office, and going to the
settings afterwards is easy to forget. Asking keeps one-off changes (another
signatory for one client) out of the office's details.

## 2026-10-28 — A40, A24: "Nova proposta" button instead of a checkbox

**Was:** one optional checkbox in the creation form, "Começa como proposta"
(entry below, same day).

**Now:** a secondary "Nova proposta" button beside "Novo projeto" opens the same
form, titled "Nova proposta", and goes straight to the proposal generator after
creating. On phones the floating + opens a menu of the two.

**Why:** Fabio, reviewing it: a checkbox at the end of the form is easily missed,
and offices think of a new client's first step as a proposal. One form behind
both keeps a proposal a project in an early status, not a separate thing.

**Alternatives rejected:**
- *Two equal buttons.* Most creations are still projects; "Novo projeto" stays
  the main one.

## 2026-10-28 — A40 (new), A24: proposals, with a "Proposta" project status

**Was:** no proposals. A project was `active` from creation (A35), and its page
showed stages and files from the start. Creation asked for name, client, type,
stages and optional client emails (A24).

**Now:** staff generate a branded proposal PDF from the project page. Creation
gains one optional checkbox, "Começa como proposta", which starts the project in
a new `proposal` status: its client page shows only the proposal and the office's
contact details until staff mark it accepted. Proposal services and their texts
are separate from stages, saved as office presets. No emails, no online
acceptance.

**Alternatives rejected:**
- *Reuse the `draft` status.* A draft's client page is "not found", but the
  proposal is meant to be sent through the project page.
- *Every project starts as a proposal*, or *generating a proposal switches the
  status.* The first adds a click for offices that never send proposals; the
  second changes the client's page without staff expecting it.
- *Proposal items are the project's stages, with one description each.* The
  example proposals list services that are not stages (rendered images,
  lighting and plumbing as separate items), and their sales wording differs from
  a stage's description on the client page.
- *Show the planned stages beside the proposal.* They would be empty.
- *Email the client when a proposal is generated.* Offices may want to present
  it first.
- *Online acceptance.* The product is not a negotiation tool; the PDF keeps
  signature lines.

**Why:** Fabio, 28 Oct 2026, from two proposals of a friendly office: proposals
are written by hand today (with mistakes such as differing footers between
pages), and a project page with only a proposal should not look empty.

## 2026-10-28 — A31/A34: renaming and hiding sections; dragging files to move them

**Was:** renaming or removing a section stayed in Drive (A31, 26 Oct). Dragging
a file onto another stage was "a later addition" (A34).

**Now:** "Renomear seção" and "Ocultar seção" on a section's "⋯". Hiding renames
its folder `_name`: the section and its files leave the page but stay in Drive,
and the confirmation says so. In edit mode a file card dragged onto a stage or
into a section moves there, as "Mover para…" does.

**Why:** Fabio, 28 Oct 2026. For a section that still holds files he chose
hiding over the alternatives:
- Moving its files up into the stage and trashing the folder fails for any file
  added through Drive, which `drive.file` can't move.
- Allowing removal only of empty sections means more clicks.
Hiding works for every section the app made and loses nothing.

---

## 2026-10-28 — A38 (proposed): a link to create an office, the base for signup

**Was:** only an operator creates an office and its address (the dashboard, or
`make tenant`); its owner then signs up through a one-time owner link (A36). An
open signup page was declined (A36, 25 Oct): "links we generate".

**Now (for review):** an operator can make a one-time link to create an office.
Its holder names the office and picks its `{address}.myunio.app` on Unio's
address; the office and address are created through the operator's lifecycle
login, the link is used up in the same transaction, and the browser goes on to
the new office's existing owner signup. Still no open signup: a link is needed,
and only an operator makes one.

**Why:** Fabio, 28 Oct 2026: "an office creation page that is only via
sharable link for now, but in the future we can use as basis for the actual
sign up page". It lets the person pick their own name and address (a trade-off
the owner-link flow recorded) without opening signup to anyone. The app's own
login gains no privilege: creation stays with the lifecycle login, and the new
table `office_signup_links` is granted to it alone (migration 0040).

**Not yet:** public signup without a link (needs rate limits, abuse checks and
perhaps payment, A38/section 22). On staging, offices it makes get an address
under `staging.myunio.app`, which isn't routed (staging serves one office).

---

## 2026-10-28 — A39: clients' and visitors' use of project pages, without cookies

**Was:** PostHog recorded staff only. Clients and suppliers stayed personless,
their browsers never loaded PostHog, and the privacy policy said visitors of
project pages are not tracked. The only visitor data was `file_transfer` bytes.

**Now:** the server also records what visitors do (unlocking a page, the
meeting's calendar file, share pages, email subscriptions, update emails sent
per office), each with an anonymous visitor id that changes every day and the
device kind. On project pages, visitors who
aren't signed-in staff get PostHog in cookieless mode: page views, where they
came from, clicks without their text, and a few named actions. Still no cookies,
no person profiles, no names or emails, no session recording. More staff
actions are sent (stages renamed, moved or removed, publishing, covers, office
settings, Drive connected, uploads with their size, the tour), and sign-ins say
how (password, Google, a link, joining). The browser sends no page title and
no project address (a project page is `/projeto` plus the project's id, Fabio's
choice: the address is made from the project's name) and keeps only `utm_` tags
from addresses. The privacy policy says what is measured on project pages and
shared files.

**Why:** Fabio (28 Oct 2026) wants to know whether offices use the features as
intended, what they use most, how clients use the project page, and what drives
costs (downloads, uploads, emails). Staff-only data answered none of the client
questions. Asked to choose, he took both the server-side anonymous events and
PostHog's cookieless mode in visitors' browsers now (rather than the browser
part later), and the daily visitor hash so distinct visitors can be counted.
Cookieless mode needs no consent banner: nothing is stored in the browser and
no one can be followed across days.

## 2026-10-26 — A31: sections in a stage, made from the page

**Was:** a stage's subfolders were shown as titled groups (one level), but only
folders made in Drive; creating folders belonged to an optional painel file
manager (A24, section 24), not built for the pilot.

**Now:** "Nova seção" in edit mode makes a subfolder of the stage's folder.
Staff upload into it from its own drop area and move files into it ("Mover
para…", within the same stage too). The page calls it a "seção", not a
folder. An empty section shows only to staff. Sections are named by their
name in requests, never by Drive id. Renaming and removing them stays in Drive.

**Why:** Fabio, 26 Oct 2026: the reading side already supported subfolders, and
offices group a stage's files (plans, renders) without leaving the site (A34).
The full painel file manager is still not needed for that.

---

## 2026-10-26 — A38/A39: on-demand file statistics and audited management

**Was:** a read-only dashboard, followed by lifecycle actions and PostHog links.

**Now:** extend the read-only view with project completeness and link status/usage;
load file sizes, types and quota only on request, without saved summaries. Use
PostHog for transfer trends. Lifecycle actions record a durable audit event;
audit browsing may follow later. Correct A38's stale read-login wording to match
section 21 and the earlier decision below (tenant-scoped app login for reads).

**Why:** Fabio wants to learn which measures are useful before adding reporting
tables. File statistics will not be needed on every visit. He approved the audit
events and implementation, with no actual share links or client content exposed.

---

## 2026-10-26 — A39 (new): product analytics with PostHog, server and browser

**Was:** no product analytics; the privacy policy listed Google Cloud and Resend
as the only providers.

**Now:** the backend sends staff actions and server errors to PostHog, tied to
the account's id, its role and its office, never the email or name. It runs only
where the token is set (production). The privacy policy names PostHog.

**Why:** Fabio wants to see how offices use the product. The PostHog wizard's
setup sent the staff member's email and name as person properties: Fabio chose
the id and role only (26 Oct 2026), which is enough to count and follow usage
without personal data at a US provider. He added the office as a group, so usage
can be seen per office. The wizard's Logs exporter (three packages for three log
lines, one per health check) was dropped: Cloud Logging and the email alerts
already cover it. It also failed every local run without a token, and read the
old app's `.env`, which would have sent tests' events to the real project; both
removed. The browser side (the wizard's too) read its key at build time; but
production deploys staging's image, so the key now comes from `/api/me` at run
time, to staff only. Its events that the server already sends (projects, stages,
share links) were dropped so nothing counts twice.

---

## 2026-10-26 — Section 5: Google sign-in's hand-off is Google's PKCE-bound code

**Was:** the shared return address completes login on the office through "a
short-lived, single-use handoff code" bound to the office and the browser, of
which only a hash is stored.

**Now:** the return is forwarded, unchanged, to the office's own address, and
Google's authorization code is that hand-off: Google makes it single use and
short lived, and it can only be redeemed with the PKCE verifier held in a
signed cookie for the office's address alone (with the flow's state and nonce),
so the same replay, wrong-office and wrong-browser refusals hold.

**Why:** the properties section 5 asks for come from the code's binding, not
from who mints it; minting a second code would add a table and a step for the
same guarantees. The Drive connection already forwards its return the same way.

---

## 2026-10-26 — A38: the dashboard reads with the app's own login, office by office

**Was:** (A38, earlier the same day) cross-office reads and the lifecycle
actions would both go through a separate database login.

**Now:** reads use the app's own login, scoped to each office in turn exactly as
a request is, so the isolation policy applies to every read and no login sees
every office at once. The separate login stays for the lifecycle actions
(creating, suspending, deleting offices), which need privileges the app lacks.

**Why:** found while building slice 1: with a handful of offices, a few queries
each is cheap, and it needed no new database login or privileges (so no schema
or infrastructure change for a read-only first slice). Codex's review of PR #138
pointed out the register still said otherwise.

---

## 2026-10-26 — A38 (new), section 21: an operator dashboard

**Was:** section 5 named a "Platform operator" with "operational tools with
audit", and section 21 said operators "can inspect redacted operational state",
but nothing was built: offices, owners and links were made with `make` commands
against the database, and debugging meant reading Cloud Logging by hand.

**Now:** a dashboard at `myunio.app/admin`: Google sign-in for allowlisted
operator emails, offices with counts and health, a support-ID lookup, creating
offices with their owner link, suspending, and deleting only a suspended office.
Audited; no client content; a separate database login for cross-office work.

**Why:** Fabio, 26 Oct 2026: to see who is on the platform, help clients with
issues and manage offices without terminal commands. Chosen over a password
account for operators (more to build and protect), over deleting in one step
(no way back), and over a separate service (more infrastructure for a small
team; the pages refuse every office's address instead).

---

## 2026-10-26 — A27: one survey stage, "Levantamento"

**Was:** 12 built-in stages, among them both "Levantamento" (site survey) and
"Levantamento e Diagnóstico" (Reforma's survey of the existing building).

**Now:** 11. "Levantamento" covers both; Reforma's usual stages list it with
Reforma's own description ("Análise das condições existentes, estrutura e
instalações."). Projects that had "Levantamento e Diagnóstico" show
"Levantamento" in its place (notes and folder kept); a project that had both
keeps the second as its own stage under the old title.

**Why:** Fabio, 26 Oct 2026: two stages named "Levantamento…" are redundant.

---

## 2026-10-25 — A36, section 5: a one-time owner signup link from a command

**Was:** creating an office's first owner required the operator to know the
person's name and email and run `make staff ROLE=owner`, which printed an invite
link to choose a password.

**Now:** `make owner-link TENANT=…` prints a one-time link, valid for 7 days by
default, without creating an account or requiring a name or email. Its recipient
chooses name, email and password, then confirms the email with the existing
6-digit code before using the owner account. The link is consumed atomically
with account creation. Only its hash is stored. The painel's shared link still
creates members only and neither lists nor revokes owner links.

**Why:** Fabio approved this smaller onboarding step and migration 0037 with the
`join_links` schema changes on 25 Oct 2026. It reuses the signup and confirmation
flow already built, while keeping office and address creation in operator
commands. A combined office-creation command and a guided setup checklist remain
future work.

---

## 2026-10-25 — A37, sections 7 and 15: "Baixar tudo", a password per link, staff copy any link

**Was:** a supplier downloaded files one at a time; a link had no password of
its own; only a hash of a link's token was stored, so only the device that made
a link could copy it again.

**Now:** "Baixar tudo" downloads every file of the link as one zip, a folder per
stage. The sender can protect a link with a password. The token is also kept
encrypted, so staff can copy any link from the project's list. A client still
sees and manages only the links made on their device (Fabio chose to keep it).

**Why:** Fabio asked for the zip and the password (25 Oct 2026), the slices left
for later. Keeping only a hash protected less than it seemed: a link opens only
files the client can already see, and staff need to resend links they didn't
make. Clients stay per device because anyone with the page's address counts as
the client, so letting every visitor see or manage every link would let anyone
with that address turn off the office's links to its suppliers.

---

## 2026-10-25 — A36, section 5: the shared link takes a password; a code confirms the email

**Was:** whoever opened the office's shared link gave a name and an email and was
emailed an invite link, on whose page they chose a password: two steps, and the
second only by email. One answer whatever the address, so the page never said
whether an account existed.

**Now:** one page asks for the name, the email and the password, and signs the
person in; the account does nothing else until a 6-digit code emailed to the
address is typed in (or the email's link pressed). "Reenviar código" and
"Corrigir e-mail" on that screen, and signing in again, cover an email that
doesn't arrive or a mistyped address. An address that already has an account is
refused with that reason.

**Why:** Fabio wanted the password on the sign-up page, without a separate step
reached only through the email, to get people onboarded. Considered and rejected:
confirming the email later as an onboarding step, with the account working
meanwhile (anyone with the shared link could use someone else's address until an
owner noticed); and a password on the first page with only a link to click (a
link opened on the phone lands outside the screen they signed up on, and whoever
receives an unrequested one could confirm an account set up in their name; the
code only works in the account's own session). The email still carries a link
too ("we can add code or link", Fabio): pressing it confirms the address but
signs nobody in, and the email tells anyone who didn't sign up to ignore it. The
remaining risk (someone presses an unrequested link) gives no more than the
shared link already does: a member's access, under another's address. Saying an address has an account tells only someone holding
the office's link, at its rate limit.

---

## 2026-10-25 — A37 (new), sections 7 and 15: sharing files by link

**Was:** an idea in future ideas (25 Oct 2026). Leaning: a link follows each
file's current version; staff see every link but don't control them; about 20
active links per project and about 20 full downloads per link per day.

**Now:** a link serves the exact versions it was made with (Fabio: "we should
serve the version that was sent"); the links list says when a file has a newer
version, and "Atualizar link" moves the link to it. Staff can turn any link off;
a client manages the links made on their device. One limit on downloads, 5 GB
per link per day, and none on the number of links per project (Fabio agreed);
new links are rate-limited per device.

**Why:** a supplier's quote should match the drawings they were sent, and the
office should know when a newer one exists rather than have the link change
under the supplier. Staff need a way to stop a link sent by mistake, since
clients have no account to do it from elsewhere. A link is a database row, so
counting them protects nothing; downloads cost transfer and can get the office's
Drive files throttled, so a single generous daily cap per link covers the real
risk, a leaked link.

---

## 2026-10-25 — A28, A32, section 10: reopening a stage emails the client

**Was:** only a stage completed (and the project completed) emailed the client;
reopening a stage emailed nobody and left the updates panel. The reopen
confirmation said nothing about email.

**Now:** reopening a stage is recorded (`stage_reopened`), emails the subscribed
clients ("A etapa 04 Anteprojeto foi reaberta.") and shows in the updates panel
as "Etapa reaberta" (Fabio, 25 Oct 2026). Its confirmation carries the same
"Clientes inscritos neste projeto serão notificados por e-mail." as completing's,
when someone is subscribed. An email names each stage whose state differs from
before the email's changes: completed then reopened (or reopened then completed
again) within the quiet period is still no news.

**Why:** a client who was told a stage was finished should hear that it is open
again; staff should know before confirming that the client will be told.

---

## 2026-10-25 — A25, section 12: versions from names, no document index

**Was:** versions needed a document index: `documents` and `document_revisions`
tables recording each logical document, its revisions (a sequence, an optional
label, the source, the published time) and a pointer to the current one, kept
up to date by the sync.

**Now:** versions are worked out from the file names each time a folder is
listed, which the page already does (A10): `Planta.pdf`, `Planta v2.pdf` and
`Planta v3.pdf` in one folder are one document, the highest version current,
with the same grouping rules as before (clear tokens only, within one folder,
clashes flagged). Nothing about files is stored, not even staff corrections
(join, split, choose current): a wrong grouping is fixed by renaming the file,
and the current version is always the highest. A version shows Drive's date
and no label (Fabio, 25 Oct 2026: "fine if we lose per-version
labels for now"). A file renamed out of its pattern, or moved to another
folder, leaves its group.

**Why:** came up while designing share links (future ideas): a link has to name
"this document, current version", and an index would have been a second copy of
what Drive's listing already says, with a sync to keep it right. Names give the
same answer for what offices do now, and a table of corrections wasn't worth
it either (Fabio): renaming the file fixes a wrong grouping. Given up: a label
per version, where each version came from, and choosing an older version as
current; an index can return if those are wanted.
A file with a new version shows "Atualizado" for 7 days from that version's
Drive date (Fabio: "only for a few days").

Also changed while building it (same day): section 12 said website uploads take
the next version number "under a lock". Uploads go from the browser straight to
Drive (A31), so a file only exists once its bytes arrive, and a lock while the
upload opens would not stop two uploads both becoming v3; holding the number
until then would mean storing a reservation, which this decision rules out. Now
the number is named when the upload opens, and two opened at the same moment
show as a clash for staff to rename, like any two files claiming one version.
Rare at a handful of offices, and nothing is lost.

And (Fabio, same day): only `v` numbers mark a version, "just use v1, v2, v3".
Section 12 also grouped the old app's `rev B` style (and the implementation
briefly `revisão 2`); a file named that way is now a document of its own,
renamed with `vN` if it should group. And a file shows its version from v2
("for v1 we can skip"): before, an unnumbered original displayed as v1; now v1
appears only in the file's list of versions.

---

## 2026-10-25 — Section 16: tours from the menus, no "?" buttons

**Was:** a "?" button started each area's tour: in the project page's staff bar
(the setup tour) and the painel's top bar (the painel tour). The account menus
and the phone's drawer gained the same item on 22 Oct 2026, so each tour had two
ways in.

**Now:** only the menus ("Ver o tour da página", "Ver o tour do painel"). An
archived project's menu doesn't offer its tour, as its staff bar didn't.

**Why:** Fabio, 25 Oct 2026: the "?" duplicated the menu item and took room in
bars that are tight on phones. The setup tour still starts by itself on a staff
member's first project page, so nobody depends on finding it.

---

## 2026-10-23 — Section 10, A28, A32: stages complete independently

**Was:** a project had one current stage. Staff moved it on with "Marcar etapa
como concluída" (the next stage became the one in progress) and back with
"Reabrir etapa"; the last stage's button completed the project, and "Reabrir
projeto" reopened it. The page showed the stages as a timeline with the current
one highlighted, the painel cards "Etapa atual" and its name, and emails said
"O projeto avançou para a etapa …".

**Now:** stages are independent and can be completed in any order (Fabio,
23 Oct 2026). Every stage has its own "Marcar como concluída", or "Reabrir
etapa" once completed, each after a confirmation. The page lists the stages as a
checklist under a thin bar of how many are completed and opens the first stage
still open; the painel cards say "X de Y etapas concluídas" with the same bar.
Emails and the updates panel name each stage completed (and still completed).
The project is completed by staff, not by its last stage (Fabio, 23 Oct 2026:
"just so we're sure before sending any emails or displaying as complete"):
completing the last open stage asks "Concluir o projeto?", and "Concluir
projeto" stays available while every stage is completed. Reopening a stage of a
completed project, or adding one, makes it active again.
`projects.current_position` stays in the database, unused, until the change is
confirmed; old `stage_advanced` events are kept but no longer shown or emailed.
For one release the previous `POST …/progress` route and the `current_position`
and `current_stage_title` fields keep working (computed from the completions),
for a tab still running the previous build during a deploy (A30).

**Why:** offices don't always work through stages in order (Fabio); one current
stage couldn't show two in progress, or a later one finished first.

---

## 2026-10-23 — A27, section 10: project page follow-ups

**Was:** a meeting had both a place and a video link field; "Adicionar etapa"
offered a list and, separately, a field for the office's own stage; only a
stage's number or head opened it; the painel's logo wasn't a link; the built-in
details had no total area.

**Now:** the meeting is "Presencial" or "On-line", and only that one's field
shows and is saved; "Adicionar etapa" is one list ending in "Etapa
personalizada…", which asks for the name; a closed stage opens on a click
anywhere on it (a shade darker under the mouse), an open one closes from its
head; the office's mark leads back to the projects from every painel screen
(ui/OfficeBrand, shared with the project pages); "Área total" is a built-in
detail (migration 0031, data only), listed after "Área construída".

**Why:** Fabio's review of the redesign (23 Oct 2026).

---

## 2026-10-23 — A24, A27, section 10: the project page on the painel's patterns

**Was:** the project page kept the prototype's look: a light grey page, the name
as "/casa **jardim**", a dark band across the current stage, a vertical
timeline of numbered circles, a ☀/☾ button, the details as a plain list with
"Cliente" one of the details staff could add, and a separate progress rail
("Etapa atual", "Reordenar etapas", "Voltar etapa", "Avançar para…"). The file
tools had their own search, a type and an order dropdown without direction.

**Now:** the painel's patterns (Fabio's 004.pdf): white page, the name in
capitals, grey rounded panels for each stage (the current one edged in the warm
colour, none of them a dark band), the stages as a numbered list that opens each
one, one rounded row per detail with the client's name from creation first
("Cliente" is no longer a detail to add, nor shown if saved before), the next
meeting in a grey panel with "Agendar reunião" in edit mode. The header has the
updates bell and the same menu as the painel (ui/HeaderMenu): "Modo escuro", and
for staff their initial, the tour and Sair. No progress rail: the current stage
has "Marcar etapa como concluída", which asks first and says the next stage
starts (the last one's completes the project); the stage finished last has
"Reabrir etapa"; a finished project's last stage has "Reabrir projeto";
"Reordenar etapas" sits beside "Adicionar etapa". The files' search and order
are the painel's (ui/SearchBox, ui/SelectField, ui/sort): one dropdown of order
and direction. The floating staff bar stays, its chosen side in the sketch's
lime. The design values (colours, corners, text sizes) are one file,
styles/tokens.css, loaded by the painel and the project page alike.

**Why:** Fabio's answers on the sketch (22–23 Oct 2026): the same patterns for
clients ("of course they shouldn't see photo inputs"); "remove client as an
option since that's populated from creation"; the theme switch "goes into the
menu same as the menu from painel. This should be a standard component"; remove
the section that advances a stage in favour of "mark step as complete" in the
current stage, with a dialog; search and sort "the same pattern as the painel
(one sort dropdown)", shared. **Set aside:** the sketch's full-width lime bar
(Fabio: keep the floating one, with some of the colour). **Kept for later:**
storing short type names per type waits for office-defined types (A27).

---

## 2026-10-22 — A24, A32, section 10: the painel redesign

**Was:** the card's pencil opened its menu; "Sem e-mail do cliente → Adicionar"
opened the whole "Projeto" dialog; the top bar showed "Conectado como …", a
☀/☾ theme button and "Sair"; completed projects were folded under a
"Concluídos" toggle; the list had no type filter; an office with no projects
saw "Novo projeto" in a toolbar and a dashed box.

**Now:** the card's menu opens from a "⋯" on the photo (same items). "Adicionar"
opens a small dialog with only the client's addresses (the "Projeto" dialog
still edits them too). The top bar has the sections in small capitals, "?" and
a round initial that opens an account menu: who is signed in, "Modo escuro" and
"Sair" (phones keep the ☰ drawer). "Em andamento" and "Concluídos" are both
open card grids under grey bars. Chips filter by project type, one per type in
use, shown only with two or more types. With no projects yet, the toolbar and
chips are hidden and an empty state with faded cards offers "Novo projeto".
Each first step's explanation sits behind an ⓘ instead of under its title.
After review the same day: a card lifts under the pointer (darker edge, soft
shadow) instead of turning charcoal; the sort is one dropdown of order and
direction together ("Nome: A–Z"), without the separate "Recentes ↓" button;
"Concluídos" shows its first 8 with "Ver todos (n)" (all of them while
searching); a search with no results offers "Limpar busca"; the painel tour is
also in the account menu and the phone's drawer; type chips wrap on phones
instead of scrolling sideways; no text below 11px (10px on phones), from one
set of text sizes in `global.css`. Then: each screen names itself in the browser tab
("Equipe · Configurações · Alinea"); a "Pular para o conteúdo" link for keyboard
users; screen readers hear how many projects a search or a chip leaves; the
search and the chosen type are kept in the address (`?q=…&type=…`); faded cards
while the list loads; the last update as "há 3 dias" (the date past a month,
the exact moment on hover), on one line so cards still line up; on phones,
something focused scrolls clear of the floating search. Also the project page's staff
bar (Painel, Ver como cliente / Editar, link, "?") is solid and inverted
instead of translucent, with a ring in the page's colour, because it blended
into the page (Fabio). Then Configurações, on Fabio's mockup: a
plain title, small-capitals tabs, each tab's content in a grey rounded panel
(the same one as Primeiros passos), rounded fields, pill buttons across the
staff app, and notices of things to do with an edge in the warm colour.

**Why:** Fabio's redesign of the painel (003.pdf, 22 Oct 2026), with his
answers: "⋯" rather than the design's "+" for the menu; the ⓘ instead of a "+"
for the step explanations ("+" reads as "add"); a dedicated dialog for client
emails "for ease"; the empty state because "we don't need the search bar on
top" before there are projects. The review changes are his answers to
suggestions (the charcoal hover is a lot across a grid; the direction button
was easy to misread; "I hate horizontal scroll on phones"). **Kept:** "?" for the painel tour (section 16),
although the design leaves it out. **Short names:** the chips show the
design's short names ("Interiores"), from the text catalogs for the four
built-in types (Fabio: "fine for now"); any other type shows its full name.
Storing a short name per type in the database waits for office-defined types
(A27).

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

## 2026-10-20 — A32: clients add themselves to a project's emails

**Was:** only staff listed the client's addresses (the Projeto dialog, and since
earlier today creation and edit mode).

**Now:** the project page offers "Novidades por e-mail". The address is listed at
once and gets a welcome email saying so, with a small "Não foi você?" link to stop
them. A client who had unsubscribed can sign up again this way; staff still can't.

**Why:** Fabio (20 Oct 2026) asked for clients to sign up themselves, and then for
no confirmation step: simpler for clients. **Considered and set aside:** a link to
confirm before listing (double opt-in). It stops anyone signing up a stranger, but
the welcome email lets that person leave with one click, and the device limit
caps how often it can happen; for a handful of offices that's proportionate.

---

## 2026-10-20 — A24, A32: the client's emails asked at creation, and missing ones flagged

**Was:** creation asked for the name, the client, the type and the stages; the
client's email addresses were added afterwards in the Projeto dialog, opened from
the card's menu. Nothing showed that a project had none.

**Now:** "Novo projeto" asks for them too, optionally. A project nobody receives
updates for (no address, or only unsubscribed ones) shows "Sem e-mail do
cliente" on its painel card, and a notice in the project page's edit mode; both
lead to adding them.

**Why:** Fabio (20 Oct 2026): the emails are an important part of the process,
and tucked in the settings they felt like an afterthought. Clients signing up
for the emails themselves is a separate change.

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
