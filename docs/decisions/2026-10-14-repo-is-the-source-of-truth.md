---
date: 2026-10-14
title: The repository is the single source of truth for decisions
status: accepted
supersedes:
superseded_by:
deciders: [fabio]
tags: [process, agents]
---

## Context

Work on this project happens across Claude Code (CLI), Cowork (cloud sessions
linked to a laptop), Codex (a non-technical collaborator), and plain chat
sessions with no repository attached. Each tool sees only its own history. A
claude.ai project's docs are invisible to the CLI and to Codex; a Cowork
conversation is invisible to both; a chat with no repo attached can read nothing
and commit nothing.

Decisions were being recorded in a claude.ai project doc, which three of the
four actors cannot read.

## Decision

The repository is the only shared substrate, so decisions live here:

- `docs/decisions/` — one file per decision, `YYYY-MM-DD-short-slug.md`.
- `docs/decisions/README.md` — a one-line index, so an agent can see the whole
  decision history without opening every file.
- `AGENTS.md` carries the protocol, because it is the one file every coding
  agent loads unprompted (an open standard; Codex, Claude Code, Cursor, Copilot's
  coding agent and others implement it).
- `docs/multi-tenant-plan.md` is the canonical plan. Copies elsewhere are
  mirrors.

A decision discussed in a chat is not recorded until it is committed.

## Rejected alternatives

- **A single append-only `decisions.md`.** Simpler to read in one pass, but with
  four actors two simultaneous appends conflict. Separate files cannot.
- **Sequentially numbered ADRs (`0007-...`).** The standard convention, but the
  numbers collide when two actors create an entry independently and there is no
  coordinating authority. Dates cannot collide.
- **Keeping decisions in the claude.ai project.** Convenient from a phone,
  unreadable by the CLI and by Codex. Demoted to a mirror.

## Consequences

- Any agent can reconstruct why the system is shaped as it is from the repo
  alone.
- The index file is a shared-edit point, but a one-line table append conflicts
  rarely and resolves trivially.
- This only holds if it is enforced. Nothing here is automatic; the cheapest real
  gate is requiring a decisions entry (or an explicit "no decisions") before a
  branch merges.
- The remaining leak is any conversation without the repo attached. That is
  discipline, not tooling: end such a conversation by producing the entry as
  markdown and committing it.
