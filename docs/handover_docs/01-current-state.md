# Current state — 2026-10-24

> **Working branch: `markbook_phase_0`** (branched from `master`, 2026-10-24).

## Phase board

| Phase | Status | Verified | Notes |
|---|---|---|---|
| 0 — Foundations | **in progress** | 2026-10-24 | Branch `markbook_phase_0`. Docker, Python 3.12, Node v24 confirmed available. |
| 1 — Identity, access, audit | not started | — | |
| 2 — People and academic structure | not started | — | |
| 3 — Assessment templates and score entry | not started | — | |
| 4 — Calculation engine and processing | not started | — | |
| 5 — Workflow, locking, publication, documents | not started | — | |
| 6 — Web client | not started | — | |
| 7 — Desktop client and sync | not started | — | |
| 8 — Hardening and pilot | not started | — | |

### Phase 0 verification step (2026-10-24)

> Start-of-phase check. All items listed as **Missing** — no application code exists.
> Plan: build all Phase 0 deliverables, then re-run the check before reporting exit.

| Deliverable | Status | Notes |
|---|---|---|
| Monorepo layout (apps/api, apps/worker, apps/web, apps/desktop, packages/) | Missing | — |
| docker compose (api, worker, postgres, redis, minio) | Missing | — |
| Config system (pydantic-settings, env loading) | Missing | — |
| DB session with tenant context (SET LOCAL app.school_id) | Missing | — |
| Alembic baseline migrations (schools, audit_events, outbox_events, jobs + RLS) | Missing | — |
| Logging with request ids (structlog-style JSON) | Missing | — |
| Error format (RFC 7807 problem details) | Missing | — |
| Pagination and idempotency helpers | Missing | — |
| CI pipeline (GitHub Actions) | Missing | — |
| Import-linter (module boundary rules) | Missing | — |
| ADRs 001–005 | Missing | — |

**Result: all Missing. Implementation starts.**

## Open items carried into Phase 0

Open decisions from [`../build_docs/09-open-decisions.md`](../build-docs/09-open-decisions.md) — defaults
accepted unless revised explicitly:

| # | Decision | Default applied | ADR needed |
|---|---|---|---|
| 1 | Hosting provider and region | Managed Postgres + container platform, nearest Nigeria-friendly region | No |
| 2 | Job queue library | **Arq** (Phase 0) | ADR 003 |
| 3 | PDF generation | WeasyPrint in worker | No |
| 4 | Retention periods | Configurable per school, set by policy | No |
| 5 | Separation of duties | On by default, configurable | No |
| 6 | Desktop encryption | SQLCipher + OS keychain | No |
