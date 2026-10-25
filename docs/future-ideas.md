# Future ideas

A running list of possibilities to explore, started 15 October 2026. Add ideas
here as they come up; they do not need a full specification or a delivery date.
This is not committed scope or a second implementation plan. When an idea is
selected for implementation, record the decision in the
[implementation plan](multi-tenant-implementation-plan.md) and any changed
decision in the [decision changelog](decision-changelog.md).

## Project-page templates and branding

- Let each office choose from different project-page templates and select a
  colour scheme that matches its branding.
- Basic branding is already in the implementation plan; this idea extends it
  with more layouts and customization choices.
- More advanced customization might be a premium feature. Which options belong
  in the base product versus a paid tier remains open.

## Multiple users and more granular permissions

- Support teams working within one office, with different responsibilities and
  access levels. The current plan already includes basic owner/member roles;
  this extends that model rather than postponing basic multi-user support.
- Contractors might only access assigned projects or upload into specific
  stages, without access to all project files.
- Financial documents, such as invoices and monetary proposals, may need
  restricted access even within the same office.
- Explore how restricted content appears: show a locked item or an indication
  that content is unavailable, versus hide it entirely. Decide what information
  can be shown without revealing confidential document names or details.
- Portal restrictions and permissions in the office's own Google Drive need to
  be considered together; hiding something in the portal does not remove direct
  Drive access.

## Organizing projects across a team

- Make it easier to find and organize projects when several architects work in
  the same office.
- Possibilities include tabs per architect, filters by responsible professional,
  and saved searches or default views such as "my projects".
- Keep organization separate from authorization: a default view can help someone
  focus on their work without necessarily restricting access to other projects.

## Usage metrics

- Record how offices use the features (for example uploads: how many, how
  large, from which screen) to see what people rely on and where limits such
  as the 100 MB upload cap (A31) should move.
- Raised by Fabio, 16 Oct 2026, while deciding uploads. Choose what to record,
  and keep clients' personal data out of it, before building.

## Searchable project themes and tags

- Let staff add `#tags` or keywords to a project's description so projects
  with related themes can be grouped, searched and filtered across the painel.
- Suggest existing terms while editing to avoid several spellings for the same
  theme (for example, natural materials or integrated spaces).
- Explore inline hashtags versus a separate keyword field. Keep the project
  description readable while making the themes reusable for search and filters.

## WhatsApp updates

- Add project-update notifications through WhatsApp alongside email.
- **Interest: potentially soon**, rather than a distant enhancement; timing is
  still undecided.
- Explore recipient preferences, batching, delivery costs and the provider's
  consent/template requirements before choosing an implementation.
- Decide whether recipients choose one channel or can receive both, and how to
  avoid unwanted duplicate notifications.


## What an office's own address shows at its root

- Today `/` shows Unio's public landing page on every address, an office's own
  domain included (`alineaarquitetos.com/`), because the page needs no office.
- On an office's address, `/` could instead belong to the office: options, from
  simplest, are a redirect to the office's own website (a new "site do
  escritório" setting), a redirect to the painel sign-in, or a simple page with
  the office's name and logo (later perhaps its public projects).
- `myunio.app` itself keeps the Unio landing page. Raised by Fabio, 17 Oct 2026;
  not urgent.


## Account settings in the phone menu

- The painel's ☰ drawer on phones (greeting, Modo escuro, Sair) is the natural
  home for a staff member's own account: change password, change email, maybe
  notification preferences. Fabio, 18 Oct 2026: "later".


## A file's link that survives renames

- "Enviar" on a file shares the page at that file by its stage, subfolder and
  name (`/casa-jardim?etapa=3&pasta=Renders&arquivo=Fachada.jpg`), since pages
  read Drive live and keep no file rows (A10); a renamed or moved file's link
  opens the page as usual, and where Drive holds two of the same name in one
  place, the link opens the first. With versions (A25) the page names a document
  by its clean name ("Planta.pdf" for `Planta v3.pdf`), so such a link opens the
  current version. Fabio, 18 Oct 2026:
  "we can wait for A25".

## Sharing files with a supplier by link

A client (or staff) picks files from the project and gets a link to send, for
example to a supplier for a quote. The supplier opens it and downloads the
files one by one or all at once as a zip, without an account. Discussed with
Fabio, 25 Oct 2026; what a link points to followed from A25's revision the same
day (versions from names, no document index).

Leaning towards (Fabio's answers, 25 Oct 2026):

- Both clients and staff can share. Staff see every link on the project (label,
  number of files, who made it, dates, downloads), but don't control them.
- A link can hold files from several stages. One panel, two ways in:
  "Compartilhar arquivos" above the stage list (every stage, collapsed, nothing
  ticked) and a button on each stage (that stage open with its files ticked,
  the others collapsed below so they can be added). Files hidden from the
  client never appear.
- The link stays up to date with the files rather than freezing what was sent.
- The sender chooses the expiry (7 days, 30 days, no expiry) and can add a
  password.
- At most 300 MB per link, counting every file in it, checked when the link is
  made; "Gerar link" is disabled above it ("O limite é de 300 MB por link.
  Desmarque alguns arquivos ou crie mais de um link."). We can raise it if
  people complain. At about $0.19/GB to Brazil, a full download costs about
  6 cents.
- Wording: "Compartilhar arquivos", an optional "Para quem?" label, "Cancelar"
  and "Gerar link"; then "Copiar link" and, on phones, the phone's own share
  sheet. Avoid "Exportar" (sounds like a format) and "Enviar" (reads as
  uploading, and is meant for the file link above).

A sketch of how it could work:

- A link is a stored random token (only its hash kept) with the office, project,
  label, creator, optional password (with a version that ends unlocks when it
  changes, as project pages do), expiry, deactivation and download count; and
  the files it holds. Creating one takes the file keys the page already handed
  out, so only what the sender can see can be shared.
- The supplier's page sits on the office's address (`/share/{token}`), branded,
  not indexed, sending no referrer. Downloads stream through the server as the
  page's do (plan section 15). The zip is built while it downloads, without
  compression (PDFs, images and CAD files barely shrink), so its size is known
  up front and the browser shows real progress; a folder per stage inside.
- Limits so a link can't run up the bill: a few new links a minute per device,
  about 20 active links a project, about 20 full downloads a day a link, and the
  office's monthly download bytes counted with an alert above a threshold.
- Possible slices: links with single-file downloads, the panel and the staff
  list; then the zip; then the password.

What a link points to:

- A link stores the Drive IDs of the files picked and checks them live on every
  visit, as file downloads already do. Renamed, moved to another stage or
  replaced in place (Drive's own versions): still in the link, with the current
  content. Hidden from the client or trashed: drops out, and comes back if
  undone. Deleted or moved out of the project, or the office reconnects another
  Drive: drops out.
- Versions (A25) are worked out from names on each listing, so a link serves
  the current version of the group holding one of its files: a new
  `Planta v3.pdf` replaces v2 in the link; if v3 is trashed, v2 again; older
  versions are never offered. So that the link keeps its group when the file
  first picked is trashed, it adds each version's ID it serves, and falls back
  to the clean name in the same folder.
- The supplier's page doesn't list files that are no longer available but says
  so ("2 arquivos compartilhados não estão mais disponíveis"; with none left,
  "Os arquivos deste link não estão mais disponíveis"); the staff list shows
  "3 de 5 disponíveis". With versions, each file shows its version and date, so
  a supplier who quoted on v2 can see the drawing changed.
- Files added to a stage after the link was made are not included; "include
  this stage's future files" could come later.
- Open: is there a case for a link that keeps the exact version that was sent
  (a quote's record) instead of the current one?

## Moving projects to another cloud account

- Switching an office's Drive account starts it fresh in the new account (the
  old account's files stay where they are; see the plan's section 9). A tool
  could later carry projects across: copy each project's files into the new
  account's folders, through the site, so the new grant can reach them. Fabio,
  18 Oct 2026: "We could also plan a migration tool for later".
- Wider (Fabio, 25 Oct 2026): move between any two storage accounts the portal
  supports, not only two Google Drive accounts, e.g. Google Drive to Dropbox,
  carrying the files along. That needs the other providers first (today the
  storage layer has Google Drive and local folders), and both accounts
  connected at once while the copy runs. Things to work out: large offices
  (a background job with progress), hidden files and versions keeping their
  meaning, and what clients see while it runs.

## Signup links for new offices

- Paused (20 Oct 2026) while UI work goes first. Fabio chose links we
  generate, not an open signup page.
- Proposed shape, not yet confirmed by Fabio: we run one command (e.g. `make
  office SLUG=… HOST=….myunio.app EMAIL=…`) that creates the office, its
  address and an owner, and prints a one-time link (7 days, like a staff
  invite). The link's page asks the first person for their name, the office
  name clients see, a contact email for clients (prefilled with theirs) and a
  password. Then a short setup checklist in the panel: logo, connect Google
  Drive, invite the team.
- Why this shape: the app never needs permission to create offices or
  addresses (the registry stays read-only for it, as today); it already edits
  the office profile and sets passwords from links. Trade-off: the office
  cannot pick its own address; we agree it before running the command.
- Existing pieces: `make tenant` (`backend/commands/tenants.py`), `make staff
  ROLE=owner` (`backend/commands/staff.py`, prints an invite link),
  `SettingsOfficePage.tsx`, `SettingsDrivePage.tsx`, `SettingsTeamPage.tsx`.

## Guided tours and an example project

- Agreed and designed: see the plan, section 16, "Onboarding help". Kept here
  as a reminder that Fabio's partners may still weigh in.

- Agreed to try (Fabio, 18 Oct 2026; may be rediscussed with his partners): an
  example project that is static (fictional data in the browser, nothing in
  the office's Drive, nothing saved), offered in Primeiros passos, with a tour
  that shows where things appear (files, description, details…) every time it
  opens, skippable. The first real project page has its own tour, focused on
  setting the project up, once per account (built: Driver.js,
  `users.tour_seen_at`, the account menu replays it).
