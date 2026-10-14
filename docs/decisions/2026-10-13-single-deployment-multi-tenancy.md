---
date: 2026-10-13
title: One deployment, tenant resolved from the Host header
status: accepted
supersedes:
superseded_by:
deciders: [fabio]
tags: [multi-tenancy, infra]
---

## Context

Serving several offices could mean one deployment per office or a single
deployment that knows who is asking.

## Decision

A single deployment. The tenant is resolved from the `Host` header. Each office
gets a subdomain of our domain via its own Cloud Run domain mapping during the
pilot; a wildcard certificate via Certificate Manager with DNS authorization
replaces that at scale (~US$18/month), after which a new tenant is a database
row and nothing else.

## Rejected alternatives

- **Per-tenant deployments.** N sets of environment variables, N deploys, N
  things subtly out of date, no isolation benefit, and Cloud Run scales to zero
  so there is no cost argument for separating them.
- **Path-based URLs (`ourdomain.com/{studio}`).** Their clients would see our
  brand on their deliverable, and architects are brand-conscious.
- **Per-office custom domains as the default.** Per-tenant DNS, certificates and
  support. Offer later as a paid add-on.

## Consequences

- Tenant isolation becomes an application concern — every query needs a tenant
  scope, and a missing one is a cross-tenant data leak.
- The classic load-balancer managed certificate does not support wildcards, so
  the scale path specifically requires Certificate Manager with DNS
  authorization, not the simpler setup.
