---
date: 2026-10-14
title: Client notifications fire automatically after a quiet window
status: accepted
supersedes: 2026-10-13-architect-triggered-notifications.md
superseded_by:
deciders: [fabio]
tags: [notifications, email, drive]
---

## Context

The previous entry had the architect pressing a button to notify the client. The
objection that overturned it: **the whole promise is that the architect keeps
working in Drive.** A notify button means they finish in Drive and then go to a
second website to tell the client, so the one step the client actually
experiences is the one most likely to be forgotten. Notifications that depend on
remembering to send them are worse than none, because the office then believes
the client was told.

Email remains the channel, for the reasons in the superseded entry.

## Decision

Detection is automatic, debounced by a quiet window.

**Detection polls `files.list`.** The service account can already list every
delivery folder — that is the live read path — so detection needs no new Drive
capability. A scheduled job lists each project's non-hidden stage folders,
filters `trashed`, and compares file IDs against a stored set already announced.

**The quiet window.** Un-announced IDs join a pending batch with a first-seen
timestamp. Send only when nothing new has appeared for `quiet_period` (default
45 minutes), with a max hold of about 2 hours so a continuous all-afternoon
upload still notifies the same day. One email per delivery session, not per file.

**The `_` prefix is the control surface.** The app already hides `_`-prefixed
folders from clients, so anything under one is excluded from detection. "Don't
tell them yet" is a folder name the architect already uses in Drive. Moving a
folder out of `_` is the publish gesture and fires the notification. No button.

**Email content is deliberately contentless:** "Novos arquivos de {office} —
{project}. Clique para ver." Project and stage name, no file list.

Suppression rules: do not fire on project setup (require `client_email` and
published); key by file ID so renames and moves are no-ops; filter `trashed`;
per-project off switch plus an unsubscribe link.

## Rejected alternatives

- **`changes.watch` push webhooks.** The notification body is always empty
  (`Content-Length: 0`); the state is coarse (`add`, `update`, `trash`, `change`)
  with no filename or path, so you still call `changes.list` to learn what
  happened. Channels expire — max 1 day for a `files` watch, 1 week for
  `changes`, 1 hour by default — and there is no automatic renewal, so a
  scheduled job is needed anyway just to keep the watch alive.
- **`files.watch` on the delivery folder.** Google documents it against a single
  file and does not commit to child changes firing on the parent.
- **`changes.list` instead of `files.list`.** More efficient, and planned anyway
  for structure protection, but it rests on an untested assumption: that items in
  a folder merely *shared with* a service account appear in that account's change
  feed. `files.list` is known to work because the live site uses it. Switch later.
- **A notify button.** See Context.

## Consequences

- The quiet window doubles as an undo window: upload to the wrong project, notice
  within 45 minutes, remove the files, and the client is never told. That argues
  for erring longer rather than shorter.
- It ends "scales to zero" — a 10-minute scheduler wakes Cloud Run around the
  clock. Free-tier noise at pilot scale; widen the interval overnight if it ever
  matters.
- Needs persistent state (`announced_ids`, the pending batch, `last_sent_at`).
  Single-tenant: the GCS state object. Multi-tenant: a `notify_state` table.
- 45 minutes is a guess, not a measurement. Ask an office how long a typical
  upload session runs.
- None of this needs the Google Cloud console, so it was buildable while console
  access was blocked.
