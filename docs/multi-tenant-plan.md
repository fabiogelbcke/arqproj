# Multi-tenant product plan

Working plan for expanding the portal from one office (Alínea Studio
Arquitetura) to a product serving several architecture offices.

**This file holds the forward-looking plan: what is not yet decided, what is
not yet built, and the numbers behind it.** Decisions that have been made, and
the reasoning and rejected alternatives behind them, live in
[`decisions/`](decisions/README.md) — one file each. Where this document states
a decision, it links to the entry rather than restating the argument, so the two
cannot drift.

Canonical copy. Any copy elsewhere (for example in a claude.ai project) is a
mirror and may be stale.

## Goal and shape

- Productize the portal for multiple architecture offices, starting with a pilot
  of 3–5 **friendly offices** the team is in close contact with.
- Target price: **R$50–100/month per office**. Pilot offices should pay something
  real, even token — friends won't churn and won't complain, so money changing
  hands is the only signal that this solves a real problem.
- Onboarding is **manual/white-glove during the pilot**. That is the point of
  friendly testers. Zero-touch onboarding is the target before selling to
  strangers, not a pilot blocker.

## What is decided

| Area | Decision |
|---|---|
| Storage | [Stays in the office's own Drive](decisions/2026-10-13-storage-stays-drive-backed.md) |
| Folder layout | [The app creates its own delivery folder](decisions/2026-10-13-app-created-delivery-folder.md) |
| Drive auth | [OAuth `drive.file` writes, service account reads](decisions/2026-10-13-oauth-writes-service-account-reads.md) |
| Region / DNS | [us-east1, Cloud Run domain mapping](decisions/2026-10-13-us-east1-for-domain-mapping.md) |
| Multi-tenancy | [One deployment, tenant from `Host`](decisions/2026-10-13-single-deployment-multi-tenancy.md) |
| Data model | [Metadata in Postgres, Drive authoritative for files](decisions/2026-10-13-metadata-in-postgres.md) |
| Notifications | [Automatic, after a quiet window](decisions/2026-10-14-automatic-notifications-quiet-window.md) |
| Errors | [No backend detail in the UI](decisions/2026-10-14-no-backend-errors-in-ui.md) |

## Status

**Built and tested, not yet merged** (branch `drive`): `arq/oauth_drive.py`, the
`/painel/drive` routes, `templates/drive.html`, pt/en strings, 14 unit tests
covering the share-ordering invariant and refresh-token failure.

**Deploy plumbing still needed:** a GCS bucket for connection state plus an
`objectAdmin` binding, the OAuth client secret in Secret Manager with an
accessor binding, and `OAUTH_CLIENT_ID` / `OAUTH_REDIRECT_URI` /
`PORTAL_STATE_BUCKET` / `SERVICE_ACCOUNT_EMAIL` set on the service.
`GOOGLE_APPLICATION_CREDENTIALS` must never be set on Cloud Run — the app
authenticates through the metadata server there.

**Not built:** notifications, client access control, the database, subdomain
provisioning, quota monitoring.

## Protecting the folder structure from the Drive side

Clients never touch Drive — only the portal. The risk is **office staff**
renaming, moving, deleting or reorganising folders.

### Prevent

- Folder-ID keying and semantics out of names make renames, moves and
  renumbering no-ops. This covers most of what people actually do.
- **Make the panel the easy path.** Principle to state out loud: *Drive is for
  files, the panel is for structure.* Not a prohibition — just make structural
  work happen somewhere safer.
- **Shared Drive roles** are the only real lock, and only with Workspace: lower
  member roles can add files but not move or delete folders. Confirm the exact
  permission matrix before relying on specifics.
- **On a personal My Drive there is no equivalent.** The owner can do anything.
  On free-Gmail tenants we can only detect and recover.

### Detect

- **Poll `changes.list`** per tenant with a stored page token: a cheap delta of
  what moved, was renamed or was trashed. Minutes to notice a deleted stage
  folder instead of waiting for a client to complain.
- **Daily snapshot of the tree** (IDs, names, parents) as a diff basis only, so
  we can tell an office exactly what changed and when.
- **Asymmetric failure:** a missing stage renders as an empty stage for clients,
  never a 500; the office gets a loud warning in `/painel`. Graceful outward,
  loud inward.

### Recover

- **Deleted isn't gone.** Drive keeps trashed items ~30 days and the API can
  untrash. When the changes feed spots a trashed project folder, `/painel` offers
  *"Casa Jardim was moved to the trash on Tuesday — restore it?"* calling
  `files.update` with `trashed: false`. Probably the highest
  value-per-line-of-code item here: it turns the scariest support incident into
  self-service.
- **Filter `trashed` on every read**, or we serve files the office thinks they
  deleted — the opposite failure, and worse.
- Honest limit: someone can still empty their trash. Nothing fixes that.

### Build order

1. Folder-ID keys, semantics out of names (free with the database work)
2. Soft-fail rendering and loud dashboard warnings
3. `changes.list` polling with orphan/trashed warnings
4. Untrash button
5. Shared Drive role guidance in onboarding where available
6. Root folder named as a warning (*"Portal Clientes — não renomear"*) with a
   short README inside. Crude; genuinely effective with less technical users.

## Accounts and quota

- **Recommended path: Google Workspace + Shared Drive.** Org ownership, pooled
  storage, survives staff turnover, no personal/professional mixing, and the only
  way to restrict who can delete things.
- **Personal Drive allowed** for the pilot. Brazil is an informal market and
  small offices may legitimately run on bare Gmail; requiring Workspace adds cost
  and onboarding friction we don't want at R$50–100.
- A free Google account shares 15 GB across Gmail, Drive and Photos — one project
  can exhaust it. When it fills, uploads fail and the portal looks broken.
- Therefore, build from the start:
  - **Quota and account-type check at connect time** (`about.get`,
    `storageQuota`), shown before they commit, actively recommending Workspace.
    *(Implemented in the connect panel.)*
  - **Ongoing monitoring**, warning the office at ~80% full.
  - **Token health check per tenant** plus a "reconnect your Drive" flow.
- Shared Drives require `supportsAllDrives` on effectively every Drive API call
  plus a `driveId`. Pervasive but small — write it in from the start.

Watch for a false conclusion: three friendly offices with modest projects will
work fine on free Gmail for months, then the first paying stranger with a 40 GB
project breaks. The telemetry above is what prevents learning the wrong lesson.

## Database schema (first cut)

```
tenants            id, subdomain, name, status, plan, created_at
drive_connections  tenant_id, google_email, refresh_token (encrypted),
                   root_folder_id, drive_id (shared drives), scopes,
                   status, last_ok_at          ← token health lives here
office_users       id, tenant_id, email, role, auth
projects           id, tenant_id, drive_folder_id, slug, title, description,
                   client_email, notify_enabled, current_stage_override,
                   visibility, sort_order, created_at, updated_at
stages             id, project_id, drive_folder_id, name, position,
                   notes, status_override
branding           tenant_id, logo_file_id, locale, timezone, colours
client_access      id, project_id, email, token, expires_at, last_seen_at
notifications      id, project_id, stage_id, sent_at, to_email, kind
notify_state       project_id, announced_file_ids, pending (id → first_seen),
                   last_sent_at
```

`client_access` is for the auth work below — stub the table now rather than
migrating under pressure later. `notifications` is a log, so the panel can show
"last notified on …".

**File listings must not go in the database.** Files stay live from Drive behind
the existing TTL cache. `notify_state.announced_file_ids` is not a listing — it
is a set of IDs already announced, with no names, sizes or parents, and it is
never read to render a page.

## Subdomains

**Pilot (US$0):** one Cloud Run domain mapping per tenant, as already done for
`alineaarquitetos.com`.

```bash
gcloud beta run domain-mappings create --service portal --region us-east1 \
  --domain alinea.ourdomain.com
# then add the CNAME it prints to our zone
```

Two scripted commands per onboarding, which fits the white-glove pilot. Check the
per-project cap before relying on this past ~20 tenants; it is also still a
preview feature.

**At scale (~US$18/month):** wildcard, via **Certificate Manager with DNS
authorization** — the classic load-balancer managed certificate does *not*
support wildcards.

1. Reserve a static IP.
2. DNS: `*.ourdomain.com` and `ourdomain.com` both A → that IP.
3. Certificate Manager: DNS authorization on `ourdomain.com` → add the CNAME it
   returns (must be the only record at that name) → create a cert covering both
   the root and the wildcard.
4. Certificate map with two entries (root + wildcard) → attach to the HTTPS
   target proxy.
5. Load balancer: serverless NEG → Cloud Run `portal`.

After that a new tenant is a database row and nothing else. That is the moment to
switch, and it would also allow moving back to southamerica-east1.

## Client access control (required before second paying customer)

Today the security *is* the unguessable slug. Acceptable for one friendly office;
not acceptable as a product — a forwarded link means a competitor reading
someone's construction documents, and the office gets blamed for something we
built. Needs real client access control, e.g. per-project email magic links.
Bigger gap than storage.

Note the overlap with notifications: both want the client's email address, but
notifications only need the architect to type it, while auth needs a verified
round trip. Ship notifications first; they don't depend on auth. Notifications
then become the auth onramp — the email already goes to a verified address, so
the magic link can ride along in it.

## Cost

Approximate; confirm in the pricing calculator before committing, since regional
rates and free tiers move.

| | Pilot (3–5 offices) | Notes |
|---|---|---|
| Cloud Run | ~US$0 | pilot traffic trivial |
| Postgres | US$0–15 | free tier (Neon/Supabase) or smallest Cloud SQL |
| Load balancer | US$0 | not needed until per-tenant mappings stop scaling |
| Artifact Registry | ~US$1 | set an image cleanup policy or it creeps |
| Cloud Build | ~US$0 | free tier covers low build volume |
| Secret Manager | pennies | |
| GCS (connection + notify state) | pennies | one small JSON object |
| Cloud Scheduler | US$0 | 3 free jobs per account; one is enough |
| Email (ESP) | ~US$0 | free tiers cover pilot volume |
| **Egress** | **variable** | see below |

Roughly **US$5–20/month fixed** during the pilot against 5 × R$100 ≈ US$90
revenue. Adding the load balancer later takes fixed cost to ~US$30–40, still fine
at ten offices.

**Egress is the only cost that scales with usage.** Every file a client downloads
is proxied through the app, at order US$0.10–0.15/GB. An office whose clients
pull 50 GB in a month costs ~US$6 — about a third of a R$100 subscription. Not
fatal, but a studio sending a full drawing set to twenty clients will show up in
the bill.

Levers if it bites: edge-cache repeat downloads, or redirect clients straight to
Drive for the bytes instead of proxying. The second eliminates egress but gives
up the "files never leave the private Drive" property and the access control that
comes with proxying. Not deciding now — **instrument per-tenant bandwidth from
day one** so it isn't a surprise.

## Economics and what they imply

Ten offices at R$100 ≈ R$1,000/month (~US$180) against fixed costs of ~US$30–40.
Real money for a side project, irrelevant against a salary; only an interesting
business at 100+ offices, which is a sales problem rather than an engineering one.

The useful implication: **at this price the product must be near zero-touch once
out of pilot.** Two hours of onboarding calls spends two months of that
customer's revenue. One support thread a month makes them unprofitable. That is
what justifies the quota and token monitoring and the untrash button, and rules
out per-customer manual steps at scale. It is also the real argument for
automatic notifications over a button: a notification the architect has to
remember is a support thread waiting to happen.

Pricing shape: flat per office is right for the pilot, but avoid publicly
anchoring on "flat, unlimited" — a two-person studio with three projects and a
fifteen-person studio with forty aren't the same customer. Tier by active
projects later. Also check Brazilian payment rails: card subscriptions fail more
often there than in the US, and Pix is how people actually pay.

## Keep optional

Keep the `Drive` class as a real interface (`list_folders`, `list_files`,
`open_media`). Don't build a second backend now, but when someone turns up on
Dropbox — or owned storage is reconsidered — it should be contained rather than a
rewrite.

## Open questions

1. **What do the pilot offices actually run?** Workspace or free Gmail? How much
   Drive space is free? How big is their largest project folder? Three WhatsApp
   messages; settles more than further reasoning.
2. **Is anyone on Dropbox?** If so the connector abstraction matters sooner.
3. **Client auth design** — magic links vs passcodes vs accounts.
4. **Payment rail** — verify current recurring-Pix options.
5. **Shared Drive permission matrix** — confirm exactly which roles can and can't
   move or delete folders.
6. **Does the automatic service-account share survive a Workspace tenant** whose
   admin restricts external sharing? Untested; no pilot office will surface it if
   they're all on personal Gmail.
7. **Which ESP**, and whether the pilot sends from our domain or Alínea's.
8. **Is 45 minutes the right quiet window?** Guessed, not measured.
9. **Does a service account's `changes.list` include items in folders merely
   shared with it?** Determines whether notification detection can move off
   `files.list` polling.

## Deliberately deferred

Billing infrastructure, custom domains, owned storage, multi-region, tiered
pricing, self-serve onboarding, `changes.watch` webhooks, per-tenant email
sending domains, WhatsApp, per-stage notification granularity.
