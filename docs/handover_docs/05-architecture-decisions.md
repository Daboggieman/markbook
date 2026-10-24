# Architecture decisions — why Markbook is built the way it is

The D1–D10 decisions from the spec
([`../build_docs/00-overview.md`](../build_docs/00-overview.md)) are the load-bearing ones. This
file records the reasoning behind them, the reasoning that is not restated per-file, and the
decisions that were made during the build. ADRs in `docs/adr/` are the formal record; this file
is the narrative.

## Why a modular monolith (D1), not microservices

Markbook's peak load is a school entering results in the last week of term — bursts of write
traffic on `scores`, then heavy read traffic on `processed_results`. This is a write-then-read
burst pattern, not a scale-out-per-module pattern. A monolith with clean boundaries lets us
deploy one thing, test it as one thing, and extract a service later only if a specific module
actually needs it (the trigger table in
[`../build_docs/01-architecture-and-stack.md`](../build_docs/01-architecture-and-stack.md)
names the triggers).

## Why Postgres-only, not Postgres + a document store

Every structured piece of data fits a table. The JSONB columns (`definition`, `breakdown`,
`flags`, `config`) hold things that are *shaped* but not *queried* — grading boundaries, score
breakdowns. When a query against a JSONB column becomes hot, that is the signal to promote the
field to a column, not to add a second store.

## Why school_id + RLS, not just school_id

`school_id` on every table is the primary defence; RLS is the second. A repository base class
enforces the first. The second exists because a single missed `WHERE school_id = ?` in a
hand-written analytics query would otherwise leak across tenants silently. RLS makes that
leak a permission error instead. The RLS test with two schools (Phase 0 exit criterion) proves
both layers work.

## Why a worker process, not async endpoints

Result processing for a 1,500-student term, PDF generation for a class, bulk imports — these
run tens of seconds. Doing them in a request thread ties up a worker slot, blows the request
timeout, and gives the client nothing to show but a spinner. Jobs return `202` immediately,
survive Redis loss (the `jobs` table), and are re-runnable.

## Why a transactional outbox, not a message broker

At launch there is exactly one consumer: in-process handlers. A broker (RabbitMQ, Kafka) adds
operational surface with no benefit until there is a second system consuming events. The
`outbox_events` table gives us the same guarantee — the event is committed in the same
transaction as the state change that produced it — and the dispatcher is the seam where a
broker later plugs in without changing producers.

## Why the engine is a pure module

`apps/api/src/app/grading/engine/` imports nothing from the app. No `platform`, no db session,
no settings. This is what makes it trivially unit-testable (pytest, hypothesis — no
testcontainers, no fixtures), and what makes it reusable by the worker without a network hop.
If a change to the engine needs a database, the change belongs in the service layer, not the
engine.

## Why contract-first

FastAPI generates OpenAPI; the TypeScript client is generated from it into
`packages/api-client/`. Web and desktop share the client. The alternative — hand-written
clients per frontend — drifts the first time someone adds a field on the backend and forgets
the frontend. The CI gate is an OpenAPI diff that flags breaking changes before merge.

## What is deliberately not here (yet)

- **No message broker.** The outbox is the seam (D5).
- **No read replica.** Added when reports slow (scaling stage 2).
- **No multi-school UI.** RLS and `school_id` are in place from day one; the UI is added when
  the second school is onboarded (scaling stage 3).
- **No fees, attendance, portals, messaging.** Requires an ADR (rule 12,
  [`../build_docs/10-coding-agent-rules.md`](../build_docs/10-coding-agent-rules.md)).
