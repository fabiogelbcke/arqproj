---
date: 2026-10-13
title: Client notifications are triggered by the architect, not automatic
status: superseded
supersedes:
superseded_by: 2026-10-14-automatic-notifications-quiet-window.md
deciders: []
tags: [notifications, email]
---

## Context

Clients needed telling when new files arrive. The portal has no client identity
(access is an unguessable link), so there is no address to notify until someone
provides one.

## Decision

The architect types the client's email on the project form. Notification is then
an explicit act: a "publicar e avisar o cliente" checkbox on publish, plus a
standalone notify button for mid-stage deliveries.

## Rejected alternatives

- **Web push.** iOS Safari will not deliver push to a browser tab — the user must
  add the site to their Home Screen and open it from that icon, and the installed
  app and the browser are separate subscription contexts with no workaround. A
  homeowner visiting twice a month will not do that, so iOS clients would
  silently get nothing. Push also only reaches people who have already visited
  and opted in, so it cannot announce a first delivery. (This part of the
  reasoning survives into the superseding entry.)
- **Automatic detection.** Argued against on the grounds that one drawing set is
  dozens of file-created events, and that it needs persistent "already notified"
  state that does not exist today.

## Consequences

Superseded the following day. Recorded here because the reasoning it got wrong
is worth keeping: this entry was written as "decided" when it was a
recommendation, and the spam objection it rested on turned out to be solvable
with a quiet window rather than a button.
