---
date: 2026-10-13
title: OAuth drive.file for writes, service account for reads
status: accepted
supersedes:
superseded_by:
deciders: [fabio]
tags: [drive, oauth, auth, security]
---

## Context

The app needs to create folder structure in the office's Drive and to read the
files they drop in. The scope choice is consequential: `drive`, `drive.readonly`
and `drive.metadata*` are **restricted scopes**, requiring restricted-scope
verification, limited to three app categories, with a security assessment when
the data touches our servers — annual, slow and expensive. `drive.file` is
non-sensitive and needs only basic verification.

Two things were established by experiment in the OAuth Playground, with a
positive control rather than inferred from documentation:

1. **`drive.file` does not inherit.** Files the *user* drops into a folder the
   *app* created are invisible to the app. Listing such a folder returned only
   the app's own items while the Drive UI showed both.
2. **The app can share its own folder with a service account** —
   `permissions.create` succeeds — *but only while that folder contains nothing
   the app cannot see*. With a user-added file already inside, it fails with
   `appNotAuthorizedToChild`.

## Decision

Two credentials:

- **OAuth (`drive.file`)** for writes — creates the delivery folder and the
  project/stage structure.
- **Service account** for reads — the delivery folder is shared with it **at
  creation time, while empty**, so everything dropped in later is readable.

The architect grants once: they approve the OAuth consent and the share happens
behind it in the same request. No second prompt, no email to copy, no sharing
settings.

**Ordering invariant:** create the folder, then share it, before anything can be
added. Finding 2 above means the reverse order fails. There is a test asserting
the call order.

## Rejected alternatives

- **A restricted scope and OAuth for everything.** Verification cost, and worse
  failure behaviour (see below).
- **OAuth for both paths with `drive.file`.** Impossible — finding 1.
- **Asking the architect to share a folder with the service account manually.**
  An onboarding step and an email address to copy, for a non-technical user.

## Consequences

- Client-facing reads rest on the durable credential. A Drive share does not
  expire, while a refresh token is revoked by a password reset or an account
  tidy-up — so a lapsed OAuth grant blocks creating new projects but does not
  take client pages down. That is the better failure.
- A Workspace admin who blocks external sharing would break the automatic share.
  Untested; no pilot office will surface it if they are all on personal Gmail.
- Drive per-user rate limits apply to the single service-account identity, which
  argues for per-tenant service accounts at hundreds of offices, not dozens.
- The service account appears as a collaborator on the folder, so give it a
  human-readable name.
- The OAuth client itself can only be created in the Cloud console; there is no
  CLI or API path.
