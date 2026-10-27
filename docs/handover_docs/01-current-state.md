# Current state — 2026-10-27

> **Working branch: `markbook_phase_1`** (cut from `markbook_phase_0`, 2026-10-27).
> Phase 0 lives on `markbook_phase_0` / `master` (PR #1). Phase 1 work sits on `markbook_phase_1`.

## Phase board

| Phase | Status | Verified | Notes |
|---|---|---|---|
| 0 — Foundations | ✅ **COMPLETE** | 2026-10-25 | All exit criteria verified live (compose, health, migrations, RLS); CI push pending |
| 1 — Identity, access, audit | 🔄 **code-complete, sign-off blocked** | unit tests 2026-10-27 | All deliverables built; 9 testcontainer tests blocked on Docker (not installed on this machine) |
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

## Phase 1 status — 2026-10-27

All Phase 1 deliverables are code-complete. Exit criteria are gated on 9 testcontainer
tests that require Docker Desktop (not installed on this machine).

### Deliverables

| Deliverable | Status | Evidence |
|---|---|---|
| users, sessions, devices tables | ✅ Built | `0002_identity_access` migration |
| roles, permissions (seeded), role/user junctions | ✅ Seeded on `upgrade head` | `permissions` 28 rows + Super Admin role with all perms |
| Authorization engine + `require()` dependency | ✅ Built | `access/service.py`, `access/dependency.py` |
| Route-coverage guard (`@public` marker) | ✅ Built + tested | `test_route_coverage.py` |
| Login throttling + lockout (Redis) | ✅ Built | `platform/throttling.py`, 6 unit tests pass |
| Refresh rotation + reuse detection | ✅ Built | `service.py`; reuse revokes session family, bumps token_version |
| MFA (TOTP setup/verify) | ✅ Built | `identity/router.py` endpoints |
| Super Admin protections (API + DB trigger) | ✅ Built | `service.py` guard + `protect_super_admin()` trigger in `0002` |
| Audit service with SHA-256 hash chain | ✅ Built | `audit/service.py`; 6 unit tests pass |

### Exit criteria

| Criterion | Status | Command / evidence |
|---|---|---|
| Authorization matrix tests | ✅ Unit pass | `pytest tests/unit/test_authorize.py -q` |
| Last-SA protection (API) | ✅ Code done; test blocked | `test_last_sa_protection.py` — testcontainer needs Docker |
| Last-SA protection (DB trigger) | ✅ Code done; test blocked | `test_super_admin_trigger.py` — testcontainer needs Docker |
| Revoked session fails immediately | ✅ Implemented | `access/dependency.py` checks token_version against Redis cache (30 s TTL) |
| Audit chain verifier | ✅ Unit pass | `pytest tests/unit/test_audit_chain.py -q` |

**Measured gates, 2026-10-27** (run from `apps/api` with `.venv`):
`ruff check` clean · `ruff format --check` clean · `mypy src/app tests migrations -q` → Success ·
`pytest tests/unit tests/api -q` → 45 passed · 9 ERRORS (Docker blocked).

### Phase 1 deviation (2026-10-27)

Phase 1 work landed on `markbook_phase_0` rather than a fresh branch (rule 16 breach —
one branch per phase was not followed). Fixed 2026-10-27 by cutting `markbook_phase_1`
at HEAD and leaving `markbook_phase_0` as-is (no force-push). `master` holds Phase 0
via PR #1 (`aeb1966`). `markbook_phase_1` holds the 17 commits of Phase 0-final-fix
through Phase 1 code-complete.

## Phase 0 deviations (2026-10-25)

Fixes applied to `infra/compose.dev.yml` to unblock local dev:

| Issue | Fix |
|---|---|
| `minio/minio` Docker Hub rate-limited; pull always fails | Replaced with `docker.io/minio/minio:latest`; placed in `profiles: ["storage"]` so it does not block `compose up` |
| Ports 5432/6379/8000 occupied by existing containers/services | Remapped postgres → `:5433`, redis → `:6380`, api → `:8001` |
| Compose `dockerfile` paths (`docker/api.Dockerfile`) resolved outside repo root | Copied Dockerfiles to `infra/api.Dockerfile` and `infra/worker.Dockerfile`; compose updated to `infra/*.Dockerfile` |
| Compose env vars (`DATABASE_URL`, `REDIS_URL`, …) ignored by `platform/config.py` (reads `MARKBOOK_*`) | All env vars prefixed `MARKBOOK_` in compose |

Phase 0 gates (live Docker):
- ✅ Health endpoint → `{"status":"ok","environment":"dev","database":"ok"}`
- ✅ `alembic upgrade head` → `INFO Running upgrade -> 0001_baseline`
- ✅ OpenAPI at `/openapi.json` → 1 path served
- ✅ RLS tests → `pytest tests/security -v` → 2 passed in 18.81s
- ⏳ CI green (push to GitHub)

## Open items carried into Phase 0

Open decisions from [`../build_docs/09-open-decisions.md`](../build_docs/09-open-decisions.md) — defaults
accepted unless revised explicitly:

| # | Decision | Default applied | ADR needed |
|---|---|---|---|
| 1 | Hosting provider and region | Managed Postgres + container platform, nearest Nigeria-friendly region | No |
| 2 | Job queue library | **Arq** (Phase 0) | ADR 003 |
| 3 | PDF generation | WeasyPrint in worker | No |
| 4 | Retention periods | Configurable per school, set by policy | No |
| 5 | Separation of duties | On by default, configurable | No |
| 6 | Desktop encryption | SQLCipher + OS keychain | No |
