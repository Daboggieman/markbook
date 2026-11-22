# Current state — 2026-11-18

> **Working branch: `markbook_phase_6`** (cut from the Phase 5 tip, 2026-11-16, at Phase 6
> start). Phase 5 lives on `markbook_phase_5`; Phase 4 on `markbook_phase_4`; Phase 3 on
> `markbook_phase_3`; Phase 2 on `markbook_phase_2`; Phase 1 on `markbook_phase_1`;
> Phase 0 on `markbook_phase_0` / `master` (PR #1).
> In progress: Phase 6 — web client.

## Phase board

| Phase | Status | Verified | Notes |
|---|---|---|---|
| 0 — Foundations | ✅ **COMPLETE** | 2026-10-25 | All exit criteria verified live (compose, health, migrations, RLS); CI push pending |
| 1 — Identity, access, audit | ✅ **COMPLETE** | 2026-10-27 | All exit criteria verified live: full suite 68 passed (incl. 10 testcontainer tests), ruff/mypy clean — see [`09-phase-acceptance.md`](09-phase-acceptance.md) |
| 2 — People and academic structure | ✅ **COMPLETE** | 2026-11-02 | All exit criteria verified live: full suite **83 passed** (incl. 25 testcontainer tests), ruff/mypy/import-linter clean — see [`09-phase-acceptance.md`](09-phase-acceptance.md) |
| 3 — Assessment templates and score entry | ✅ **COMPLETE** | 2026-11-06 | All exit criteria verified live: full suite **125 passed** (incl. 42 testcontainer tests), ruff/mypy/import-linter clean — see [`09-phase-acceptance.md`](09-phase-acceptance.md) |
| 4 — Calculation engine and processing | ✅ **COMPLETE** | 2026-11-11 | All exit criteria verified live: full suite **193 passed** (incl. 77 testcontainer-gated tests), coverage on `app.grading` **96%**, ruff/mypy/import-linter clean — see [`09-phase-acceptance.md`](09-phase-acceptance.md) |
| 5 — Workflow, locking, publication, documents | ✅ **COMPLETE** | 2026-11-13 | All exit criteria verified live: full suite **243 passed** (exit 0), coverage grading **96%** / access **99%** / workflow **96%**, ruff/mypy/import-linter clean — see [`09-phase-acceptance.md`](09-phase-acceptance.md) |
| 6 — Web client | 🚧 **In progress** | started 2026-11-16 | Scaffold + generated API client + auth flow + shell landed (`ad803a7`…`0f08060`); admin screens built (users/roles incl. the new access router, academic, students, assessments); **score sheet landed 2026-11-22** (keyboard grid, m/a/e statuses, conflict dialog, 7 component tests); **review/approval + reports landed 2026-11-22** (`WorkflowBar` — §10 actions per state+grants, reason prompts, step-up dialog with MFA reveal; `ReportsPage` + the new `GET /documents/assessment/{id}` list endpoint, 29 component tests, API+web both green); **Playwright E2E scaffolded 2026-11-22** (`e2e/workflow.spec.ts` — the §16 walk, TS TOTP helper, API-driven seeding; needs the dev stack running + browsers installed to execute) |
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

## Phase 5 status — COMPLETE 2026-11-13

All Phase 5 deliverables are built and all exit criteria verified live (full suite
**243 passed**, exit 0). Sign-off detail and the two Phase 1 model bugs the coverage
gate exposed are in [`09-phase-acceptance.md`](09-phase-acceptance.md).

### Deliverables

| Deliverable | Status | Evidence |
|---|---|---|
| State machine with configurable stages | ✅ Built | `workflow/models.py` + `workflow/service.py`; definitions upsertable (stages replaced on save); unknown state rejected |
| §10 transition table (8 edges) | ✅ Built + tested | `TRANSITIONS` in `workflow/service.py`; permission/guard/reason/document_job flags mirror the spec table row-for-row (`test_transitions_table.py`) |
| Approval records | ✅ Built | One from→to record per transition in the same transaction; 5 pairs asserted on the full walk |
| Step-up auth + MFA on publish | ✅ Built | `require_reauth()` (300s window) on lock; +`reauth_mfa` claim on publish; REAUTH_REQUIRED / MFA_REQUIRED / expired-window all over real HTTP |
| Publication + PDF generation job | ✅ Built | `documents/jobs.py` — worker entry points with `_renderer`/`_storage_factory` seams; enqueue on the publish transition (ADR 005) |
| Report cards + transcripts | ✅ Built | report cards per published assessment; transcripts collect every published term ordered; download via presigned URL + audit |
| Correction versioning | ✅ Built | `published_documents` INSERT-only; corrections force vN+1 with `supersedes_id` + `correction_reason` |
| RLS on the three Phase 5 tables | ✅ Verified live | `tests/security/test_phase5_rls.py` — cross-tenant reads blocked through the app role |
| Audit trail per action (exit criterion) | ✅ Verified live | full walk asserts audit actions + both outbox topics inside each transition transaction |

### Exit criteria

| Criterion | Status | Evidence |
|---|---|---|
| Every illegal transition rejected | ✅ Verified live | `TestIllegalTransitions` — 409 INVALID_STATE_TRANSITION on every out-of-table action from every state |
| Edits blocked after submit | ✅ Verified live | 409 while submitted; editable again after return with `base_version` optimistic concurrency |
| Published documents immutable; corrections supersede | ✅ Verified live | identical re-run generates 0 / skips 3; correction v2 supersedes v1, v1 untouched |
| Every action in the audit log | ✅ Verified live | audit + outbox asserted per transition; download audited too |

**Measured gates, 2026-11-13 (final)** (run from `apps/api` with `.venv`):
`ruff check` clean (src+tests) · `ruff format` clean (114 files) ·
`mypy src/app` → Success (79 files) · `lint-imports` 4/4 KEPT ·
`pytest tests` → **243 passed**, exit 0 · coverage grading **96%** / access **99%** /
workflow **96%** against the ≥90% gate on all three (05-testing-strategy.md).

### Phase 5 notes

- **The access coverage gate found two Phase 1 model/migration drifts** (both fixed):
  `UserRole` lacked `school_id` (NOT NULL in migration 0002 — any ORM insert would
  violate it) and `RolePermission.scope_type` was `String(20)` against the
  `scopetype` enum (VARCHAR param refused). Neither had ever been exercised — no
  roles API exists yet; all seeds use raw SQL. Detail in the acceptance doc.
- `scores.edit` (edit-after-submit gating, carried from Phase 3's note) landed here:
  submitted blocks score writes (409), returned allows them with optimistic
  concurrency.
- Reauth deliberately has no lockout/throttling (contrast login) — flagged for the
  Phase 8 hardening review.

## Phase 2 status — COMPLETE 2026-11-02

All Phase 2 deliverables are built and all exit criteria verified live (full suite **83 passed**,
including 25 testcontainer tests). Sign-off detail and the 2026-11-02 gate repair are in
[`09-phase-acceptance.md`](09-phase-acceptance.md).

### Deliverables

| Deliverable | Status | Evidence |
|---|---|---|
| students, guardians, student_guardians | ✅ Built | `people/models.py`; migration `0003` |
| Duplicate detection (409 POSSIBLE_DUPLICATE + confirm bypass) | ✅ Built | `people/service.py` (`BLOCK_SIMILARITY` 0.85 / report 0.6), `POST /students/check-duplicates` |
| academic_sessions, terms, levels, classes, sections, subjects, class_subjects | ✅ Built | `academic/models.py`, `academic/router.py` |
| enrolments, subject_enrolments | ✅ Built | Models + `POST /enrolments`; subject enrolments managed via enrolment/promotion services |
| teacher_assignments | ✅ Built | `GET/POST /teacher-assignments` |
| promotions (`POST /promotions/run`, per-student decisions) | ✅ Built | `academic/service.py::run_promotion` |
| Nigerian default seed (Nursery, Primary 1–6, JSS 1–3, SS 1–3) | ✅ Seeded on `upgrade head` | Migration `0003` level/class seed loops |

### Exit criteria

| Criterion | Status | Evidence |
|---|---|---|
| Student archive preserves history | ✅ Verified live | `tests/db/test_people.py::test_archive_preserves_history` |
| Promotion keeps old results context | ✅ Verified live | `tests/db/test_academic.py` promotion invariant (old enrolment row + stamps + subject_enrolments kept) |
| Scoped student lists respect teacher assignments | ✅ Verified live | `test_scoped_list_respects_teacher_assignments` + `test_assignment_section_narrowing`; `GET /students` uses `require_with_scope("students.view")` |
| Migrations apply on clean DB | ✅ Verified every run | testcontainer fixture applies `alembic upgrade head` to a fresh Postgres per session |

**Measured gates, 2026-11-02 (final)** (run from `apps/api` with `.venv`):
`ruff check` clean · `ruff format --check` clean (79 files) · `mypy src/app tests migrations` →
Success (79 files) · `lint-imports` 4/4 KEPT · `pytest tests` → **83 passed** (exit 0), incl. 25
testcontainer-gated tests.

### Phase 2 deviation (2026-10-30 → 2026-11-02)

Commit `981717c` ("Remove legacy identity router and phase 2 academic tests") emptied
`identity/router.py` (the entire Phase 1 auth surface) and `tests/db/test_academic.py` (the
promotion-invariant tests) to zero bytes without a replacement or an ADR, leaving `main.py`
importing the emptied module — the app could not start and no API-level test could collect.
Repaired 2026-11-02 by restoring both files from the parent commit (`3f4b0f6`), fixing the
latent defects the restored test carried (F821 `decider`, stale 3-tuple annotation, mojibake +
BOM), adding the documented `app.people.service -> app.people.repository` self-import ignore to
`contracts.ini`, and silencing S608/E501 in migration `0003` (seed literals; SQL byte-identical).
The Phase 2 RLS seed helper also gained the missing `schools` row insert (FK violation against a
fabricated `uuid4()` school id). No commits were made in-session; the repair sits uncommitted in
the working tree for the owner to commit.

## Phase 4 status — COMPLETE 2026-11-11

All Phase 4 deliverables are built and all exit criteria verified live (full suite **193 passed**,
including 77 testcontainer-gated tests; coverage on `app.grading` **96%**). Sign-off detail and
deviations are in [`09-phase-acceptance.md`](09-phase-acceptance.md).

### Deliverables

| Deliverable | Status | Evidence |
|---|---|---|
| Pure calculation engine | ✅ Built | `grading/engine/` — `compute` / `rank` / `scheme` / `hashing` / `types`; no I/O, no framework imports, Decimal with a pinned `localcontext(prec=50)` so global context can't shift outputs. Enforced by the `engine-is-pure` import-linter contract |
| Versioned grading schemes | ✅ Built | `grading_schemes` row-per-version (migration `0005`): new name → draft v1, same name → next version, activation retires the previous active, retired can't reactivate (409). Engine `validate_scheme` is the single authority (contiguous integer bands 0..100) |
| Processing job + runs | ✅ Built | `POST /assessments/{id}/process` → 202 + durable Job + `queued` run; `grading/jobs.py::process_results` (worker) → `apply_run`: `running` → compute → `succeeded` with `input_hash`; failures settle job AND run from a fresh transaction (with tenant context — see note) |
| Processed results + ranking | ✅ Built | `processed_results` (UNIQUE per run+enrolment, run `ON DELETE CASCADE`); dense/competition ranking; report-card order (position, name) via the results endpoint |
| Run history + recalculation | ✅ Built | `GET /assessments/{id}/processing-runs` newest first; recalculation is an explicit re-POST creating a NEW run; current = latest **succeeded**; failed runs never become current (proven by `TestBlockedRun`) |
| Blocked-run semantics | ✅ Verified live | `missing_policy=block` with an unscored student fails the WHOLE run (error lists the blocked enrolments); the prior successful run stays current untouched |
| Golden example §9.3 end-to-end | ✅ Verified live | Scores via the sheet API, scheme via the grading API, job via the worker entry point, results read back: 78 A / 63 B / 49.5→50 C / 79 A / 72.5→73 A + `renormalised`, dense positions 1–5 |

### Exit criteria

| Criterion | Status | Evidence |
|---|---|---|
| All golden examples pass | ✅ Verified live | Unit `TestGoldenExample` (engine-level) + `TestGoldenFlow.test_golden_example_end_to_end` (HTTP-level, spec §9.3's five students) |
| Boundary and property tests pass | ✅ Verified live | Boundary edges 39/40/44/45/69/70/100; policy matrix; tie policies; rounding-once property (49.5 → 50, 1/3·30 → 10 at full precision) |
| Identical inputs → identical `input_hash` and outputs | ✅ Verified live | Two processing runs: same 64-hex hash, identical result fingerprint, both runs retained |
| Coverage on `grading` ≥ 90% | ✅ Verified live | `pytest tests --cov=app.grading` → **96%** (all files ≥ 86%) |

**Measured gates, 2026-11-11 (final)** (run from `apps/api` with `.venv`):
`ruff check` clean · `ruff format` clean (100 files) · `mypy src/app` → Success (69 files) ·
`lint-imports` 4/4 KEPT · `pytest tests` → **193 passed**, incl. 77 testcontainer-gated tests.

### Phase 4 notes

- The new tests exposed and fixed a **Phase 2 latent bug**: `AuditEvent.actor_ip` was
  `String(45)` against the DDL's `INET` — every ORM audit insert failed. See the
  acceptance record for the full note.
- `pytest-cov` added to the `dev` extra (coverage gate needed a runner).
- Grading consumes `AssessmentService.get_sheet()` (service-interface edge, legal under
  `no-cross-repository`) — one definition of "what is on the sheet", two consumers.
- Worker job failure settlement is RLS-sensitive: `set_tenant_context` before the run
  UPDATE, or the fresh transaction matches zero rows silently.

## Phase 3 status — COMPLETE 2026-11-06

All Phase 3 deliverables are built and all exit criteria verified live (full suite **125 passed**,
including 42 testcontainer tests). Sign-off detail and deviations are in
[`09-phase-acceptance.md`](09-phase-acceptance.md).

### Deliverables

| Deliverable | Status | Evidence |
|---|---|---|
| assessment_templates + versioned definitions | ✅ Built | `assessment/models.py`, migration `0004`; `create_template` makes draft v1, `create_template_version` appends (max+1), edits never rewrite an existing version |
| Version lifecycle (draft → active → retired) | ✅ Built | `activate_template_version`: activates target, retires the template's previous active, retired cannot reactivate (409) |
| assessments (per term/class/section/subject) | ✅ Built | Natural key `UNIQUE NULLS NOT DISTINCT`; creation requires an **active** template version (draft → 422, dup → 409) |
| Score entry with zero vs missing vs absent vs exempt | ✅ Built | `scores` CHECK `(status = 'entered') = (value IS NOT NULL)` — verified at the DB layer with raw SQL; `('entered', 0.00)` round-trips as a real zero |
| Batch upsert (per-cell optimistic concurrency) | ✅ Built | Each row carries `base_version`; stale → conflict; no-op writes bump nothing; web batch is all-or-nothing with every bad cell reported |
| score_changes ledger + `score.changed` outbox | ✅ Built | One ledger row + one outbox event per change, same transaction |
| Bulk import as an async job | ✅ Built | `POST /assessments/{id}/scores/import` → 202 + durable `jobs` row; Arq trigger best-effort (`platform/job_queue.py`); `assessment/jobs.py::import_scores` applies valid rows, reports bad ones per CSV data-row number |
| Teacher entry boundary (exit criterion) | ✅ Verified live | Direct HTTP: assigned-scope teacher outside assignment → 403 on PUT and on import enqueue; with a covering assignment → 200 |

### Exit criteria

| Criterion | Status | Evidence |
|---|---|---|
| DB CHECK blocks invalid zero/missing combinations | ✅ Verified live | `tests/db/test_assessment.py` — 12 passed, raw-SQL inserts against the migrated testcontainer |
| Editing a template creates a new version without altering existing assessments | ✅ Verified live | `TestTemplatesAndVersions` — v2 created as draft, activation retires v1, assessments keep their pinned version |
| Teacher cannot enter scores outside assignment | ✅ Verified live | `TestTeacherScope` — 403 PERMISSION_DENIED over real HTTP with real role grants and RLS tenant context |

**Measured gates, 2026-11-06 (final)** (run from `apps/api` with `.venv`):
`ruff check` clean · `ruff format` clean (87 files) · `mypy src/app` → Success (59 files) ·
`lint-imports` 4/4 KEPT · `pytest tests` → **125 passed**, incl. 42 testcontainer-gated tests.

### Phase 3 notes

- `platform/models.py` annotations moved from the shadowing dialect `UUID` to stdlib
  `uuid.UUID` (runtime-neutral; column types unchanged) — found by mypy on the first run.
- `GET /jobs/{job_id}` lives on the assessment router until a second job producer exists.
- Score writes gate on `scores.enter`; `scores.edit` (edit-after-submit gating) is Phase 5.

## Phase 1 status — COMPLETE 2026-10-27

All Phase 1 deliverables are built and all exit criteria verified live (Docker Desktop now
installed; full suite **68 passed** including the 10 testcontainer tests). Sign-off detail and
the fixes the live run required are in [`09-phase-acceptance.md`](09-phase-acceptance.md).

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
| Last-SA protection (API) | ✅ Verified live | `test_last_sa_protection.py` — 3 passed |
| Last-SA protection (DB trigger) | ✅ Verified live | `test_super_admin_trigger.py` — 5 passed |
| Revoked session fails immediately | ✅ Implemented + verified | `access/dependency.py` checks token_version against Redis cache (30 s TTL); bump verified live |
| Audit chain verifier | ✅ Pass | `pytest tests/unit/test_audit_chain.py -q` |

**Measured gates, 2026-10-27 (final, Docker installed)** (run from `apps/api` with `.venv`):
`ruff check` clean · `ruff format --check` clean · `mypy src/app tests migrations` → Success (64 files) ·
`pytest tests` → **68 passed** (incl. 10 testcontainer tests) in 17.71s.

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
