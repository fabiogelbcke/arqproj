# Storage: our own, or more cloud providers?

**28 October 2026 · analysis for discussion, not decisions**

Companion to the [implementation plan](multi-tenant-implementation-plan.md)
(sections 8, 9 and 11; decisions A10, A31, A34) and
[`future-ideas.md`](future-ideas.md) ("Moving projects to another cloud
account"). Nothing here is decided. A choice goes into the
[decision register](multi-tenant-implementation-plan.md#2-decision-register) and the
[changelog](decision-changelog.md). Prices were checked on 28 Oct 2026; several
come from secondary sources, so confirm them on the provider's page.

## Where we are

Each office connects **its own Google Drive**. The project's stage folders live
there, and the page lists them live (A10). Two Google permissions are involved:

- **The office's grant is `drive.file`**: the app may change only files and
  folders it created itself (uploads through the site, sections from
  "Nova seção").
- **A separate reader identity** can see everything in the project folders.

This explains the limits staff run into: a file someone added through Drive can
be shown but not moved, renamed or hidden from the site (A34 says to do it in
Drive).

Why `drive.file` and not full Drive access: full access is a **restricted
scope**. Google then requires a yearly **CASA** security assessment by an
approved lab. Prices found:

- **Tier 2: about US$540 per app per year** (TAC Security, the lab Google
  points to). Other labs charge US$3,000–6,000.
- **Tier 3: about US$3,600–4,500 per year.**
- **Time:** 1–6 weeks.

So it's affordable in money, but it's a yearly process. It also means asking
offices for access to their **entire** Drive, which some will refuse.

## The three directions

| | A. Stay on Google Drive only | B. Add more providers | C. Our own storage |
| --- | --- | --- | --- |
| What it means | Today's model, polished | Dropbox, OneDrive/SharePoint, maybe Box, each behind the same storage contract | Files in a bucket we run (e.g. Cloudflare R2, Google Cloud Storage), uploaded through the site |
| Who holds the files | The office | The office | **Us** |
| Monthly cost to us | ~US$0 | ~US$0 | Storage + traffic (below) |
| Build cost | Small | ~2–4 weeks per provider, plus upkeep | ~2–3 weeks for the provider, more for the extras that become ours |
| Who it serves | Google Workspace / Gmail offices | Offices on Dropbox or Microsoft 365 | Any office, even with no cloud drive |
| Edit files outside the site | Yes, in Drive (the main draw) | Yes, in their tool | Only through the site (or a sync app we'd have to offer) |
| Site limits (`drive.file`-style) | Yes | Yes, similar on each | **None**: we can do anything with any file |

## B. More cloud providers

Our storage layer already has a provider contract (Google Drive and local
folders implement it), so each provider is an adapter plus its sign-in.

**Dropbox**
- Production approval is free, but Dropbox reviews an app only after **50 linked
  users**, and until then it's limited to 500 users.
- An "App folder" permission avoids broad access, but files must then live in
  `Apps/Unio/`. That clashes with an office's existing folder structure, the
  same tension as `drive.file`.
- Effort: ~2 weeks.

**OneDrive / SharePoint (Microsoft Graph)**
- Ordinary file reads and uploads aren't metered: no per-call fee, only
  throttling.
- Costs are in the variety: personal OneDrive vs SharePoint libraries, tenant
  admin consent in companies, and Microsoft's publisher verification.
- Effort: ~3 weeks, the most varied of the three.

**Box**: rare among small Brazilian architecture offices; not worth it without
demand.

**Ongoing cost:** every provider multiplies testing (A16's capability matrix per
account type), support ("my Dropbox disconnected") and the edge cases of moving,
versions and hidden files, which differ per provider.

**When it's worth it:** only when offices we want to sign actually use these.
Ask each pilot office what it uses (one question in onboarding). If Microsoft
365 is common among them, OneDrive comes first; Dropbox second.

## C. Our own storage

### Running costs

Assume an office keeps **50–150 GB of client deliverables** (renders, PDFs,
some models; working files stay elsewhere) and its clients download
**10–30 GB a month**.

| Provider | Storage (per GB/month) | Download traffic | 100 GB stored + 20 GB/month downloaded |
| --- | --- | --- | --- |
| **Cloudflare R2** | US$0.015 | **free** | **~US$1.50/month** |
| Backblaze B2 | ~US$0.007 | free up to 3× stored, then US$0.01/GB | ~US$0.70/month |
| Google Cloud Storage, São Paulo | US$0.035 | ~US$0.12/GB (more from São Paulo) | ~US$5.90/month |
| AWS S3 (US) | US$0.023 | ~US$0.09/GB after 100 GB free | ~US$2.30/month |

So even generous storage costs **US$1–6 per office per month**. That's small
against any plausible price (see [pricing-and-trials.md](pricing-and-trials.md)).
**R2 stands out**: free downloads matter because clients download, and an S3
API means the code isn't tied to Cloudflare. Pay attention to:

- Requests are cheap but not free: R2 charges US$4.50 per million writes.
- Storage grows forever unless there's a retention policy: archived projects,
  older versions.

### What we'd gain

- **No permission limits.** Move, rename, hide, version, make thumbnails: on
  every file, always. Most of the "do it in Drive" messages disappear.
- **Fewer incidents.** No Drive disconnections, expired grants or reconnect
  support. Section 22 lists "reconnect incidents" as a metric because they
  hurt.
- **Faster pages.** No live listing of Drive folders on each visit (A10's
  cost); we'd own the index.
- **Downloads without Cloud Run.** Signed links straight from the bucket, which
  also removes the download traffic cost in
  [pricing](pricing-and-trials.md#1b-per-office-as-it-is-today).
- **Something to sell.** Storage-based tiers, "keep finished projects forever"
  as a paid extra.
- **Offices with no Google account** can use Unio.

### What we'd take on

- **Custody of clients' files**:
  - LGPD obligations as their processor;
  - backups and restores;
  - deleting on request, and when an office leaves;
  - an export so an office can take everything with it.
- **Losing the main draw for many offices**: "it's just my Drive folder". Their
  team edits in Drive and the client page follows. With our own storage, files
  go up through the site only, unless we build a sync app (large and costly).
- **Two sources of truth if mixed**: an office that keeps working files in
  Drive and publishes copies to us ends up with copies out of date in one of
  the two places.
- **Moving existing projects in**: a migration tool (future-ideas already
  describes one).

## Recommendation to discuss

1. **Pilot: stay on Google Drive (A)**, and remove friction within `drive.file`:
   - sections, rename/hide and drag-to-move, done in PRs #150 and #152;
   - the Google Picker (A34's "later option"): staff pick a file added through
     Drive once, and the site can then change it. It avoids the CASA process
     and full-Drive access entirely.
2. **Ask every pilot office which cloud it uses.** Add providers (B) only for
   real demand: OneDrive if Microsoft 365 is common, then Dropbox.
3. **Prepare our own storage (C) as one more provider, not a replacement.** Use
   R2 behind the same storage contract, for:
   - offices without Google;
   - a "Unio storage" option in a paid tier.

   Build it when the first office without Google wants to sign, or when Drive
   incidents become the main support cost. Measure both during the pilot.
4. **Don't request full Drive access.** CASA is affordable (~US$540/year at
   Tier 2), but asking offices for their whole Drive costs more in trust than
   it gains, and the Picker covers the need.

## Sources

- CASA pricing: [TAC Security](https://tacsecurity.com/esof/), [Switchlabs comparison](https://www.switchlabs.dev/post/casa-tier-2-tier-3-security-review-providers-pricing-and-the-cheapest-option), [Leviathan Security](https://leviathansecurity.com/programs/google-casa-cloud-application-security-assessment), [Nango on Google's security review](https://nango.dev/docs/api-integrations/google-shared/google-security-review)
- Cloudflare R2: [Filebase summary](https://filebase.com/blog/cloudflare-r2-pricing-costs-savings-and-alternatives-in-2026/) (confirm on Cloudflare's pricing page)
- Backblaze B2: [egresscost.com](https://egresscost.com/backblaze-b2), [tech-insider comparison](https://tech-insider.org/backblaze-b2-vs-wasabi-vs-s3-2026/)
- Google Cloud Storage: [cloud.google.com/storage/pricing](https://cloud.google.com/storage/pricing)
- Dropbox production approval: [Dropbox forum (staff answer)](https://dropboxforum.com/discussions/101000014/production-approval-for-a-very-small-amount-of-users/503543/replies/503552), [DBX developer guide](https://www.dropbox.com/developers/reference/developer-guide)
- Microsoft Graph metering: [Microsoft Q&A](https://learn.microsoft.com/en-us/answers/questions/1332719/what-is-pricing-for-microsoft-graph-api-of-uploads)
