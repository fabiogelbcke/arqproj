---
date: 2026-10-14
title: Never surface backend or upstream error detail in the UI
status: accepted
supersedes:
superseded_by:
deciders: [fabio]
tags: [ux, security, errors]
---

## Context

A failed Drive connect attempt flashed the raw upstream body to the panel:
`Drive API error 401: { "error": "invalid_client", ... }`. That body was
harmless, but the code path would print whatever Google returned.

## Decision

No HTTP status codes, response bodies, exception text, stack traces or provider
names in any user-facing surface — not in a flash message, not on an error page,
not in form validation. This applies to the architect's panel exactly as much as
to client-facing pages.

Instead: a short message in the user's language saying what failed and what to do
next; where the user can fix it, say what to fix in their terms; log the full
detail server-side at ERROR with route, operation and tenant; optionally show a
short opaque reference ID that the log line also carries.

Keep the detail on the exception for logging; translate at the boundary where it
becomes user-visible.

## Rejected alternatives

- **Showing the detail "just in the admin panel".** The panel's user is an
  architect, not an engineer, and upstream bodies can carry identifiers or
  credential fragments to whoever is looking at the screen.

## Consequences

- Known violation to fix: the Drive connect flow under `/painel/drive`.
  `DriveWriteError` should keep the detail for the log and the route should flash
  a generic translated string.
- Debugging moves to logs, which means the logs have to actually carry enough
  context. The reference ID is what makes a support message matchable to a log
  line without the user reading a stack trace.
- Recorded as a project-wide convention in `AGENTS.md`, not just as a fix.
