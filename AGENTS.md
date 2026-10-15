# Project Instructions

## Git workflow

Before starting any new task:

1. Check the current Git status and branch.
2. Fetch the latest changes from origin.
3. If on main with a clean working tree, pull the latest
   main using fast-forward only.
4. If there are uncommitted changes, conflicts, or a
   different working branch, explain the situation
   instead of overwriting anything.
5. Never discard local changes without permission.

Before finishing:

- Check whether main has changed since work began.
- Warn about any conflicts or outdated code.
- Never push, merge, or deploy without explicit approval.

## Making changes

- Prefer small, focused changes.
- Follow existing code conventions.
- Avoid unnecessary refactoring.
- Explain significant architectural changes before making them.
- Keep safeguards proportional to the real risk in our setup (Cloud Run,
  Cloud SQL, a handful of offices, a small team). Prefer one simple check that
  covers the real failure over many checks for unusual configurations.

### Naming: tenant

An office using the product is a **tenant**. Code says "tenant" everywhere:
classes, functions, variables, database objects, settings, tests and code
comments (e.g. `Tenant`, `CurrentTenant`, `current_tenant`, `TenantOwned`,
`tenant_isolation`). Text users see says "escritório". Plans and docs for people
may say "office", meaning a tenant.

### Searching code

When Jev is available (for example in Claude Code or the Codex CLI), use it to
locate code by behaviour or to check a property across many files. Scope searches
to the relevant directories when known, then read the matching sections. Use
ordinary text search for exact names. Read enough surrounding code to make edits
safely. If Jev fails, report it.

### Runtime code vs one-off code (`backend/`)

Code the running app executes lives apart from code that runs once or only by
hand, so a reader of the app's code sees only what actually runs:

- **Runtime** (loaded by the app): `backend/app.py`, `settings.py`, `db/`,
  `tenancy/`, `web/`, and later feature packages.
- **Migrations** (`backend/migrations/`): Alembic versions, plus
  `snippets.py` (SQL to paste into new migrations) and `registry.py`.
  A migration writes its SQL out in full and never imports helpers from app
  code, so it replays exactly as it first ran.
- **Commands** (`backend/commands/`): run by a developer or a release step,
  e.g. local database setup, seeding, provisioning.

One-off code may import runtime code, never the reverse. A test fails if the app
loads anything from `backend/migrations/` or `backend/commands/`.

## Testing

- Add or update automated tests for changed functionality. Be thorough about
  behaviour: what the code does, its edge cases and failure paths, and the rules
  that later changes could break (for example "every office table is isolated").
- Do not test fixed values for their own sake: constants, default literals,
  exact copies of SQL or strings that merely restate the implementation. Such
  tests break on harmless edits and catch nothing. Test the behaviour that
  depends on them instead.
- A regression test for a bug should fail on the code before the fix; check it.
  A test of a safety rule should include a self-test showing it catches a
  violation, so it cannot silently stop working.
- Run relevant tests after making changes.
- Run the production build and check for errors.
- Fix any test failures introduced by the changes.
- If tests cannot run, explain why.
- For changes under `backend/`, also run `uv run pytest` and
  `uv run ruff check backend && uv run ruff format --check backend`.
- When the current app's libraries change, update both `requirements.txt`
  (production deploys from it) and the `legacy` group in `pyproject.toml`.
- Run the complete existing local suite with `.venv/bin/python -m tools.test_local`.
  Prepare the environment with `uv sync`, then `npm ci` and
  `npm run browsers:install` if needed. The runner uses isolated fictional data,
  ignores `.env`, and cleans up its temporary servers. It does not require the
  manual dataset reuse/regeneration question. Integration and browser servers
  use available ports rather than taking over a manually running server.
- Keep the browser fixture in `tools/test_local.py` consistent with generator
  changes. Browser tests must not silently default to a real-data server.
  Distinguish simulated behavior from live Google integration verification.

## Local development

- Use the project's documented development commands.
- Start the application locally when testing UI changes.
- Verify that the local server starts successfully.
- Provide the localhost URL to the user.
- If browser testing is available, verify the changed UI.
- Never claim that something was tested if it wasn't.

### Choosing the local data source

- Interpret intent in Portuguese or English; the phrases below are examples,
  not exact commands the user must memorize. Accept natural paraphrases and
  respond in the user's language.
- Requests such as “roda o site com dados de teste”, “abre com dados fictícios”,
  or “quero testar com os dados de exemplo” select test mode.
- Requests such as “roda com os dados do Google Drive”, “usa o meu .env”,
  or “abre localmente com os dados reais do Drive” select Drive mode.
  “Localmente” alone does not select a data source: both modes run locally.
- Treat “run the website locally with test data” as a request to run
  `.venv/bin/python run_local.py test`. This mode ignores `.env`, generates
  fictional data on first use, and needs no Google account. Follow the local-folder
  startup workflow below before launching an existing dataset. Open
  `http://127.0.0.1:5000/casa-jardim`; `/painel` uses password `demo`.
- Treat “run the website with Google Drive data” as a request to run
  `.venv/bin/python run_local.py drive`. This still runs locally and reads
  the developer's private `.env`. Never deploy to satisfy this request.
- Requests such as “roda com a conexão do Google Drive”, “testa o OAuth de
  verdade”, or “run with the Drive connection” select Drive OAuth mode:
  `.venv/bin/python run_local.py drive-oauth`. The site reads the projects
  folder created by connecting Google Drive in `/painel`, so the user signs in
  with Google themselves; before that the project list is empty. Requires the
  `OAUTH_*` settings in `.env` (README.md, “Google Drive connection (OAuth)”).
- If the data source is unspecified, use test data and say so.
- Prepare `.venv` with `uv sync` if needed, following README.md. Each developer supplies their own `.env`
  and credential file; never print credentials or passwords from those files.
- If Drive settings are missing, explain the missing setup from README.md.
  Never fall back to fake data while claiming to use Google Drive.
- Preserve existing servers. Use `--port 5001` for another instance and
  `--fake-drive-port 8766` for a second test-data instance when needed.
- Verify a real project page (not just `/healthz`) before claiming the data
  source works. Leave the server running and provide its localhost URL.

### Maintaining test data

- All newly generated demo and manual test examples must be in Brazilian
  Portuguese, including project descriptions, visible labels, stage notes,
  folder names, and document/image filenames. Use `SITE_LANG=pt` for previews.
- Keep generated examples fictional and preserve existing manual edits.
  Dedicated automated fixtures may explicitly use English only to test
  English-language support; manual/demo exports must always use Portuguese.

- Keep `tools/fake_drive.py`, `tools/export_sample.py`, `tools/local_data.py`,
  `tools/folder_drive.py`, `demo.py`, and `run_local.py` tracked in Git.
  Generated documents and screenshots remain ignored.
- Whenever supported data structures, parsing rules, or features change,
  review and update `tools/fake_drive.py` with representative fictional
  examples needed to exercise the change, including relevant edge cases.
- Add or update automated tests for the new examples and behavior. If the
  existing fixtures already cover the change, explain that explicitly.
- Never copy real client documents, credentials, or private information
  into committed fixtures.

### Local-folder test data workflow

Manual test mode serves editable `local-test-data/Projects/` files through
`tools/folder_drive.py`. Automated tests retain isolated in-memory fixtures
for Google-specific behavior and errors. Real Drive mode still uses `.env`.
The local folder is loaded at startup; restart with `--reuse-data` after
manual edits. Do not promise live file watching.

Follow these steps for each new manual test run:

1. Check whether a local test dataset exists. If none exists, generate the
   default fictional dataset automatically.
2. If a dataset exists, ask whether to reuse the existing files or regenerate
   the defaults, unless the user already specified their choice. Ask in the
   user's language, for example: “Usar os arquivos de teste existentes ou
   gerar novamente os exemplos padrão?” Wait for their answer; silence is
   not permission to regenerate.
3. Track the generator/fixture version used to create the dataset. If it has
   changed, explain that updated examples are available and recommend
   regeneration, especially when new features require new test cases.
4. Before any regeneration, back up the entire existing dataset to a unique
   location. Verify the backup succeeded before replacing files; if it fails,
   stop regeneration. Report the backup location and preserve earlier backups.
   Use the provided regeneration command; do not delete or overwrite files by hand.
5. Start the simulator using the selected folder, verify a project page, and
   provide both the editable folder path and the localhost URL.
6. Restarting the server alone must preserve manual file changes. Never
   regenerate or overwrite an existing dataset merely because the server
   restarted.

After the user's choice, launch with `.venv/bin/python run_local.py test
--reuse-data` or `--regenerate-data` (on one line). Without either flag the
launcher prompts in a terminal; in a noninteractive Codex task, ask the user
in conversation first. Missing datasets are generated automatically.
For regeneration without starting the site, use
`.venv/bin/python -m tools.local_data --regenerate` after authorization.
The default dataset and timestamped sibling backups are ignored by Git.
Use `--data-dir PATH` only for a dedicated test directory and ensure custom
locations and their backups are also excluded from commits.

Keep the generator as the source of the default dataset. For feature or data
format changes, review and update `tools/fake_drive.py`, the exporter
`tools/export_sample.py`, and the regeneration script `tools/local_data.py`
where needed, plus folder loading and tests. Never update only generated
files to add default coverage. The version is a hash of all three generator
files, so changes automatically mark existing datasets as outdated. Update
that version calculation if generation gains additional source files. Keep generated datasets and backups
out of Git. Automated tests must not prompt or modify the user's manual
dataset; they should create their own isolated fixtures.

## Decisions and shared context

Several people and agents work on this repository: Claude Code, Cowork, Codex,
and chat sessions with no repository attached. **The repository is the only thing
all of them can see.** A decision discussed in a chat is not recorded until it is
committed here.

- `docs/multi-tenant-implementation-plan.md` is the architecture and rollout
  plan, and **section 2 is the decision register** — the current position on
  every settled question, with IDs (A01, A02, …). Section 24 lists the decisions
  deliberately left open and who needs them. Read both before starting.
- **A change to a register entry must update the register and its affected tests
  before coding proceeds.** This is the plan's own rule; follow it.
- `docs/decision-changelog.md` records what each decision *was* and why it
  changed. The register cannot hold a rejected alternative, so without the
  changelog the same argument gets re-litigated. Before reopening a settled
  question, read its changelog entry; if there is none and you are changing a
  register row, add one. Newest at the top, never edit a past entry.
- `docs/infrastructure-cost-comparison.md` holds the hosting and provider cost
  analysis.
- Don't start a parallel planning or decision document. If something doesn't fit
  the plan's structure, say so rather than creating a second source of truth.
- Any copy of these documents outside the repository — for example in a claude.ai
  project — is a stale mirror. Read the repo.

## Code review (Codex)

Pull requests for the rewrite go into the `staging` branch. Codex reviews them on
GitHub (comment `@codex review`; marking a draft ready does not reliably trigger
it). When the review rounds end, the pull request goes to Fabio, who reviews and
merges.

How many rounds:

- Request another review after fixes while the last round found something that
  was fixed because it was serious or realistic for our setup. Declined or
  marginal findings do not count.
- Stop when a round brings only declined or marginal findings, or comes back
  clean (👍).
- A serious (P1) finding always gets one more round after its fix.
- Hard stop after 4 rounds. If real issues are still appearing, the pull request
  is too big or its design is unsettled: pause and discuss it with Fabio.
- Scale with the risk: security and data-isolation work follows the rules above;
  documentation-only or file-move pull requests get one review, and a
  documentation-only change after a clean review needs none.

- Fix serious findings and those realistic for our actual setup.
- Do not implement findings that are nitpicky, guard against configurations we
  never create, or would add code without real benefit. Reply on the comment
  explaining why, and list it in the pull request description.
- Reproduce a finding before fixing it.

### Pull request description

Start every rewrite pull request description with a **Plan** section linking the
documents that describe the work, so reviewers know what to check against:

- the step in `docs/rewrite-steps.md` (link to its heading), and the plan
  sections and register entries (A…, D…) it implements;
- `docs/decision-changelog.md` entries added or relied on;
- one line each: what the step called for, what was built, and what was
  deliberately left out or deferred, with the reason.

### Review guidelines

Whoever reviews (Codex, Claude or a person) reads the linked documents first and
checks the change against them, in addition to bugs:

- It does what its step lists, and nothing that belongs to a later step.
- It does not contradict a decision in the register (plan section 2) or a
  `D…` decision in `docs/rewrite-steps.md`. A change of decision must update the
  register, the changelog and their tests in the same pull request.
- Anything the plan requires for this area is present, unless the step's notes
  or the description record it as deferred.
- The step's notes in `docs/rewrite-steps.md` ("As built") match what the code
  actually does.

Report a mismatch with the plan as a finding like any other, citing the document.

## User-facing errors

Never surface backend or upstream error detail in the UI. No HTTP status codes,
no API response bodies, no exception text, no stack traces, no provider names —
not in a flash message, not on an error page, not in form validation. This
applies to the staff panel exactly as much as to client-facing pages.

Two reasons, and both matter: upstream bodies leak implementation detail, and
sometimes identifiers or fragments of credentials, to whoever is looking at the
screen; and they are meaningless to the reader (see Communication below — the
user may not be a software engineer).

Instead: a short message in the user's language saying what failed and what to do
next; where the user can fix it, say what to fix in their terms, not the API's;
log the full detail server-side at ERROR with route, operation and tenant; show a
short support/request ID that the log line also carries. Keep the detail on the
exception for logging and translate at the boundary where it becomes
user-visible.

Section 17 of the implementation plan holds the error-code and support-ID
conventions this belongs to.

Known violation to fix: the Drive connect flow under `/painel/drive` on the
`drive` branch flashes the raw upstream body, e.g.
`Drive API error 401: {"error": "invalid_client", ...}`. `DriveWriteError` should
keep that detail for the log and the route should flash a generic translated
string.

## Safety

- Never deploy directly to Google Cloud.
- Never modify production data during testing.
- Never expose or commit credentials or secrets.
- Do not modify infrastructure or database schemas
  without explicit approval.

## Communication

The user may not be a software engineer.

- Explain problems in simple language.
- Handle technical steps yourself whenever possible.
- Give clear instructions for manual steps.
- After each task, summarize what changed, what was
  tested, and how to view the result locally.
