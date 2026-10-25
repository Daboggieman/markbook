# Markbook — Overview and Architectural Decisions

Source of record: spec §1 (Purpose and Key Architectural Decisions).

## What Markbook is

Markbook is a school record and report-card system: assessment templates, score entry (web and
offline desktop), a deterministic calculation engine, an approval workflow from entry to
publication, and generated report cards and transcripts. It replaces spreadsheets and manual
report-card assembly with a system where zero is distinct from missing, every change is
attributed and audited, and published documents are immutable and superseded by version.

The launch posture is **one school**. That is a product decision, not an architectural one.

## The one deliberate adjustment: single-school features, tenant-ready foundations

The product plan postpones multi-school tenancy, which is correct for features. But
retrofitting tenancy into a finished schema is one of the most painful migrations there is. So
the spec makes one adjustment, and everything in this package follows from it:

> **Single-school features, tenant-ready foundations.** Every tenant-owned table carries a
> `school_id` from day one. The app runs with exactly one school row at launch. No cross-school
> features are built. Going multi-school later becomes a configuration and UI task, not a
> rewrite.

Mechanically this means: `school_id UUID NOT NULL` on every tenant-owned table, an index
leading with `school_id`, the request context deriving `school_id` from the authenticated user
(never from client input), Row-Level Security as the second defence layer, composite
uniqueness scoped by school, and a repository base class so developers cannot forget it. Full
detail in [`02-data-model.md`](02-data-model.md).

## Decision summary (D1–D10)

These are locked. Recording them as ADRs in `docs/adr/` is part of Phase 0 (ADRs 001–005) and
continues per [`10-coding-agent-rules.md`](10-coding-agent-rules.md) rule 13.

| # | Decision | Why |
| --- | --- | --- |
| D1 | Modular monolith (one FastAPI deployable, strict internal module boundaries) | Fastest to build, easiest to test, and modules can be extracted into services later because boundaries are already enforced |
| D2 | Stateless API behind a load balancer | Horizontal scaling by adding instances |
| D3 | PostgreSQL as sole source of truth, with `school_id` on every tenant table and Row-Level Security (RLS) as a second defence layer | Tenant-ready and defence in depth |
| D4 | Background worker (separate process, same codebase) for result processing, imports, PDF generation, sync post-processing | Heavy work never blocks request threads |
| D5 | Transactional outbox for domain events | Reliable events without a message broker at launch; broker can be added later without changing producers |
| D6 | Redis for rate limiting, caching, and job queue | Standard, cheap, scales independently |
| D7 | Object storage (S3-compatible) for generated PDFs, imports, exports | Keeps the database lean and files durable |
| D8 | Server is authoritative for permissions, calculation, workflow, and locking; clients never decide these | Matches the product plan security invariant |
| D9 | Calculation engine is a pure, dependency-free Python module | Deterministic, trivially unit-testable, reusable by workers |
| D10 | Contract-first API: OpenAPI generated from FastAPI, TypeScript client generated from it | Web and desktop share one typed client; no drift |

## The internal modules (bounded contexts)

| Module | Owns |
| --- | --- |
| `identity` | users, sessions, devices, MFA, password reset |
| `access` | roles, permissions, scopes, authorization engine |
| `people` | students, guardians, staff profiles |
| `academic` | sessions, terms, levels, classes, sections, subjects, enrolments, teacher assignments, promotions |
| `assessment` | templates, template versions, assessments, scores |
| `grading` | grading schemes, calculation engine, processing runs, processed results |
| `workflow` | approval state machine, approval records, locks, publication |
| `documents` | report cards, transcripts, PDF generation, exports |
| `sync` | desktop sync operations, device registration, conflict handling |
| `audit` | audit events (append-only) |
| `platform` | config, db, redis, jobs, outbox, logging, errors (shared kernel) |

**Dependency rule:** `platform` depends on nothing. `audit` and `access` may be called by all.
Other modules may depend on `people` and `academic` read interfaces, and `workflow` may depend
on `grading`. No cycles. Enforced with an import-linter rule in CI.

## What is deliberately out of scope

No fees, no attendance, no parent portals, no multi-school UI, no messaging. Rule 12 in
[`10-coding-agent-rules.md`](10-coding-agent-rules.md): features outside the initial scope
require an ADR first.
