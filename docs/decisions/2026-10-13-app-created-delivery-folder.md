---
date: 2026-10-13
title: The app creates its own delivery folder instead of reading existing working folders
status: accepted
supersedes:
superseded_by:
deciders: [fabio]
tags: [drive, product, onboarding]
---

## Context

Onboarding an office previously meant finding a folder ID and sharing a folder
by hand. The alternative is for the app to create a folder of its own on connect.

## Decision

On connect, the app creates its own folder in the office's Drive and builds the
project and stage structure inside it. Onboarding needs no folder sharing, no
folder IDs and no console.

## Rejected alternatives

- **Reading the office's existing working folders.** A client portal should not
  mirror working folders: they are full of half-finished files and internal
  markups. Putting a file in the delivery folder *is* the act of publishing it,
  and that curation step is the product.

## Consequences

- Makes the `drive.file` OAuth scope viable, which avoids Google's restricted-scope
  verification entirely.
- The boundary is a convention, not a lock: the folder is in their Drive and they
  can rename, move or trash it, and on a personal My Drive nothing can prevent
  that. Detection and recovery, not prevention.
- Duplication stays bounded only if the folder holds deliverables rather than
  source files. Nothing stops someone dragging in a 4 GB Revit model; the UI
  should push against it.
