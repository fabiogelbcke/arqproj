# Infrastructure

What exists on Google Cloud and GitHub for the new app (`backend/` + `frontend/`),
and why. This is a record, not a script: deploys happen by merging on GitHub
(`staging` → staging; `main` → production). Change infrastructure
deliberately, with approval, and update this file in the same pull request.

Production is the Cloud Run service `portal` (Alinea at `alinea.myunio.app`), which ran the
old Flask site (`app.py`) until the new app replaced it in place. Every project
on it was test data (Fabio, 17 Oct 2026), so nothing was migrated.

Project `arq-proj`, region `us-east1`.

## Deploys

| Branch | Trigger | Does |
| --- | --- | --- |
| `staging` | Cloud Build `portal-staging-deploy` (runs as `portal-staging-deploy@`) | `deploy/staging/cloudbuild.yaml`: build `deploy/Dockerfile`, push, migrate `arqproj_staging`, provision, deploy `portal-staging` from `deploy/staging/service.yaml` |
| `main` | `portal-production-deploy` (runs as `portal-production-deploy@`) | `deploy/production/cloudbuild.yaml`: **no build**. Finds the image staging built from exactly this code (tagged `tree-<git tree hash>` by the staging build once it has deployed), migrates `arqproj_production` with it and deploys it to `portal` by digest (plan section 19). Stops if staging never ran this code: merge `staging` into `main` and nothing else |
| `main` | `rmgpgab-alinea-arquitetos-…` (old site, buildpacks) | **Disabled**: it would deploy the old site over the new app. Delete once the new app has run a while |

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
| `portal-staging-operator@arq-proj.iam`, `portal-production-operator@arq-proj.iam` | the operator dashboard's lifecycle actions (A38), from the app | Member of `arqproj_<env>_operator` only (migration 0039's limited grants; added by `make operator-login`); never of `_app` |
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
| `portal-staging-operator@` | the operator login, through the service's second proxy | Cloud SQL client + instance user; `portal-staging@` may act as it (Token Creator on this account only) |
| `portal-staging@` | `portal-staging` service | Cloud SQL client + instance user (plus the current site's staging grants from earlier, unused by the new app) |

`portal-production-deploy@` and `portal-production@` have the same permissions
for production (the deploy account may act as `portal-production@`), plus
Secret Manager accessor on production's secrets for `portal-production@`.

People who run admin commands against staging or production need
**Service Account Token Creator** on that environment's deploy account
(granted on both to `arqdevproj@gmail.com`).

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
Scheduler calls on it and needs no office. Drive's return address is
`https://staging.myunio.app/api/drive/callback`.

## Google Drive on staging

No special logic: the Drive connection is made in staging's painel, choosing the
account and folder, as in production (plan section 9, "Staging and production").
Staging gets **its own OAuth client** ("Portal ALINEA (staging)", created in the
Cloud Console; redirect URIs below) so its write access never overlaps
production's, and reads as `portal-staging@`.
Set up 15 Oct 2026: client `496714293251-do3f1dtjsv5ae4l7559h3ghhg2ng34u5`
with redirect URIs `https://staging.myunio.app/api/drive/callback` (since 18 Oct 2026; the
`run.app` one before) and `http://127.0.0.1:5173/api/drive/callback` (local development: one shared
return address that forwards to the office that started, `backend/web/drive.py`).
Its secret is `portal-staging-oauth-client-secret`; staging's `APP_SECRET`
(signing and token encryption) is `portal-staging-app-secret`. Both are read
by `portal-staging@` and named in `deploy/staging/service.yaml`.

## Cloud Run `portal` (production)

Same shape as staging (`deploy/production/service.yaml`), 0–4 instances, running
as `portal-production@`. Addresses: `alinea.myunio.app`, office `alinea`'s primary
address since 25 Oct 2026 (Fabio; `alineaarquitetos.com` and `www.` redirect to it,
except the `/` home page, which every address shows), and `myunio.app`, all through
the load balancer below (A21), and
`https://portal-496714293251.us-east1.run.app`. Secrets:
`portal-production-app-secret` (its own), `portal-oauth-client-secret` and
`portal-resend-api-key` (production's, from the old site). PostHog (A39):
`POSTHOG_PROJECT_TOKEN` and `POSTHOG_HOST` as plain settings in
`deploy/production/service.yaml` (a project token is public by design); staging
has none. Drive uses the production OAuth client
`496714293251-ov1b5fd8gir885g9p51qsrbn9gbq6l7i`, whose redirect URIs must include
`https://myunio.app/api/drive/callback` (one shared return address that forwards to
the office that started); files are read as `portal-production@`. Emails send from `myunio.app`, Alinea's from
`alineaarquitetos.com`; both must be verified in the Resend account that owns
`portal-resend-api-key` (`myunio.app` wasn't until 22 Oct 2026, so its emails were
refused). Email alerts for errors and stopped maintenance passes: README, "Alerts".

**Right after the first production deploy:**
1. Cloud Scheduler job `portal-production-maintenance`, every 10 minutes as
   `portal-scheduler@` (command in README, "Client emails locally"); until it
   exists, nothing scans for new files or sends client emails in production.
2. The `myunio.app` domain mapping moves from `portal-staging` to `portal`.
3. The office: `make tenant ENV=production SLUG=alinea NAME="ALINEA ARQUITETOS"
   HOST=alineaarquitetos.com`, then `make staff ENV=production …`.

## Load balancer (A21)

Built 20 Oct 2026: a global external Application Load Balancer in front of
`portal`, at `34.149.133.166` (`portal-lb-ip`). Serverless NEG `portal-neg`
(us-east1), backend `portal-backend`, URL map `portal-lb`; HTTPS proxy
`portal-https` (port 443) with the certificate map `portal-cert-map`; port 80
only redirects to HTTPS (`portal-http-redirect`). Certificate Manager
`portal-cert` covers `*.myunio.app`, `myunio.app`, `alineaarquitetos.com` and
`www.alineaarquitetos.com`, proven by DNS records at GoDaddy (`_acme-challenge`
CNAMEs: `myunio-auth`, `alinea-auth`, `www-alinea-auth`). Every office on a
`myunio.app` subdomain reaches it through the `*.myunio.app` record; staging keeps
its own domain mapping (`staging.myunio.app`).

**Switching an address to it:** its DNS points at `34.149.133.166` (an A record;
the Cloud Run mapping's A/AAAA or `ghs.googlehosted.com` records go). Once every
production address goes through it, `portal` runs with `FORWARDED_HOPS=2` and
ingress `internal-and-cloud-load-balancing` (`deploy/production/service.yaml`).

## Images: Artifact Registry `portal`

`us-east1-docker.pkg.dev/arq-proj/portal/app:<commit>`. Cleanup policy keeps the
10 most recent images.

## Operator dashboard (A38)

`https://myunio.app/admin` (production) and `https://staging.myunio.app/admin`
(staging): Google sign-in for the emails in `OPERATOR_EMAILS`
(`deploy/*/service.yaml`). It signs in through each environment's Drive OAuth
client, whose redirect URIs include `https://<host>/api/auth/google/callback`
(added by Fabio, 26 Oct 2026). Adding an operator: add the email to
`OPERATOR_EMAILS` in that environment's `service.yaml` and deploy.

The lifecycle actions (create, owner link, suspend, delete) connect as the
environment's operator login, `portal-<env>-operator@arq-proj.iam`, through a
second Cloud SQL proxy in the service (`cloudsql-operator`, port 5433) that acts
as that account; `OPERATOR_DATABASE_URL` points at it. Without it the dashboard
hides the actions. The app refuses to start if that login is missing its group or
is the app's own. Set up 26 Oct 2026 (Fabio approved), per environment:

```bash
gcloud iam service-accounts create portal-staging-operator
gcloud projects add-iam-policy-binding arq-proj --condition=None \
  --member=serviceAccount:portal-staging-operator@arq-proj.iam.gserviceaccount.com --role=roles/cloudsql.client
gcloud projects add-iam-policy-binding arq-proj --condition=None \
  --member=serviceAccount:portal-staging-operator@arq-proj.iam.gserviceaccount.com --role=roles/cloudsql.instanceUser
gcloud iam service-accounts add-iam-policy-binding portal-staging-operator@arq-proj.iam.gserviceaccount.com \
  --member=serviceAccount:portal-staging@arq-proj.iam.gserviceaccount.com --role=roles/iam.serviceAccountTokenCreator
gcloud sql users create portal-staging-operator@arq-proj.iam --instance=arqproj-db --type=cloud_iam_service_account
make operator-login ENV=staging   # after migration 0039; safe to re-run
```

## Admin commands against staging

From a laptop with `brew install cloud-sql-proxy` and, once per machine,
`gcloud auth application-default login` (the proxy logs in with those credentials):

```bash
make tenant ENV=staging SLUG=alinea NAME="ALINEA ARQUITETOS" HOST=portal-staging-496714293251.us-east1.run.app
make tenant-host ENV=staging SLUG=alinea HOST=staging.myunio.app PRIMARY=1   # done 17 Oct 2026
make owner-link ENV=staging TENANT=alinea   # one-time owner signup link, valid for 7 days
make staff ENV=staging TENANT=alinea EMAIL=you@example.com NAME=You ROLE=owner   # invite a known person
make reset-link ENV=staging TENANT=alinea EMAIL=you@example.com
```

The Makefile starts the proxy as you, acting as `portal-staging-deploy@`, runs the
command and stops the proxy. Links print only in your terminal (never in logs).
`make owner-link` also works locally and with `ENV=production`; `DAYS=…` changes
its lifetime (default 7). The office and primary address must already exist.
The recipient supplies their own name, email and password, then confirms the
email with the code. Creating this link does not change the painel's shared
member link.

## Costs (approximate, monthly)

Cloud SQL ~$9–10. Cloud Run, Cloud Build, Artifact Registry: within free tiers
at this scale. GitHub Actions: free (public repository).
