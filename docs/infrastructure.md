# Infrastructure

What exists on Google Cloud and GitHub for the new app (`backend/` + `frontend/`),
and why. This is a record, not a script: deploys happen by merging on GitHub
(`staging` → staging; `main` → production). Change infrastructure
deliberately, with approval, and update this file in the same pull request.

The current site (Flask, `app.py`) keeps running as Cloud Run service `portal`
(alineaarquitetos.com), deployed from `main` by its own trigger, until Alinea
moves to `portal-production` (plan section 20). Nothing below touches it.

Project `arq-proj`, region `us-east1`.

## Deploys

| Branch | Trigger | Does |
| --- | --- | --- |
| `staging` | Cloud Build `portal-staging-deploy` (runs as `portal-staging-deploy@`) | `deploy/staging/cloudbuild.yaml`: build `deploy/Dockerfile`, push, migrate `arqproj_staging`, provision, deploy `portal-staging` from `deploy/staging/service.yaml` |
| `main` | `portal-production-deploy` (runs as `portal-production-deploy@`) | `deploy/production/cloudbuild.yaml`: the same steps against `arqproj_production` and `portal-production` |
| `main` | `rmgpgab-alinea-arquitetos-…` (existing; never delete until Alinea has moved) | Current site, buildpacks → `portal`, alongside |

A failed step stops the deploy; the running revision keeps serving. Settings
live in `deploy/staging/service.yaml`: change them in a pull request.

GitHub: `staging` accepts only pull requests whose checks pass
(`.github/workflows/ci.yml`: backend, frontend, e2e, image).

## Database: Cloud SQL `arqproj-db` (plan A16)

PostgreSQL 17, Enterprise edition, `db-f1-micro` (shared core), 10 GB SSD,
zonal. Daily backups at 06:00 UTC kept 7, deletion protection on. About
$9–10/month. Public IP with **no authorized networks**: reachable only through
the Cloud SQL connectors (the Auth Proxy), which require IAM permission.
`cloudsql.iam_authentication=on`.

Databases: `arqproj_staging` and `arqproj_production`, set up the same way.

Logins are Google identities (IAM database authentication), so there are no
database passwords in the app or in builds:

| Database login | Who | Role |
| --- | --- | --- |
| `portal-staging-deploy@arq-proj.iam` | the staging deploy (Cloud Build) and admin commands | Owner: runs migrations, owns the tables |
| `portal-staging@arq-proj.iam` | the staging app (Cloud Run) | Restricted runtime login; member of `arqproj_staging_app` only (granted by `backend.commands.provision`); tenant isolation applies |
| `portal-production-deploy@arq-proj.iam` | the production deploy and admin commands | Owner of `arqproj_production`'s tables |
| `portal-production@arq-proj.iam` | the production app | Restricted runtime login; member of `arqproj_production_app` only |
| `postgres` | emergencies only | Built-in; password in Secret Manager `arqproj-db-postgres-password` |

One-time setup per database, run as `postgres` (Cloud SQL logins are not true
superusers, so the owner is given exactly what migrations need); production is
the same with `production` in every name:

```sql
CREATE ROLE arqproj_staging_app NOLOGIN;                         -- group role migrations grant to
GRANT arqproj_staging_app TO "portal-staging-deploy@arq-proj.iam" WITH ADMIN OPTION;  -- provision adds the app login
GRANT USAGE, CREATE ON SCHEMA public TO "portal-staging-deploy@arq-proj.iam" WITH GRANT OPTION;
```

## Service accounts

| Account | Used by | Permissions |
| --- | --- | --- |
| `portal-staging-deploy@` | staging trigger; admin commands (impersonated) | Artifact Registry writer on `portal`; Cloud Run developer; Cloud SQL client + instance user; log writer; may act as `portal-staging@` |
| `portal-staging@` | `portal-staging` service | Cloud SQL client + instance user (plus the current site's staging grants from earlier, unused by the new app) |

`portal-production-deploy@` and `portal-production@` have the same permissions
for production (the deploy account may act as `portal-production@`), plus
Secret Manager accessor on production's secrets for `portal-production@`.

People who run admin commands against staging or production need **Service Account Token
Creator** on `portal-staging-deploy@` (granted: `arqdevproj@gmail.com`).

## Cloud Run `portal-staging`

Two containers: `app` (the image; port 8080) and `cloudsql` (Cloud SQL Auth
Proxy 2.26.2, `--auto-iam-authn`), which the app waits for. Public (no IAM
check), 0–2 instances, 1 CPU / 512 MiB for the app. Address:
`https://staging.myunio.app`, office `alinea`'s primary address (17 Oct 2026). It is
a Cloud Run domain mapping (free, managed certificate) on `myunio.app` (A33),
verified in Search Console for `arqdevproj@gmail.com`, with a CNAME `staging` →
`ghs.googlehosted.com` at GoDaddy. The service's own address,
`https://portal-staging-496714293251.us-east1.run.app`, stays an address of
`alinea` and redirects there, except `/internal/maintenance`, which Cloud
Scheduler calls on it and needs no office. Drive's return address is still the
`run.app` one; the redirect takes it to `staging.myunio.app`, where the sign-in
started.

## Google Drive on staging

No special logic: the Drive connection is made in staging's painel, choosing the
account and folder, as in production (plan section 9, "Staging and production").
Staging gets **its own OAuth client** ("Portal ALINEA (staging)", created in the
Cloud Console, redirect `https://portal-staging-496714293251.us-east1.run.app/…`)
so its write access never overlaps production's, and reads as `portal-staging@`.
Set up 15 Oct 2026: client `496714293251-do3f1dtjsv5ae4l7559h3ghhg2ng34u5`
with redirect URIs `https://portal-staging-496714293251.us-east1.run.app/api/drive/callback`
and `http://127.0.0.1:5173/api/drive/callback` (local development: one shared
return address that forwards to the office that started, `backend/web/drive.py`).
Its secret is `portal-staging-oauth-client-secret`; staging's `APP_SECRET`
(signing and token encryption) is `portal-staging-app-secret`. Both are read
by `portal-staging@` and named in `deploy/staging/service.yaml`.

## Cloud Run `portal-production`

Same shape as staging (`deploy/production/service.yaml`), 0–4 instances. Address
for now: `https://portal-production-496714293251.us-east1.run.app`; office
addresses go through the load balancer (plan A21) once it is built. Secrets:
`portal-production-app-secret` (its own), `portal-oauth-client-secret` and
`portal-resend-api-key` (production's, shared with the current site until Alinea
moves). Drive uses the production OAuth client
`496714293251-ov1b5fd8gir885g9p51qsrbn9gbq6l7i`, whose redirect URIs must include
`https://myunio.app/api/drive/callback` (one shared return address that forwards to
the office that started; it works once `myunio.app` reaches this service through
the load balancer); files are read as `portal-production@`. Emails send from `myunio.app` (verified
in Resend), Alinea's from `alineaarquitetos.com`.

## Images: Artifact Registry `portal`

`us-east1-docker.pkg.dev/arq-proj/portal/app:<commit>`. Cleanup policy keeps the
10 most recent images.

## Admin commands against staging

From a laptop with `brew install cloud-sql-proxy` and, once per machine,
`gcloud auth application-default login` (the proxy logs in with those credentials):

```bash
make tenant ENV=staging SLUG=alinea NAME="ALINEA ARQUITETOS" HOST=portal-staging-496714293251.us-east1.run.app
make tenant-host ENV=staging SLUG=alinea HOST=staging.myunio.app PRIMARY=1   # done 17 Oct 2026
make staff ENV=staging TENANT=alinea EMAIL=you@example.com NAME=You ROLE=owner   # prints an invite link
make reset-link ENV=staging TENANT=alinea EMAIL=you@example.com
```

The Makefile starts the proxy as you, acting as `portal-staging-deploy@`, runs the
command and stops the proxy. Links print only in your terminal (never in logs).

## Costs (approximate, monthly)

Cloud SQL ~$9–10. Cloud Run, Cloud Build, Artifact Registry: within free tiers
at this scale. GitHub Actions: free (public repository).
