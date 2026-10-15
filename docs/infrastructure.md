# Infrastructure

What exists on Google Cloud and GitHub for the new app (`backend/` + `frontend/`),
and why. This is a record, not a script: deploys happen by merging on GitHub
(`staging` → staging; `main` → production at cutover). Change infrastructure
deliberately, with approval, and update this file in the same pull request.

The current site (Flask, `app.py`) keeps running as Cloud Run service `portal`
(alineaarquitetos.com), deployed from `main` by its own trigger. Nothing below
touches it.

Project `arq-proj`, region `us-east1`.

## Deploys

| Branch | Trigger | Does |
| --- | --- | --- |
| `staging` | Cloud Build `portal-staging-deploy` (runs as `portal-staging-deploy@`) | `deploy/staging/cloudbuild.yaml`: build `deploy/Dockerfile`, push, migrate `arqproj_staging`, provision, deploy `portal-staging` from `deploy/staging/service.yaml` |
| `main` | `rmgpgab-alinea-arquitetos-…` (existing; never delete) | Current site, buildpacks → `portal`. Switches to the new app only at cutover (slice 7) |

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

Databases: `arqproj_staging` (now), `arqproj_production` (at cutover).

Logins are Google identities (IAM database authentication), so there are no
database passwords in the app or in builds:

| Database login | Who | Role |
| --- | --- | --- |
| `portal-staging-deploy@arq-proj.iam` | the staging deploy (Cloud Build) and admin commands | Owner: runs migrations, owns the tables |
| `portal-staging@arq-proj.iam` | the staging app (Cloud Run) | Restricted runtime login; member of `arqproj_staging_app` only (granted by `backend.commands.provision`); tenant isolation applies |
| `postgres` | emergencies only | Built-in; password in Secret Manager `arqproj-db-postgres-password` |

One-time setup per database, run as `postgres` (Cloud SQL logins are not true
superusers, so the owner is given exactly what migrations need):

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

People who run admin commands against staging need **Service Account Token
Creator** on `portal-staging-deploy@` (granted: `arqdevproj@gmail.com`).

## Cloud Run `portal-staging`

Two containers: `app` (the image; port 8080) and `cloudsql` (Cloud SQL Auth
Proxy 2.26.2, `--auto-iam-authn`), which the app waits for. Public (no IAM
check), 0–2 instances, 1 CPU / 512 MiB for the app. Address:
`https://portal-staging-496714293251.us-east1.run.app`, mapped to office `alinea`.

## Images: Artifact Registry `portal`

`us-east1-docker.pkg.dev/arq-proj/portal/app:<commit>`. Cleanup policy keeps the
10 most recent images.

## Admin commands against staging

From a laptop with `brew install cloud-sql-proxy` and, once per machine,
`gcloud auth application-default login` (the proxy logs in with those credentials):

```bash
make tenant ENV=staging SLUG=alinea NAME="ALINEA ARQUITETOS" HOST=portal-staging-496714293251.us-east1.run.app
make staff ENV=staging TENANT=alinea EMAIL=you@example.com NAME=You ROLE=owner   # prints an invite link
make reset-link ENV=staging TENANT=alinea EMAIL=you@example.com
```

The Makefile starts the proxy as you, acting as `portal-staging-deploy@`, runs the
command and stops the proxy. Links print only in your terminal (never in logs).

## Costs (approximate, monthly)

Cloud SQL ~$9–10. Cloud Run, Cloud Build, Artifact Registry: within free tiers
at this scale. GitHub Actions: free (public repository).
