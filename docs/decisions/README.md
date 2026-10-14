# Decisions

One file per decision. Read this index first, then open only the entries that
bear on what you are doing.

**Naming:** `YYYY-MM-DD-short-slug.md`. Dates, not sequence numbers — two people
creating `0007-...` independently collide, dated files don't.

**Adding one:** copy [`TEMPLATE.md`](TEMPLATE.md), fill it in, add a row below.

**Reversing one:** never edit a past entry to change what it says. Write a new
entry with `supersedes:` pointing at the old file, set the old entry's
`status: superseded` and its `superseded_by:`, and add the new row here. The
history of reversals is the useful part — it records what reasoning turned out
to be wrong, which is what stops the same argument being had twice.

| Date | Decision | Status |
|---|---|---|
| 2026-10-13 | [Keep files in the office's own Drive](2026-10-13-storage-stays-drive-backed.md) | accepted |
| 2026-10-13 | [The app creates its own delivery folder](2026-10-13-app-created-delivery-folder.md) | accepted |
| 2026-10-13 | [OAuth `drive.file` for writes, service account for reads](2026-10-13-oauth-writes-service-account-reads.md) | accepted |
| 2026-10-13 | [Move Cloud Run to us-east1 for domain mappings](2026-10-13-us-east1-for-domain-mapping.md) | accepted |
| 2026-10-13 | [One deployment, tenant from the `Host` header](2026-10-13-single-deployment-multi-tenancy.md) | accepted |
| 2026-10-13 | [Project metadata in Postgres, Drive authoritative for files](2026-10-13-metadata-in-postgres.md) | accepted |
| 2026-10-13 | [Client notifications triggered by the architect](2026-10-13-architect-triggered-notifications.md) | **superseded** |
| 2026-10-14 | [Client notifications fire automatically after a quiet window](2026-10-14-automatic-notifications-quiet-window.md) | accepted |
| 2026-10-14 | [Never surface backend error detail in the UI](2026-10-14-no-backend-errors-in-ui.md) | accepted |
| 2026-10-14 | [The repository is the source of truth for decisions](2026-10-14-repo-is-the-source-of-truth.md) | accepted |
