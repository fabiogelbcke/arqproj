# Architecture project portal (POC)

A small Flask site that turns a Google Drive folder tree into a clean,
client-facing project page: title, description, project details, a stage
timeline with status, and the files for each stage. Drive stays private — the
server reads it with a service account and proxies files to clients.

## Drive conventions

```
Projects/                        ← root folder (shared with the service account)
  Casa Jardim/                   ← one folder per project → /casa-jardim
    _project                     ← config doc (Google Doc, or _project.txt / .md)
    01 - Briefing/               ← stages, ordered by numeric prefix
      Program of needs.pdf
      Site photos/               ← subfolders become groups inside the stage
    02 - Concept/
    03 - Schematic Design/
    _internal/                   ← anything starting with "_" or "." is hidden
```

- Stage prefixes can be `01 - `, `1. `, `03_`, and so on. The number is shown and the rest becomes the label.
- Google Docs, Sheets and Slides are downloaded as PDF. Other files are served as they are. PDFs and images open in the browser, and everything else downloads.
- Shortcuts are followed, so you can link a file into a stage without moving it.

### `_project` doc

```
Title: Casa Jardim
Client: Família Oliveira
Location: Florianópolis, SC
Built area: 320 m²
Current stage: 3
Slug: casa-jardim

Free-form description. Each line is a paragraph.
- Lines starting with "- " become bullets
```

- The header is `Key: value` lines up to the first blank line.
- `Title`, `Slug` and `Current stage` control behavior. Portuguese aliases work too: `Título`, `Etapa atual`, `Link`.
- **Every other key is shown to the client** as a project detail.
- `Current stage` takes a number (`3`) or a stage name. Earlier stages show as completed, later ones as upcoming. `done` / `concluído` marks everything complete.
- If `Slug` is missing, the URL comes from the folder name. The folder ID also always works as a URL.
- Without a `_project` doc, the page still works and uses the folder name as the title.

## Try it without Google (demo)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
python demo.py        # → http://127.0.0.1:5000/casa-jardim
python -m unittest discover -s tests -v
```

The demo runs a fake Drive API locally, with real JWT signing and verification, loaded with sample data.

## Connect a real Drive (~15 min)

1. At <https://console.cloud.google.com>, create a project. Any Google account works, and billing isn't needed.
2. Under **APIs & Services → Library**, enable the **Google Drive API**.
3. Under **IAM & Admin → Service Accounts**, create a service account. It doesn't need any roles.
4. On the service account, go to **Keys → Add key → JSON**, download the file, and save it as `service-account.json` in this folder. It's gitignored.
5. In Drive, share the root `Projects` folder with the service account's email (`…@….iam.gserviceaccount.com`) as **Viewer**.
6. Copy the root folder's ID from its URL: `drive.google.com/drive/folders/<THIS_PART>`.
7. Configure and run:

```bash
cp .env.example .env      # fill in DRIVE_ROOT_FOLDER_ID and SITE_NAME
set -a; source .env; set +a
python app.py             # → http://127.0.0.1:5000/<project-slug>
```

For production, use `gunicorn 'app:create_app()'`. On hosts without a filesystem for the key, put the key's JSON (raw or base64) in `GOOGLE_SERVICE_ACCOUNT_KEY`.

## Environment

| Variable | |
|---|---|
| `DRIVE_ROOT_FOLDER_ID` | Root folder containing the project folders (required). |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to the service account JSON key. |
| `GOOGLE_SERVICE_ACCOUNT_KEY` | Alternatively, the key's JSON (raw or base64). Takes precedence. |
| `SITE_NAME` | Firm name shown in the header and footer. |
| `SITE_LANG` | `en` (default) or `pt` for the UI text. |
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
- **Hosting.** Downloads stream through the app, so avoid hosts with small response-size limits for large CAD and model files. Serverless platforms often have them, so check before deploying there. Render, Fly or Cloud Run running gunicorn work well.
