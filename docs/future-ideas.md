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
- Research done 28 Oct 2026: [whatsapp-updates.md](whatsapp-updates.md)
  (costs, provider, whose number, consent, effort).
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

Agreed 25 Oct 2026 and moved to the plan: A37 and section 15. Still open: a
link that takes in a stage's future files.

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

- Built (25 Oct 2026, A36): after `make tenant` creates the office and its
  address, `make owner-link TENANT=…` prints a one-time owner signup link,
  valid for 7 days by default. The operator need not know the person's name or
  email. The recipient chooses their name, email and password and confirms the
  email with the existing 6-digit code before the account works. Fabio chose
  links we generate, not an open signup page.
- Still proposed: one command creating the office, its address and its owner
  link together; a signup page that also asks the office name clients see and a
  contact email (prefilled with theirs); then a short setup checklist in the
  panel: logo, connect Google Drive, invite the team.
- Why this shape: the app never needs permission to create offices or
  addresses (the registry stays read-only for it, as today); it already edits
  the office profile. Trade-off: the office cannot pick its own address; we
  agree it before running the command.
- Existing pieces: `make tenant` (`backend/commands/tenants.py`),
  `make owner-link` and `make staff ROLE=owner` (`backend/commands/staff.py`),
  `SettingsOfficePage.tsx`, `SettingsDrivePage.tsx`, `SettingsTeamPage.tsx`.
- Proposed 28 Oct 2026 (A38, PR for review): a one-time link with which the
  person creates their own office (name and address) and then their owner
  account (`/criar-escritorio`); the base for a public signup page.

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

## Sign in with Apple

- Raised by Fabio, 26 Oct 2026, after Google sign-in was planned (A38, section
  21). Not now: Google works on Apple devices, and Apple requires its sign-in
  only in App Store apps that offer other social logins.
- About 1-2 days on top of Google's hand-off between domains, plus:
  - a paid Apple Developer account, a Services ID, domain verification and a
    signing key whose client secret must be renewed at least every 6 months;
  - "Hide My Email": Apple may give a relay address that matches no invited
    account, so an account would have to be linked to its Apple ID on first use
    (a schema change and screens), and our sending domains registered with
    Apple for mail to reach relay addresses;
  - Apple returns by form POST (cookies behave differently on that hop) and
    gives the name only the first time.

