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

## Testing

- Add or update automated tests for changed functionality.
- Run relevant tests after making changes.
- Run the production build and check for errors.
- Fix any test failures introduced by the changes.
- If tests cannot run, explain why.

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
  fictional data, and needs no Google account. Open
  `http://127.0.0.1:5000/casa-jardim`; `/painel` uses password `demo`.
- Treat “run the website with Google Drive data” as a request to run
  `.venv/bin/python run_local.py drive`. This still runs locally and reads
  the developer's private `.env`. Never deploy to satisfy this request.
- If the data source is unspecified, use test data and say so.
- Prepare `.venv` and install `requirements.txt` and `requirements-dev.txt`
  if needed, following README.md. Each developer supplies their own `.env`
  and credential file; never print credentials or passwords from those files.
- If Drive settings are missing, explain the missing setup from README.md.
  Never fall back to fake data while claiming to use Google Drive.
- Preserve existing servers. Use `--port 5001` for another instance and
  `--fake-drive-port 8766` for a second test-data instance when needed.
- Verify a real project page (not just `/healthz`) before claiming the data
  source works. Leave the server running and provide its localhost URL.

### Maintaining test data

- Keep `tools/fake_drive.py`, `demo.py`, and `run_local.py` tracked in Git.
  Generated documents and screenshots remain ignored.
- Whenever supported data structures, parsing rules, or features change,
  review and update `tools/fake_drive.py` with representative fictional
  examples needed to exercise the change, including relevant edge cases.
- Add or update automated tests for the new examples and behavior. If the
  existing fixtures already cover the change, explain that explicitly.
- Never copy real client documents, credentials, or private information
  into committed fixtures.

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
