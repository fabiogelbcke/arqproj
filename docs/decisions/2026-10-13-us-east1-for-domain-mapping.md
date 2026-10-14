---
date: 2026-10-13
title: Move Cloud Run to us-east1 so domain mappings work
status: accepted
supersedes:
superseded_by:
deciders: [fabio]
tags: [infra, dns, cost, region]
---

## Context

`alineaarquitetos.com` was registered at GoDaddy and needed to point at the
portal. Cloud Run domain mappings are not supported in southamerica-east1, where
the service was running. The explicit constraint was the cheapest option.

## Decision

Move the `portal` service to us-east1 and use a Cloud Run domain mapping, with
the apex A/AAAA records and a `www` CNAME at GoDaddy. Cost: US$0.

## Rejected alternatives

- **An external HTTPS load balancer** in southamerica-east1. Works, supports
  wildcards later, but roughly US$18/month in fixed cost for one office.
- **Firebase Hosting** as a front end. Also free, but blocked at the time by a
  Google account 2-step-verification problem ("we couldn't verify it's you"),
  and it adds a second hosting product to reason about.

## Consequences

- Latency to Brazilian clients is worse than a São Paulo region would give. Page
  loads are small; file downloads are proxied and dominated by bandwidth anyway.
- Domain mappings are still a preview feature and have a per-project cap worth
  checking before ~20 tenants.
- Moving back to southamerica-east1 becomes possible once the wildcard load
  balancer exists, since that path is region-independent.
