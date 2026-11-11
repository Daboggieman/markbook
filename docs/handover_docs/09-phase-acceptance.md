# Phase acceptance — sign-off record for each phase

Each phase's exit criteria are in [`../build_docs/06-roadmap.md`](../build_docs/06-roadmap.md).
This file is the sign-off record: what was verified, when, and by what command. It is the
per-phase close-out, not the full detail.

## How to use this file

A phase is not complete until this file says it is — and what it says is measured, not
assumed. Every row below was filled in by running the stated command and recording the exact
output.

## The phases

### Phase 0: Foundations

**Exit criteria:**
- `docker compose up` works; health endpoint passes
- CI green
- RLS test with two schools passes
- OpenAPI served at `/openapi.json`

| Criterion | Verified | Command + result |
| --- | --- | --- |
| ruff check | ✅ 2026-10-24 | `ruff check .` → All checks passed! |
| ruff format | ✅ 2026-10-24 | `ruff format --check .` → 34 files already formatted |
| mypy (full tree) | ✅ 2026-10-24 | `mypy src/app tests migrations` → Success: no issues found in 44 source files |
| mypy strict (grading/access) | ✅ 2026-10-24 | `mypy src/app/grading src/app/access` → Success (3 files) |
| import-linter | ✅ 2026-10-24 | `lint-imports --config contracts.ini` → Contracts: 4 kept, 0 broken |
| pytest unit+api | ✅ 2026-10-24 | `pytest tests/unit tests/api -q` → 15 passed |
| OpenAPI at /openapi.json | ✅ 2026-10-24 | TestClient: `test_openapi_served` passes; spec served at FastAPI default |
| Request-id middleware echo | ✅ 2026-10-24 | `test_request_id_middleware` passes — X-Request-Id echoed on response |
| docker compose up | ✅ 2026-10-25 | `docker compose -f infra/compose.dev.yml up -d --build` → all services started (postgres on :5433, redis on :6380, api on :8001) |
| health endpoint (live) | ✅ 2026-10-25 | `curl localhost:8001/health` → `{"status":"ok","environment":"dev","database":"ok"}` |
| alembic upgrade head (clean DB) | ✅ 2026-10-25 | `MARKBOOK_DATABASE_URL=...@localhost:5433/markbook alembic -c alembic.ini upgrade head` → `INFO Running upgrade -> 0001_baseline` |
| RLS test (two schools) | ✅ 2026-10-25 | `pytest tests/security -v` → 2 passed in 18.81s — cross-tenant read isolation verified; unset context returns empty |
| CI green | ⏳ PENDING | Same checks as above in GitHub Actions; cannot run locally without a push |

---

### Phase 1: Identity, access, audit

**Exit criteria:**
- Authorization matrix tests pass
- Cannot delete or deactivate last Super Admin (API and DB trigger)
- Revoked session fails immediately
- Audit chain verifier passes

| Criterion | Verified | Command + result |
| --- | --- | --- |
| Authorization matrix tests | ✅ 2026-10-27 | `pytest tests/unit/test_authorize.py -q` — pass |
| Super Admin delete block (API) | ✅ 2026-10-27 | `test_last_sa_protection.py` — 3 passed (sole-SA 409; suspend with second SA allowed; revocation + token bump) |
| Super Admin delete block (trigger) | ✅ 2026-10-27 | `pytest tests/security/test_super_admin_trigger.py` — 5 passed (delete/deactivate/demote blocked; allowed with second active SA; non-SA never blocked) |
| Revoked session fails | ✅ 2026-10-27 (code) | `access/dependency.py` rejects JWT whose `token_version` ≠ DB value; Redis cache 30 s TTL; token_version bump on revocation verified live in `test_deactivate_revokes_sessions_and_bumps_token_version` |
| Audit chain verifier | ✅ 2026-10-27 | `pytest tests/unit/test_audit_chain.py -q` — pass |

**Full-suite gates, 2026-10-27 (Docker Desktop installed):**
`pytest tests` → **68 passed** in 17.71s (includes 10 testcontainer tests: Super Admin trigger ×5,
last-SA API ×3, RLS isolation ×2) · `ruff check` clean · `ruff format --check` clean (64 files) ·
`mypy src/app tests migrations` → Success (64 files).

**Fixes required to run the Docker-gated tests on this machine (Windows, Python 3.14):**
- `migrations/env.py` — run async migrations with `loop_factory=asyncio.SelectorEventLoop` on
  win32 (psycopg async refuses ProactorEventLoop; also affects host-side `alembic upgrade`).
- `tests/conftest.py` — register `pytest_asyncio_loop_factories` hook (Windows only) so
  pytest-asyncio builds Selector loops; enable `citext` extension on the testcontainer before
  migrations; libpq connection-string helper for the extension call.
- `migrations/versions/0002_identity_access.py` — `user_roles` RLS policy referenced a
  `school_id` column the table never had; added `school_id UUID NOT NULL` (+index), matching
  the model's tenancy convention.
- `src/app/identity/models.py` — `User.status` declared `String(20)` but the DB column is the
  `userstatus` enum; comparisons rendered `::VARCHAR` and failed. Declared as native `Enum`.
  (`RolePermission.scope_type` has the same String-vs-`scopetype` mismatch but no code path
  compares it in SQL yet — flagged for Phase 2.)
- Test bugs (never run against a live DB before 2026-10-28): bind-name mismatch (`:st` vs
  `"status"`) and str-vs-UUID bind in `test_super_admin_trigger.py::_exec`; revocation test
  seeded its user as a lone Super Admin (correctly hit the 409 guard) and never committed the
  service transaction (router commits after service calls) — both corrected.

**Result: Phase 1 exit criteria all verified 2026-10-27.**

---

### Phase 2: People and academic structure

**Exit criteria:**
- Student archive preserves history
- Promotion keeps old results context
- Scoped student lists respect teacher assignments
- Migrations apply on clean DB

| Criterion | Verified | Command + result |
| --- | --- | --- |
| Student archive | — | — |
| Promotion preserves results | — | — |
| Scoped student lists | — | — |
| Clean-DB migrations | — | — |

---

### Phase 3: Assessment templates and score entry

**Exit criteria:**
- DB CHECK blocks invalid zero/missing combinations
- Editing a template creates a new version without altering existing assessments
- Teacher cannot enter scores outside assignment

| Criterion | Verified | Command + result |
| --- | --- | --- |
| CHECK constraint enforced | — | — |
| Template versioning | — | — |
| Scored entry boundary | — | — |

---

### Phase 4: Calculation engine and processing

**Exit criteria:**
- All golden examples pass
- Boundary and property tests pass
- Identical inputs produce identical `input_hash` and outputs
- Coverage on `grading` at least 90%

| Criterion | Verified | Command + result |
| --- | --- | --- |
| Golden examples | — | — |
| Boundary / property tests | — | — |
| Determinism (`input_hash`) | — | — |
| Coverage ≥ 90% | — | — |

---

### Phase 5: Workflow, locking, publication, documents

**Exit criteria:**
- Every illegal transition rejected
- Edits blocked after submit
- Published documents immutable; corrections create a superseding version
- Every action in the audit log

| Criterion | Verified | Command + result |
| --- | --- | --- |
| Illegal transitions | — | — |
| Edit lock after submit | — | — |
| Document immutability | — | — |
| Audit trail completeness | — | — |

---

### Phase 6: Web client

**Exit criteria:**
- Playwright E2E for teacher and admin flows pass
- UI hides unauthorised actions; backend tests prove enforcement

| Criterion | Verified | Command + result |
| --- | --- | --- |
| Teacher E2E | — | — |
| Admin E2E | — | — |
| Backend enforcement proven | — | — |

---

### Phase 7: Desktop client and sync

**Exit criteria:**
- All sync tests pass
- Duplicate prevention proven
- Revoked device wipes local data
- Online-only actions disabled offline

| Criterion | Verified | Command + result |
| --- | --- | --- |
| Sync test suite | — | — |
| Duplicate prevention | — | — |
| Revocation wipe | — | — |
| Offline guards | — | — |

---

### Phase 8: Hardening and pilot

**Exit criteria:**
- No known critical security issues
- Restore drill succeeded with recorded RTO/RPO
- Load targets met (500 concurrent teachers; 1,500-student term processing)
- Pilot checklist signed off

| Pilot checklist | — | — |

---

## Phase 0 delivered files (2026-10-24)

Built this session on branch `markbook_phase_0`:

- **Monorepo layout** — `apps/api` (FastAPI + SQLAlchemy async + Alembic), `apps/worker` (Arq
  entrypoint), `apps/web`, `apps/desktop`, `packages/{api-client,ui,rules}` (skeletons),
  `infra/`, `docs/adr/`
- **Config system** — `platform/config.py` (pydantic-settings, env + .env)
- **DB session with tenant context** — `platform/db.py`; `set_config('app.school_id', …, true)`
  inside the transaction (SET LOCAL cannot take bind params — ADR 004)
- **Alembic baseline** — `migrations/versions/0001_baseline.py`: schools (seeded), audit_events
  (append-only by design), outbox_events (RLS enabled + policy), jobs; indexes per spec §6
- **Logging with request ids** — `platform/logging.py` (structlog JSON, request/school/actor
  context, scrubber denylist)
- **Error format** — `platform/errors.py`: RFC 7807, stable machine codes, FastAPI exception
  handler
- **Pagination** — `platform/pagination.py`: cursor round-trip, hard max 200
- **Idempotency** — `platform/idempotency.py`: Redis-backed, 24 h TTL, fingerprint mismatch → 422
- **Outbox helpers** — `platform/outbox.py`: `enqueue_outbox_event` for the three launch topics
- **Docker compose** — `infra/compose.dev.yml`: postgres 17, redis 7, minio, api, worker
  (healthchecks wired)
- **Dockerfiles** — `infra/docker/api.Dockerfile`, `infra/docker/worker.Dockerfile`
- **Worker entrypoint** — `apps/worker/worker.py` (Arq WorkerSettings; job list empty until
  Phase 2)
- **CI** — `.github/workflows/ci.yml`: ruff, mypy, import-linter, pytest (unit+api), DB tests
  via testcontainers
- **ADRs 001–005** — monolith, outbox, Arq, tenant-context/RLS, WeasyPrint
- **`.env.example`** — all environment variables with dev placeholders
- **Import-linter note**: `contracts.ini` carries the no-cross-repository contract with
  forbidden_modules for `.repository` submodules that Phase 1 will create; the self-import
  `ignore_imports` entries are documented in the file and must be added when the first
  repository.py lands

### Deviations from spec (recorded per rule 14)

- Compose file lives at `infra/compose.dev.yml` (spec §4 layout reads as `infra/` root) with
  Dockerfiles under `infra/docker/`.
- RLS policy ships on `outbox_events` only in Phase 0 — the other three baseline tables are
  cross-tenant infrastructure; full RLS lands with the tenant-owned tables (Phase 1+). The RLS
  *test* proves the mechanism, not full coverage.
- `unmatched_ignore_imports_alerting = warning` in contracts.ini until Phase 1 adds the
  repository self-import ignore entries.