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
| Monorepo layout (apps/api, apps/worker, apps/web, apps/desktop, packages/) | ✅ Done | Skeleton + full api platform layer |
| docker compose (api, worker, postgres, redis, minio) | Built, **unverified** | `infra/compose.dev.yml` written; `up` blocked on Docker daemon not running |
| Config system (pydantic-settings, env loading) | ✅ Built | `platform/config.py` |
| DB session with tenant context (set_config + RLS) | ✅ Built | `platform/db.py`; ADR 004 |
| Alembic baseline (schools, audit_events, outbox_events, jobs + RLS) | Built, **needs live-DB run** | `alembic upgrade head` untested (no DB) |
| Logging with request ids (structlog JSON) | ✅ Built | Middleware echoes X-Request-Id (tested) |
| Error format (RFC 7807 problem details) | ✅ Built | Handler registered; unit-tested |
| Pagination and idempotency helpers | ✅ Built | Unit-tested (15 tests pass) |
| CI pipeline (GitHub Actions) | ✅ Written | `.github/workflows/ci.yml` — runs on push |
| Import-linter (module boundary rules) | ✅ Verified | 4/4 contracts KEPT |
| ADRs 001–005 | ✅ Done | `docs/adr/001`–`005` |

**Measured gates, 2026-10-24** (all run from `apps/api` with `.venv`):
`ruff check` clean · `ruff format --check` clean · `mypy` clean (44 files) ·
`lint-imports` 4/4 KEPT · `pytest tests/unit tests/api -q` → 15 passed.

**Blocked on Docker daemon (not running):** `docker compose up`, live health endpoint,
`alembic upgrade head` against real Postgres, RLS testcontainers run. Sign-off rows for these
sit in [`09-phase-acceptance.md`](09-phase-acceptance.md) as PENDING.

**Result: Partial — local gates green, Docker-dependent gates pending.**

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
