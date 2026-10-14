---
date: 2026-10-13
title: Project metadata in Postgres; Drive stays authoritative for files
status: accepted
supersedes:
superseded_by:
deciders: [fabio]
tags: [data-model, drive, postgres]
---

## Context

Project metadata — titles, descriptions, stage notes, ordering — lived in a
hand-edited text file in Drive, keyed by folder name. That was the original
fragility behind the duplicate-slug incident. An earlier draft of the plan
proposed moving it to Drive `appProperties` instead; that was reversed here.

Allowing edits in both the web UI and the Drive UI is the right product promise
and the classic way to build a consistency nightmare.

## Decision

**Drive is authoritative for files and for the existence of folders. Postgres is
authoritative for everything we invented** — metadata, ordering, notes, access.
Postgres never holds a copy of the file listing.

`appProperties` keeps one narrow job: write the project UUID onto the folder
once, so a folder can identify itself if the database is lost or it moves.
Write-once, never read in the hot path.

**Key projects and stages by `drive_folder_id`, never by name or path.** Stage
order becomes a `position` column rather than an `01 ` filename prefix.

## Rejected alternatives

- **Metadata in `appProperties`.** Proposed, then reversed: tight size limits,
  and stage notes and descriptions are free text that will outgrow them. A
  database exists anyway for tenants and auth, and once it does, metadata there
  costs nothing extra and buys ordering, filtering and cross-tenant admin views
  that Drive cannot give without N API calls.
- **Keeping the hand-edited text file.** The user's objection was direct: it is a
  fragile document format and clients or staff should not be editing it.
- **Mirroring file listings into Postgres.** Recreates the dual-truth problem the
  whole split exists to avoid.

## Consequences

- Renames and moves in Drive become no-ops, which covers most of what offices
  actually do. An architect can rename "Casa Jardim" to "Residência Jardim" and
  move it anywhere without breaking anything.
- What stays name-dependent is the remaining risk surface: version tokens
  (`rev B`, `v2`), the `_` hidden prefix, and sidecar preview images.
- When a folder ID stops resolving the project is orphaned. Do not guess and do
  not silently hide it — surface it in `/painel` as a warning.
