# Architecture project portal (POC)

A small Flask site that turns a Google Drive folder tree into a clean,
client-facing project page: title, description, project details, a stage
timeline with status, and the files for each stage. Drive stays private — the
server reads it with a service account and proxies files to clients.

## Drive conventions

```
Projects/                        ← root folder (shared with the service account)
  _site/logo.png                 ← optional firm logo (+ logo-dark.png for dark mode)
  Casa Jardim/                   ← one folder per project → /casa-jardim
    _project                     ← config doc (Google Doc, or _project.txt / .md)
    01 - Briefing/               ← stages, ordered by numeric prefix
      Program of needs.pdf
      Site photos/               ← subfolders become groups inside the stage
    03 - Schematic Design/
      _stage                     ← optional stage notes, shown under the stage heading
      Floor plans – rev A.pdf    ← versions of one file: the latest becomes the card,
      Floor plans – rev B.pdf       older ones go under "Previous versions"
      Model.skp
      Model.jpg                  ← same name + image = preview for Model.skp (no separate card)
    _internal/                   ← anything starting with "_" or "." is hidden
```

- **Stages.** Stage prefixes can be `01 - `, `1. `, `03_`, and so on. The number is shown and the rest becomes the label.
- **Stage status.** Stages with no files still appear. If `_project` has no `Current stage:`, the last stage with files is *in progress*, earlier stages are *completed* and later ones *upcoming*.
- **Versions.** Files are grouped when their names differ only by a trailing version token: `rev B`, `rev.3`, `revisão 2`, `R03`, `v2`, `_v02`, `(rev A)`. The file extension must match. The highest version wins; a file with no token counts as the oldest.
- **Previews.** An image (`.jpg`, `.png`, `.webp`) with exactly the same name as another file becomes that file's thumbnail. This is useful for `.skp`, `.dwg`, `.rvt` and other files Drive can't preview. Files without a preview get an icon for their type (CAD, 3D model, document, spreadsheet…).
- **New badge.** Files modified in the last `NEW_BADGE_DAYS` days (default 7) get a "New" badge, and stages show how many are new.
- **Downloads.** Google Docs, Sheets and Slides download as PDF. Other files are served as they are. PDFs and images open in the browser, and everything else downloads.
- **Shortcuts** are followed, so you can link a file into a stage without moving it.
- **Dates** are shown in `SITE_TIMEZONE` (default `America/Sao_Paulo`).

### Scheduled meeting

The project page shows a meeting card above the timeline. Add these fields to
the header of `_project` (before the description) to schedule it:

```text
Reunião agendada: 20/10/2026 14:00
Fim da reunião: 20/10/2026 15:00
Assunto da reunião: Apresentação do layout
Local da reunião: Online · Google Meet
Link da reunião: https://meet.google.com/your-meeting-code
```

Use `DD/MM/YYYY HH:MM` or ISO `YYYY-MM-DD HH:MM`; times use `SITE_TIMEZONE`
(default `America/Sao_Paulo`). ISO timestamps with an explicit offset are also
accepted. Only the start is required; the default duration is one hour. The
subject, location and HTTPS meeting link are optional. English aliases are
`Meeting start`, `Meeting end`, `Meeting title`, `Meeting location`, `Meeting link`.
Invalid settings are flagged in the dashboard. Missing or finished meetings
show “Não há reuniões agendadas” (localized to the site language).

“Adicionar ao Google Agenda” opens a prefilled event for the client to save in
their own calendar. This does not synchronize calendars, invite attendees or
create a Google Meet link automatically. “Apple Agenda” downloads an `.ics`
file with the same date, time, subject, location and meeting link for importing
into Apple Calendar. Both actions require the client to confirm saving the event.
If the date changes, the saved event
must also be updated by the client. Never put fictional meeting details in a
real client project.

### `_project` doc

```
Title: Casa Jardim
Client: Família Oliveira
Tipo de projeto: Projeto Arquitetônico
Location: Florianópolis, SC
Built area: 320 m²
Current stage: 3
Slug: casa-jardim-7k2p

Free-form description. Each line is a paragraph.
- Lines starting with "- " become bullets
```

- The header is the `Key: value` lines at the top. Blank lines between them are fine, and it ends at the first line of description text.
- `Title`, `Slug` and `Current stage` control behavior. Portuguese aliases work too: `Título`, `Etapa atual`, `Link`.
- **Every other key is shown to the client** as a project detail.
- Add `Tipo de projeto: Projeto Arquitetônico` or `Tipo de projeto: Projeto de Interiores` to the `_project` header to show the project type in the side panel. Existing projects need this line added to their Drive document; the site does not guess a type when it is absent.
- `Current stage` takes a number (`3`) or a stage name, and overrides the automatic status. `done` / `concluído` marks everything complete.
- **`Slug` must be lowercase letters, numbers and hyphens only**, e.g. `casa-nova-7k2p`. An invalid slug is never rewritten: the project is hidden from clients and flagged in the dashboard until it's fixed.
- If `Slug` is missing, the URL comes from the folder name, which is easy to guess. The folder ID also always works as a URL.
- Without a `_project` doc, the page still works and uses the folder name as the title.

### `_stage` notes (optional, one per stage folder)

Same format as `_project`: `Key: value` lines are shown as small facts, and the rest as text. For example:

```
Review meeting: 30 Sep 2026
Status: Awaiting client feedback

Rev B incorporates the comments from the concept review.
```

`_etapa` also works as the file name.

## Architect dashboard (`/painel`)

This page is for the architects, not clients. It lists every project with its current stage, a progress bar, the file count and how many files are new, and the last update. It has a **Copy** button for each client link and a **Refresh from Drive** button that skips the cache. It also flags problems:

- a missing `_project` doc;
- a link that's easy to guess (no `Slug:`);
- a `Current stage` that matches no stage folder;
- a project with no stage folders;
- loose files in a project folder, which aren't shown;
- two folders that resolve to the same link.

Mistakes never make a project vanish silently. **Every project folder is listed, even broken ones**, with a plain explanation:

- a slug already taken by another folder, which usually means a `_project` was copied. The copy is marked **Hidden** and is reachable only by its folder ID until it gets its own `Slug:`;
- a folder or stage the site can't open, e.g. a shortcut to a Drive that isn't shared;
- a `Slug:` / `Current stage:` line stranded below the description, which is ignored and never shown to clients;
- an invalid `Slug:`, meaning spaces, accents, capitals or other characters. The project is hidden until it's fixed;
- two project folders with the same name, or two stages with the same number;
- a repeated key;
- a config file that isn't UTF-8;
- more than one `_project` in a folder.

One bad folder never breaks the others.

The dashboard is enabled by setting `DASHBOARD_PASSWORD`. Without it, `/painel` returns 404. Sessions last 30 days, and changing the password signs everyone out. `deploy.sh` stores the password in Secret Manager, not as a plain env var.

## Try it without Google (demo)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
python run_local.py test  # → http://127.0.0.1:5000/casa-jardim and /painel (password: demo)
python -m unittest discover -s tests -v
```

The demo runs a fake Drive API locally, with real JWT signing and verification, loaded with sample data.

### Two local testing modes (including Codex)

Ask Codex **“run the website locally with test data”** or
**“run the website with Google Drive data”**. The root `AGENTS.md` maps these
requests to the commands below, checks startup, and provides the local URL.
You can also ask naturally in Portuguese, for example **“roda o site com dados
de teste”** or **“roda localmente com os dados do Google Drive”**. Codex follows
the intended data source, not an exact phrase, and replies in your language.

| Data source | Command | Setup |
| --- | --- | --- |
| Generated fictional data | `.venv/bin/python run_local.py test` | No Google credentials; ignores `.env` |
| Actual Google Drive | `.venv/bin/python run_local.py drive` | Your own `.env`, service-account credentials, and folder access |

Both run only on your computer. Drive mode uses read-only access and does not
deploy. Use `--port 5001` if port 5000 is already occupied; a second test-data
instance also needs `--fake-drive-port 8766`.

The generator `tools/fake_drive.py` and demo code are committed; generated
files are not. Keep fictional fixtures current when features or data formats
change. Each collaborator creates their own ignored `.env` and credentials.

### Editing and regenerating local test files

On first launch, test mode generates `local-test-data/Projects/`. Edit the
`_project.txt` and `_stage.txt` files, rename stages, or add your own test
PDFs and images using the same folder conventions as Drive. Restart the
server with **reuse** after edits; files are loaded at startup, not watched.

If the dataset already exists, the launcher asks whether to reuse it or
regenerate defaults. Codex asks in your language before choosing the flag:

```bash
.venv/bin/python run_local.py test --reuse-data
.venv/bin/python run_local.py test --regenerate-data
```

Regeneration creates a new dataset first, then preserves the old directory
intact as `local-test-data-backup-<timestamp>-<unique-id>/`. It prints that
backup path. If generation or backup fails, existing files are not replaced.
You can copy files out of a backup to recover manual edits. Backups are never
automatically removed. Dataset and backup directories are ignored by Git.

To generate or regenerate without starting the website:

```bash
.venv/bin/python -m tools.local_data
# Explicitly regenerate, with a backup if data already exists:
.venv/bin/python -m tools.local_data --regenerate
```

Both commands accept `--data-dir PATH` for a dedicated dataset directory
containing `Projects/`. Custom locations and backups must also stay out of Git.
The launcher detects changes to the generator, exporter, and regeneration
script using a saved fingerprint and recommends regeneration when outdated.
It never regenerates existing data without your choice. In noninteractive
runs, supply an explicit choice; missing input does not overwrite files.

The generator remains `tools/fake_drive.py`; exporting is handled by
`tools/export_sample.py`, and backup/version management by `tools/local_data.py`.
Keep these scripts and tests current when features require new samples.
Google Docs become text files and Slides become sample PDFs. A disk folder
cannot represent duplicate sibling names or Google shortcuts; these cases
remain covered by the in-memory automated fixtures. Symbolic links are skipped.
Use real Drive mode to verify actual Google-native exports and permissions.
`python demo.py` still runs the original in-memory demo when
`LOCAL_TEST_PROJECTS` is unset; automated tests do not use your editable dataset.

## Connect a real Drive (~15 min)

1. At <https://console.cloud.google.com>, create a project. Any Google account works, and billing isn't needed.
2. Under **APIs & Services → Library**, enable the **Google Drive API**.
3. Under **IAM & Admin → Service Accounts**, create a service account. It doesn't need any roles.
4. On the service account, go to **Keys → Add key → JSON**, download the file, and save it as `service-account.json` in this folder. It's gitignored.
5. In Drive, share the root `Projects` folder with the service account's email (`…@….iam.gserviceaccount.com`) as **Viewer**.
6. Copy the root folder's ID from its URL: `drive.google.com/drive/folders/<THIS_PART>`.
7. Configure and run:

```bash
python run_local.py drive  # → http://127.0.0.1:5000/<project-slug>
```

Before running, create `.env` in the project root with your local settings
(`.env.example` is optional and is not committed):

```dotenv
DRIVE_ROOT_FOLDER_ID=your-test-root-folder-id
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json
SITE_NAME="Your Studio"
SITE_LANG=en
SHOW_PROJECT_INDEX=1
DASHBOARD_PASSWORD="choose-a-local-test-password"
```

With `SHOW_PROJECT_INDEX=1`, open `http://127.0.0.1:5000/` to find project
links. The dashboard is at `/painel` and uses your configured password.
The root folder should contain project folders following the conventions above.
The launcher reads literal `KEY=value` lines, optional `export`, quotes, and
comments; it does not execute shell commands or expand variables such as `$HOME`.
Use an absolute credentials path. Never commit `.env` or credential files.

## Cloud Run

The app is set up for Cloud Run source deploys:

- `Procfile` runs gunicorn, and `.python-version` pins Python 3.13 (the google-24 builder only offers 3.13+).
- `.gcloudignore` keeps `.env`, `*.json` keys, tests and sample data out of the upload.
- **No key on Cloud Run.** When no key variable is set and `K_SERVICE` exists (Cloud Run sets it), the app gets tokens from the metadata server for the service account attached to the service. Deploy with `--service-account <the account Drive is shared with>`, and don't set `GOOGLE_APPLICATION_CREDENTIALS` there.
- Downloads are sent chunked (no `Content-Length`), so files larger than Cloud Run's 32 MiB limit on sized HTTP/1 responses still stream through.
- Pass the app settings (`DRIVE_ROOT_FOLDER_ID`, `SITE_NAME`, `SITE_LANG`, …) as env vars on the service.

## Environment

The header provides a light/dark mode toggle on every page. The initial theme
is light; the visitor's choice is saved in their browser and restored on later
visits. The logo background and glass surfaces adapt to both themes. An
available `_site/logo-dark.*` follows the selected theme; otherwise the regular
header logo is adjusted for contrast.

| Variable | |
|---|---|
| `DRIVE_ROOT_FOLDER_ID` | Root folder containing the project folders (required). |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to the service account JSON key. |
| `GOOGLE_SERVICE_ACCOUNT_KEY` | Alternatively, the key's JSON (raw or base64). Takes precedence. |
| `USE_METADATA_SERVER` | `1` to force metadata-server auth (automatic on Cloud Run). |
| `SITE_NAME` | Firm name shown in the header and footer. |
| `SITE_LANG` | `en` (default) or `pt` for the UI text. |
| `SITE_TIMEZONE` | Timezone for displayed dates (default `America/Sao_Paulo`). |
| `NEW_BADGE_DAYS` | Files changed within this many days get a "New" badge (default 7, `0` turns it off). |
| `DASHBOARD_PASSWORD` | Enables `/painel`. Unset means the dashboard is off. |
| `CACHE_TTL_SECONDS` | How long Drive listings are cached (default 60). Edits in Drive show up within this window. |
| `SHOW_PROJECT_INDEX` | `1` to list all projects on `/`. Keep it off when sharing with clients. |

## Security model

- Access control is the URL. Anyone with a project's link can see that project, so use slugs that are hard to guess for real clients (e.g. `casa-jardim-7k2p`). A per-project passcode is the natural next step.
- Files are only served if they appear on that project's page. A file ID from another project, a hidden `_` file, or the config doc returns 404.
- Pages send `noindex`, `Referrer-Policy: no-referrer` and `X-Frame-Options: DENY`. Proxied files are sent with `Content-Security-Policy: sandbox`, and SVGs are never shown inline.
- The service account has read-only scope (`drive.readonly`) and only sees what you've shared with it.

## Code map

```
app.py              routes, headers, streaming downloads
arq/google_auth.py  service-account JWT → access token (PyJWT, no Google SDK)
arq/drive.py        Drive v3 REST: list, read text, export, stream, thumbnails
arq/projects.py     folders → projects/stages/file groups, statuses, slugs
arq/config.py       _project doc parser
arq/cache.py        in-process TTL cache
arq/i18n.py         UI strings (en/pt) and formatting
tools/fake_drive.py fake Drive + token server for the demo and tests
```

## Known gaps and things to verify against real Drive

- **Thumbnails.** These fetch Drive's `thumbnailLink` using the service account's token. That's unverified against real Drive for private files. If it fails, cards fall back to the file-type badge.
- **Google-native export.** Drive caps exports at 10 MB, so a very large Google Slides deck may fail to download as PDF.
- **Caching** is per process and in memory. That's fine for one instance. Use Redis if you scale out.
- **Hosting.** Downloads stream through the app, so hosts with small response-size limits are out. Vercel, for example, caps function responses at 4.5 MB.
