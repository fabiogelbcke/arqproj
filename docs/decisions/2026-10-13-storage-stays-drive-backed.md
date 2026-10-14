---
date: 2026-10-13
title: Keep files in the office's own Google Drive rather than storage we own
status: accepted
supersedes:
superseded_by:
deciders: [fabio]
tags: [storage, cost, drive]
---

## Context

Expanding the portal from one office to a product for several raised whether to
move files into storage we control (S3 or similar) and feed them through an
admin panel. Architecture files are large — renders, drawing sets, Revit models,
point clouds — and a single project can run to tens of GB. Target price is
R$50–100/month per office.

## Decision

Files stay in the office's own Google Drive. We read from it and write structure
into it; we never hold the bytes.

## Rejected alternatives

- **S3 or any storage we own.** Marginal storage cost per customer goes from zero
  to linear, which does not survive the price point. It also removes the main
  advantage — the architect keeps dragging files into a folder from Finder, where
  their studio already syncs — and puts us in custody of other firms' documents,
  with the backup, retention, deletion and LGPD obligations that follow.

## Consequences

- Storage cost stays effectively zero; egress is the only usage-scaling cost,
  since every client download is proxied through the app.
- We inherit Drive's constraints: free-Gmail 15 GB quota shared with Gmail and
  Photos, no way to prevent an owner deleting things on a personal My Drive, and
  `supportsAllDrives` required on every API call for Shared Drive support.
- Revisit only if offices ask to stop using Drive, or if free-Gmail quota turns
  out to block most of the market.
