# Handoff: the `drive` branch

Scratch note for picking this branch up in Claude Code. **Delete this file when
the branch merges.** Written 14 Oct 2026.

## What this branch is

Single-tenant Google Drive OAuth connect flow, built to put the UI in front of
people for feedback — not to be the multi-tenant architecture. It is one commit
(`30a020a`) on top of `f67c3b1`, local only, never pushed.

```
arq/oauth_drive.py          ~400 lines: OAuthConfig, DriveWriter, Connection,
                            FileStateStore / GcsStateStore
app.py                      7 routes under /painel/drive, behind the existing
                            @dashboard_login_required
templates/drive.html        the panel
arq/i18n.py                 ~35 drive.* keys per language, appended in a
                            delimited block so the feature can be removed in
                            one edit
tests/test_oauth_drive.py   14 tests, a FakeSession, all passing
arq/google_auth.py          scope parameterised so the same code can mint GCS
                            tokens (backwards compatible, default unchanged)
```

## First decision: this branch is behind main

`main` has moved on four commits since `drive` was cut, including app code the
OAuth work hasn't seen (`arq/stages.py`, `static/file-search.js`,
`static/notifications.js`, `static/stage-collapse.js`, template and i18n
changes). Merging `main` into `drive` is almost clean:

- **one conflict, `.gitignore`** — both branches appended lines; take both
- `arq/i18n.py` auto-merges, but both branches edited it. Check the `drive.*`
  keys still match across `en` and `pt` afterwards

Do that merge before building anything else here, or the divergence only grows.

## Immediate blocker

Local connect fails with:

```
Drive API error 401: {"error": "invalid_client", "error_description": "The provided client secret is invalid."}
```

Google matched the client ID but the secret didn't verify. In order of
likelihood:

1. ID and secret from different clients — if the client was created more than
   once, or the secret regenerated, copy both from the same row in Credentials
2. Stray characters in `.env` — quotes, trailing space, or a line break from a
   wrapped paste. `echo ${#OAUTH_CLIENT_SECRET}` should be 35 for a `GOCSPX-`
   secret; 0 means the export didn't happen, 37 means quotes
3. Stale shell — `source .env` doesn't re-run itself

## Running it

```bash
set -a; source .env; set +a
python app.py          # http://127.0.0.1:5000/painel/drive
python -m unittest tests.test_oauth_drive -q
```

`.env` keys and their state as of this note:

| Key | |
|---|---|
| `OAUTH_CLIENT_ID` | set |
| `OAUTH_CLIENT_SECRET` | set, but rejected — see above |
| `OAUTH_REDIRECT_URI` | set |
| `SERVICE_ACCOUNT_EMAIL` | **empty** — the automatic share is skipped without it, so the read path stays empty and the panel's "visible to the site" list stays blank. `gcloud run services describe portal --region us-east1 --format='value(spec.template.spec.serviceAccountName)'` |
| `PORTAL_STATE_BUCKET` | empty, correct locally — falls back to `.drive-connection.json` (gitignored) |

Redirect URIs registered on the OAuth client:
`http://127.0.0.1:5000/painel/drive/callback` and
`https://alineaarquitetos.com/painel/drive/callback`. Use `127.0.0.1`, not
`localhost` — Google treats them as different strings.

## Don't break this

`Connection.setup_delivery_folder` creates the folder and shares it with the
service account **while the folder is still empty**. That order is not
stylistic: `permissions.create` fails with `appNotAuthorizedToChild` once the
folder holds a file the OAuth app didn't create. `tests/test_oauth_drive.py`
asserts the call order; if that test starts failing, the bug is the reordering,
not the test. Full reasoning in section 9 of
`docs/multi-tenant-implementation-plan.md` on `main`.

The other protected invariant: a rejected token refresh raises `NotConnected`
rather than failing open.

## Known defect to fix here

The connect flow flashes raw upstream error bodies to the panel — the 401 above
is what the architect would see. `DriveWriteError` should keep the detail for the
log and the route should flash a generic translated string. The rule is in
`AGENTS.md` on `main` under "User-facing errors"; conventions in section 17 of
the plan.

## Before connecting any real office

External OAuth apps left in **Testing** can have **seven-day refresh-token
expiry** for Drive. The architect's connection would break weekly. Publish the
consent screen first. Fabio has this.

## Deploy, when it's worth deploying

1. `gcloud storage buckets create gs://arq-proj-portal-state --location=us-east1 --uniform-bucket-level-access`, plus `roles/storage.objectAdmin` for the runtime service account
2. client secret into Secret Manager as `portal-oauth-client-secret`, plus an accessor binding — never a plain env var
3. `gcloud run services update portal` with `OAUTH_CLIENT_ID`, `OAUTH_REDIRECT_URI`, `PORTAL_STATE_BUCKET`, `SERVICE_ACCOUNT_EMAIL` and the secret
4. never set `GOOGLE_APPLICATION_CREDENTIALS` on Cloud Run — the app uses the metadata server there

`deploy.sh` is gitignored; its env whitelist already includes the four variables
and deliberately excludes the secret.

## Out of scope on this branch

Multi-tenancy, the FastAPI rewrite (A01/A18), Postgres, notifications. Those
belong to `docs/multi-tenant-implementation-plan.md`, not here. This branch
exists to find out whether architects like the flow.

Decisions and their history live on `main`: section 2 of the plan is the
register, section 24 the open questions, `docs/decision-changelog.md` the record
of what changed and why, and `AGENTS.md` the protocol. A `docs/decisions/` folder
was created and removed on 14 Oct because it duplicated the register — don't
recreate it.
