# Markbook — Planning Package

This is the **plan**: what Markbook is meant to be, and the decisions that are locked. The
running record of what is actually built — current state, conventions in force, verified test
results, history — is a separate package in [`../handover_docs/`](../handover_docs/); start at
[`../handover_docs/README.md`](../handover_docs/README.md) before doing any work.

The source of record for everything here is
[`../Markbook_Build_Specification .md`](../Markbook_Build_Specification%20.md) (v1.0, derived from
the Consolidated Product and Technical Plan v1.0). These docs restate it in build order and add
nothing that contradicts it. If a claim here disagrees with the spec, the spec wins and this file
should be corrected.

Read in this order:

1. **00-overview.md** — the product in one page, the architectural stance, decisions D1–D10
2. **01-architecture-and-stack.md** — system diagram, module boundaries, dependency rule,
   scaling principles and path
3. **02-data-model.md** — multi-tenancy foundations, full schema per module, conventions
4. **03-api-design.md** — authentication, the authorization engine, API conventions, endpoint
   groups
5. **04-core-engine-specs.md** — the result calculation engine, the workflow state machine, the
   offline sync protocol
6. **05-testing-strategy.md** — what each test layer must cover, the CI gates
7. **06-roadmap.md** — the phased build plan (Phases 0–8) with exit criteria, and the
   verification-step template that opens every phase
8. **07-repo-structure.md** — the monorepo layout and the per-module internal shape
9. **08-security-and-operations.md** — the controls checklist, the STRIDE threat model,
   deployment and operations, runbooks
10. **09-open-decisions.md** — the decisions to resolve before or during Phase 0, with defaults
11. **10-coding-agent-rules.md** — the standing rules every coding session works under

## The one-paragraph summary

Markbook is a school record and report-card system for a single school at launch, built as a
modular monolith: one FastAPI deployable, Postgres as the sole source of truth, Redis for jobs
and rate limiting, S3-compatible object storage for documents. Web (React + TypeScript) and
desktop (Tauri, offline score entry with sync) share one generated API client. Every tenant
table carries `school_id` from day one with Row-Level Security as the second defence layer, so
going multi-school later is configuration, not a rewrite. The server is authoritative for
permissions, calculation, workflow, and locking — clients never decide these. Build one phase
at a time, in the order given by `06-roadmap.md`, and never start a phase before the previous
phase's exit criteria pass.
