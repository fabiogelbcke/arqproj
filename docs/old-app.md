# The old app

The app outside `backend/` and `frontend/` (`app.py`, `arq/`, `run_local.py`,
`tools/`, `templates/`) is no longer in use; the rewrite replaces it. CI does not
test it. These instructions apply only when someone works on it.

## Testing

- When the current app's libraries change, update both `requirements.txt`
  (production deploys from it) and the `legacy` group in `pyproject.toml`.
- Run its complete suite with `.venv/bin/python -m tools.test_local`.
  Prepare the environment with `uv sync`, then `npm ci` and
  `npm run browsers:install` if needed. The runner uses isolated fictional data,
  ignores `.env`, and cleans up its temporary servers. It does not require the
  manual dataset reuse/regeneration question. Integration and browser servers
  use available ports rather than taking over a manually running server.
- Keep the browser fixture in `tools/test_local.py` consistent with generator
  changes. Browser tests must not silently default to a real-data server.
  Distinguish simulated behavior from live Google integration verification.

## Local data sources

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
