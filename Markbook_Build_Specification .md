# Markbook: Technical Build Specification

Version 1.0 | Derived from: Consolidated Product and Technical Plan v1.0 | Status: Ready for implementation planning

## 1. Purpose and Key Architectural Decisions

This document turns the product plan into an engineering specification. It is written for a developer or coding agent to build from, phase by phase.

The goal you set: an architecture that is easy to scale. The product plan postpones multi-school tenancy, which is correct for features. But retrofitting tenancy into a finished schema is one of the most painful migrations there is. So this spec makes one deliberate adjustment:

**Single-school features, tenant-ready foundations.** Every tenant-owned table carries a `school_id` from day one. The app runs with exactly one school row at launch. No cross-school features are built. Going multi-school later becomes a configuration and UI task, not a rewrite.

### Decision summary

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

## 2. Scalability Principles (Rules the Code Must Follow)

1. **No in-process state.** No module-level caches of user data, no sticky sessions, no local-disk files. Anything shared lives in Postgres, Redis, or object storage.
2. **No module reaches into another module's tables.** Cross-module access goes through that module's service interface. This is what makes later extraction possible.
3. **Every list endpoint is paginated** (cursor-based) and has a hard max page size.
4. **Every long operation is a job.** Anything over roughly 500 ms of expected work (result processing for a class, bulk import, PDF batch) is enqueued, returns a job id, and is polled.
5. **Every write that can be retried is idempotent** (idempotency key).
6. **Every tenant-owned query is scoped by `school_id`**, enforced by a repository base class plus RLS. Developers cannot forget it.
7. **Schema changes are backward compatible** (expand, migrate, contract), so deploys never require downtime.
8. **Config over code.** Roles, templates, grading rules, and workflow stages are data, not code branches.
9. **Indexes are designed with the schema,** not added after complaints.
10. **Observability from phase 1:** structured logs, request ids, metrics, and error tracking.

### Scaling path (what changes, and when)

| Stage | Trigger | Change |
| --- | --- | --- |
| 0. Launch | One school | One API instance, one worker, managed Postgres, Redis |
| 1. Busy school | Peak load at result time | Run 2 to 4 API instances behind a load balancer; scale workers |
| 2. Read pressure | Reports and dashboards slow | Add a Postgres read replica for reporting queries |
| 3. Multi-school | Second school onboarded | Add tenant admin UI and school onboarding flow; RLS and `school_id` already in place |
| 4. Large multi-school | Thousands of users, heavy reports | Partition large tables (`scores`, `audit_events`) by `school_id` or time; extract Reporting and Sync into separate services if needed |

## 3. System Architecture

```
[Web: React+TS]   [Desktop: Tauri+React+TS]
        \               /
         HTTPS (JWT access + refresh cookie)
                |
         [Load Balancer / TLS]
                |
   [FastAPI API instances x N]  (stateless)
     |        |         |
[Postgres] [Redis]  [Object storage]
     |        |
 [Outbox]  [Job queue] --> [Worker processes x M]
```

### Internal modules (bounded contexts)

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

**Dependency rule:** `platform` depends on nothing. `audit` and `access` may be called by all. Other modules may depend on `people` and `academic` read interfaces, and `workflow` may depend on `grading`. No cycles. Enforce with an import-linter rule in CI.

## 4. Repository Layout

Monorepo.

```
markbook/
  apps/
    api/
      src/app/
        main.py                 # app factory, middleware, routers
        platform/               # config, db, redis, jobs, outbox, logging, errors, pagination, idempotency
        identity/               # router.py, service.py, repository.py, models.py, schemas.py
        access/
        people/
        academic/
        assessment/
        grading/
          engine/               # PURE calculation engine, no imports from app
        workflow/
        documents/
        sync/
        audit/
      migrations/               # Alembic
      tests/
        unit/ api/ workflow/ sync/ security/ conftest.py
      pyproject.toml
    worker/                     # entrypoint that imports api modules and runs jobs
    web/                        # React + TS (Vite)
    desktop/                    # Tauri shell wrapping the web UI + local sync layer
  packages/
    api-client/                 # generated TS client from OpenAPI
    ui/                         # shared components
    rules/                      # shared validation helpers (UI hints only, never authoritative)
  infra/
    docker/ compose.dev.yml terraform-or-equivalent/ runbooks/
  docs/
    adr/                        # architecture decision records
    threat-model.md
  .github/workflows/            # CI
```

Each backend module has the same internal shape: `router.py` (HTTP only), `service.py` (business logic, transactions), `repository.py` (SQL, always tenant-scoped), `models.py` (SQLAlchemy), `schemas.py` (Pydantic). Routers never touch repositories directly.

## 5. Multi-Tenancy Readiness

- `schools` table with one seeded row.
- Every tenant-owned table has `school_id UUID NOT NULL REFERENCES schools(id)` and an index starting with `school_id`.
- Request context carries `school_id` (derived from the authenticated user, never from client input).
- The DB session sets `SET LOCAL app.school_id = '<uuid>'` at transaction start. RLS policies on every tenant table: `USING (school_id = current_setting('app.school_id')::uuid)`.
- The application DB role is not a superuser and does not bypass RLS. Migrations and ops use a separate role.
- Uniqueness rules are composite with `school_id` (for example, admission number unique per school).
- Primary keys are UUIDv7 (time-ordered): index-friendly, safe to expose, merge-safe across schools later.

## 6. Database Design

Conventions: UUIDv7 PKs; `created_at`, `updated_at`; `version INT` for optimistic concurrency on mutable records; archive via `archived_at` (no hard deletes for academic data); timestamps are `timestamptz` in UTC; scores are `NUMERIC(6,2)`.

### 6.1 Identity and access

```sql
schools(id, name, config JSONB, created_at)

users(id, school_id, email CITEXT, username, password_hash, is_super_admin BOOL,
      status ENUM('active','suspended','deactivated'), mfa_enabled BOOL,
      failed_login_count INT, locked_until TIMESTAMPTZ, token_version INT,
      created_at, updated_at, version)
  UNIQUE (school_id, email)

sessions(id, user_id, device_id NULL, refresh_token_hash, issued_at, expires_at,
         revoked_at, ip INET, user_agent)

devices(id, user_id, school_id, label, registered_at, last_sync_at, revoked_at)

roles(id, school_id, name, is_system BOOL, description)  UNIQUE (school_id, name)
permissions(code PK, description)                         -- global catalogue, seeded
role_permissions(role_id, permission_code, scope_type ENUM('school','assigned','own'))
user_roles(user_id, role_id, granted_by, granted_at)
```

Scope model: `role_permissions.scope_type` expresses breadth. `school` means all records. `assigned` means only records tied to the user's `teacher_assignments`. `own` means records the user created. Narrower, record-specific scope (individual classes) is resolved through `teacher_assignments`, so no separate scope table is needed in v1. If you later need arbitrary scopes, add `permission_scopes` without changing the check interface.

Protected Super Admin rules are enforced in `access.service` and by a DB trigger that blocks deleting, deactivating, or demoting the last active Super Admin.

### 6.2 People

```sql
students(id, school_id, system_id TEXT UNIQUE-per-school, admission_no, first_name,
         middle_name, last_name, dob DATE, sex, status ENUM('active','graduated','withdrawn','archived'),
         archived_at, created_at, updated_at, version)
  UNIQUE (school_id, admission_no) WHERE admission_no IS NOT NULL
  INDEX  (school_id, last_name, first_name)
  INDEX  trigram on (first_name || ' ' || last_name) for duplicate detection

guardians(id, school_id, name, phone, email, address)
student_guardians(student_id, guardian_id, relationship, is_primary)
```

Duplicate detection: before create, query by normalized name plus DOB with pg\_trgm similarity; if any candidate scores above threshold, the API returns `409 POSSIBLE_DUPLICATE` with candidates; the client resubmits with `confirm_not_duplicate=true`.

### 6.3 Academic structure

```sql
academic_sessions(id, school_id, name, start_date, end_date, is_current)
terms(id, school_id, session_id, name, ordinal, start_date, end_date, is_current)
educational_levels(id, school_id, name, ordinal)          -- Nursery, Primary, JSS, SS
classes(id, school_id, level_id, name, ordinal)           -- JSS 1, SS 2 ...
sections(id, school_id, class_id, name)                   -- A, B, Science ...
subjects(id, school_id, name, code)
class_subjects(id, school_id, class_id, subject_id, is_optional BOOL)

enrolments(id, school_id, student_id, session_id, class_id, section_id,
           status ENUM('enrolled','promoted','repeated','graduated','withdrawn'),
           started_on, ended_on)
  UNIQUE (student_id, session_id) WHERE status='enrolled'

subject_enrolments(id, school_id, enrolment_id, class_subject_id)
teacher_assignments(id, school_id, teacher_user_id, session_id, class_id, section_id NULL, subject_id, role ENUM('subject','form'))
  INDEX (school_id, teacher_user_id, session_id)
promotion_records(id, school_id, student_id, from_enrolment_id, to_enrolment_id, decision, decided_by, decided_at)
```

Historical context: results reference `enrolment_id` and `class_subject_id`, never a mutable "current class". Promoting a student creates a new enrolment; old results stay attached to the old one.

### 6.4 Assessment and scores

```sql
assessment_templates(id, school_id, name, created_by)
assessment_template_versions(id, school_id, template_id, version_no, status ENUM('draft','active','retired'),
                             definition JSONB, created_at, created_by)
  -- definition: components [{key,label,max_score,weight,required}], active versions are IMMUTABLE

assessments(id, school_id, term_id, class_id, section_id NULL, subject_id,
            template_version_id, workflow_state, version)
  UNIQUE (school_id, term_id, class_id, subject_id, section_id)

scores(id, school_id, assessment_id, subject_enrolment_id, component_key,
       status ENUM('entered','absent','exempt','missing'),
       value NUMERIC(6,2) NULL, entered_by, entered_at, updated_by, updated_at, version,
       CHECK ((status='entered') = (value IS NOT NULL)))
  UNIQUE (assessment_id, subject_enrolment_id, component_key)
  INDEX  (school_id, assessment_id)

score_changes(id, school_id, score_id, old_status, old_value, new_status, new_value,
              reason, changed_by, changed_at, source ENUM('web','desktop_sync','import'))
```

The `CHECK` constraint is the database-level guarantee that zero is distinct from missing: `entered` with value `0.00` is a real zero; `missing` has NULL.

### 6.5 Grading, results, workflow

```sql
grading_schemes(id, school_id, name, version_no, status, definition JSONB)
  -- definition: rounding, missing_policy, absent_policy, exempt_policy, boundaries [{grade,min,max,remark}], tie_policy

result_processing_runs(id, school_id, assessment_id, scheme_id, scheme_version, template_version_id,
                       status ENUM('queued','running','succeeded','failed'),
                       input_hash TEXT, started_at, finished_at, requested_by)
processed_results(id, school_id, run_id, subject_enrolment_id, total NUMERIC(6,2),
                  grade TEXT, position INT NULL, breakdown JSONB, flags JSONB)
  INDEX (school_id, run_id)

workflow_definitions(id, school_id, name, stages JSONB)   -- configurable stage list + required permissions
approval_records(id, school_id, assessment_id, from_state, to_state, actor_id, reason, at)
published_documents(id, school_id, assessment_id NULL, enrolment_id NULL, kind, doc_version INT,
                    supersedes_id NULL, storage_key, checksum, published_by, published_at, correction_reason)
```

### 6.6 Audit and sync

```sql
audit_events(id, school_id, at, actor_id NULL, actor_ip, action TEXT, entity_type, entity_id,
             before JSONB NULL, after JSONB NULL, reason TEXT NULL, request_id, prev_hash BYTEA, hash BYTEA)
  -- append-only: app role has INSERT only; no UPDATE/DELETE grants

sync_operations(id, school_id, device_id, user_id, idempotency_key UNIQUE, op_type, payload JSONB,
                base_version INT NULL, status ENUM('applied','conflict','rejected','duplicate'),
                result JSONB, received_at, processed_at)

outbox_events(id, school_id, topic, payload JSONB, created_at, dispatched_at NULL)
```

Audit hash chain: each event stores `hash = SHA256(prev_hash || canonical_json(event))`. A nightly job verifies the chain; a break raises an alert. This makes tampering detectable.

## 7. Authentication and Authorization

### 7.1 Authentication

- Passwords hashed with Argon2id (tuned parameters in config).
- Access token: short-lived JWT (10 to 15 minutes) carrying `sub`, `school_id`, `token_version`, `session_id`. Refresh token: opaque random value stored hashed in `sessions`, rotated on every use, httpOnly secure cookie on web; OS keychain on desktop.
- Refresh token reuse detection: reuse of a rotated token revokes the whole session family.
- Revocation: bumping `users.token_version` or setting `sessions.revoked_at` invalidates tokens. Middleware checks `token_version` through a short Redis cache (30 s TTL) to avoid a DB hit on every request.
- Login throttling: Redis counters per (username, IP) and per IP; exponential backoff plus `locked_until`.
- Re-authentication: sensitive endpoints require a `reauth_at` claim within the last 5 minutes (step-up).
- MFA: TOTP, mandatory for Super Admin and any role holding `results.publish`, `roles.manage`, `permissions.manage`.

### 7.2 Authorization engine

One function, used everywhere:

```python
authorize(actor, permission: str, resource: ResourceRef | None) -> Decision
```

Steps:

1. Load the actor's effective permissions (cached per `token_version`).
2. If no role grants `permission`, deny.
3. Take the broadest granted scope. If `school`, allow.
4. If `assigned`, check that `resource` resolves to a class/section/subject present in the actor's `teacher_assignments` for the relevant session. Deny if no resource is supplied for a scoped permission.
5. If `own`, check `resource.created_by == actor.id`.
6. Return the decision and write an audit event for denials on sensitive permissions.

Enforcement: a FastAPI dependency `require(permission, resource_loader)` is mandatory on every route. A CI test iterates all registered routes and fails if any route lacks a `require` dependency or an explicit `@public` marker. List queries apply the same scope as a SQL filter (`scope_filter(actor, permission)`), so teachers never receive rows outside their assignments.

## 8. API Conventions

- Base path `/api/v1`. Versioning by path; breaking changes require `/v2`.
- JSON; ISO 8601 UTC timestamps.
- Errors: RFC 7807 problem details with stable machine codes (`PERMISSION_DENIED`, `VERSION_CONFLICT`, `VALIDATION_ERROR`, `INVALID_STATE_TRANSITION`, `POSSIBLE_DUPLICATE`, `RATE_LIMITED`).
- Pagination: `?limit=50&cursor=...`, max limit 200. Response `{items, next_cursor}`.
- Optimistic concurrency: mutable resources return `ETag`/`version`; updates require `If-Match` or `version` in the body; mismatch returns `409 VERSION_CONFLICT`.
- Idempotency: all POSTs that create or transition accept `Idempotency-Key`. Stored 24 h in Redis plus durable record for sync operations.
- Every request gets an `X-Request-Id`, echoed in logs and audit events.
- Long operations return `202 Accepted` with `{job_id, status_url}`.

### Endpoint groups (contract summary)

| Group | Key endpoints | Permission |
| --- | --- | --- |
| Auth | `POST /auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/mfa/verify`, `/auth/reauth` | public / session |
| Users | `GET/POST /users`, `GET/PATCH /users/{id}`, `POST /users/{id}/suspend`, `POST /users/{id}/revoke-sessions` | `users.*` |
| Roles | `GET/POST /roles`, `PUT /roles/{id}/permissions` | `roles.manage`, `permissions.manage` |
| Students | `GET/POST /students`, `GET/PATCH /students/{id}`, `POST /students/{id}/archive`, `POST /students/check-duplicates` | `students.*` |
| Academic | `/academic-sessions`, `/terms`, `/classes`, `/sections`, `/subjects`, `/enrolments`, `/teacher-assignments`, `POST /promotions/run` | `*.manage` |
| Templates | `/assessment-templates`, `POST /assessment-templates/{id}/versions`, `POST /template-versions/{id}/activate` | `assessments.manage` |
| Assessments | `GET /assessments` (scope filtered), `GET /assessments/{id}/sheet` | `assessments.view` |
| Scores | `PUT /assessments/{id}/scores` (batch upsert), `POST /assessments/{id}/scores/import`, `GET /scores/{id}/history` | `scores.enter`, `scores.edit` |
| Workflow | `POST /assessments/{id}/submit`, `/start-review`, `/return`, `/approve`, `/lock`, `/publish`, `/correct` | `scores.submit`, `scores.review`, `results.*` |
| Results | `POST /assessments/{id}/process` (202), `GET /assessments/{id}/results`, `GET /jobs/{id}` | `results.process` |
| Documents | `POST /documents/report-cards` (202), `GET /documents/{id}/download` | `reports.view`, `transcripts.generate` |
| Audit | `GET /audit-events` | `audit_logs.view` |
| Sync | `POST /sync/devices/register`, `GET /sync/bootstrap`, `POST /sync/push`, `GET /sync/pull?since=...` | `scores.enter` + device check |

Full request/response schemas are Pydantic models; the OpenAPI document is the contract of record and is diffed in CI to flag breaking changes.

## 9. Result Calculation Engine

Location: `apps/api/src/app/grading/engine/`. Pure functions, no I/O, no framework imports, `Decimal` arithmetic only (never float).

### 9.1 Inputs and outputs

```python
compute(student_scores: list[ScoreInput], template: TemplateDef, scheme: SchemeDef) -> ComputedResult
rank(results: list[ComputedResult], scheme: SchemeDef) -> list[RankedResult]
```

### 9.2 Algorithm

1. For each component, resolve status: `entered`, `absent`, `exempt`, `missing`.
2. Apply policies from the scheme:
   - `missing_policy`: `block` (cannot process), `treat_zero`, or `flag_incomplete`.
   - `absent_policy`: `treat_zero` or `exclude_and_renormalise`.
   - `exempt_policy`: `exclude_and_renormalise` (default).
3. Component contribution = `(value / max_score) * weight`, kept at full precision.
4. Total = sum of contributions (if excluded components exist, renormalise: `sum / sum_of_included_weights * 100`).
5. Round once, at the end, using the scheme's rounding mode (default `ROUND_HALF_UP`, 0 decimal places) to the scheme's precision.
6. Grade = first boundary where `min <= total <= max`. Boundaries must be validated at scheme creation to be contiguous and non-overlapping across 0 to 100.
7. Positions: dense or competition ranking per `tie_policy`; ties share a position.
8. Output includes the full `breakdown` and any `flags` (incomplete, renormalised).

### 9.3 Worked example

Template (weights sum to 100): CA1 max 10 weight 10; CA2 max 10 weight 10; Test max 20 weight 20; Exam max 60 weight 60. Scheme: rounding HALF\_UP to 0 dp; absent policy `treat_zero`; boundaries A 70-100, B 60-69, C 50-59, D 45-49, E 40-44, F 0-39.

| Student | CA1 | CA2 | Test | Exam | Computation | Total | Grade |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Ada | 8 | 7 | 15 | 48 | 8 + 7 + 15 + 48 | 78 | A |
| Bayo | 6 | 5 | 12 | 40 | 6 + 5 + 12 + 40 | 63 | B |
| Chidi | 5 | 4.5 | 9 | 31 | 5 + 4.5 + 9 + 31 = 49.5 | 50 (HALF\_UP) | C |
| Dara | 9 | absent | 18 | 52 | 9 + 0 + 18 + 52 | 79 | A |
| Efe | 7 | 6 | exempt | 45 | contributions 7 + 6 + 45 = 58 over included weight 80, so 58 / 80 \* 100 | 72.5 rounds to 73 | A |

Chidi demonstrates that rounding happens once at the end, so 49.5 becomes 50 (grade C), not 49. These rows, plus boundary edge values (39, 40, 44, 45, 69, 70, 100), become the first golden tests.

### 9.4 Determinism and recalculation

- Each processing run stores `template_version_id`, `scheme_id`, `scheme_version`, and an `input_hash` of all scores consumed. Same inputs and versions always produce byte-identical `processed_results`.
- Editing a template or scheme creates a new version. Existing runs are untouched.
- Recalculation is an explicit action (`POST /process` with a chosen version), creates a new run, and is audited. The latest successful run for an assessment is the "current" one; older runs are retained.

## 10. Workflow State Machine

Default states per assessment (result set): `DRAFT -> SUBMITTED -> UNDER_REVIEW -> APPROVED -> LOCKED -> PUBLISHED`, plus `RETURNED` (back to editing).

| From | To | Action | Required permission | Constraints |
| --- | --- | --- | --- | --- |
| DRAFT | SUBMITTED | submit | `scores.submit` (scoped) | All required components resolved (no `missing` unless policy allows); validation passes |
| SUBMITTED | UNDER\_REVIEW | start-review | `scores.review` | Reviewer is not the submitter |
| UNDER\_REVIEW | RETURNED | return | `scores.review` | Reason required |
| RETURNED | SUBMITTED | resubmit | `scores.submit` | Fresh submission and fresh review |
| UNDER\_REVIEW | APPROVED | approve | `results.approve` | A successful processing run exists and is current |
| APPROVED | LOCKED | lock | `results.lock` | Online only; re-auth |
| LOCKED | PUBLISHED | publish | `results.publish` | Online only; re-auth; MFA; generates documents |
| PUBLISHED | PUBLISHED (v+1) | correct | `results.correct` | Reason required; creates corrected document version, supersedes the old one, never overwrites |

Implementation notes:

- The transition table lives in code as data (`TRANSITIONS`) combined with per-school `workflow_definitions` that can add or skip optional intermediate stages and set required permissions. Mandatory invariants (permission check, audit event, no silent change, locks block edits) are not configurable.
- Every transition runs in one DB transaction: row lock on the assessment (`SELECT ... FOR UPDATE`), state check, permission check, side effects, `approval_records` insert, `audit_events` insert, `outbox_events` insert.
- Score edits are only allowed in `DRAFT` and `RETURNED`. Edits in later states are rejected; post-publication change goes only through `correct`.
- Invalid transitions return `409 INVALID_STATE_TRANSITION`.
- Separation of duties (submitter cannot approve own work) is a configurable rule, on by default.

## 11. Offline Desktop Sync Protocol

Scope: offline is limited to entering CA scores. Everything else is online-only.

### 11.1 Device lifecycle

1. User logs in online; `POST /sync/devices/register` creates a `devices` row and returns a device id and a per-device key.
2. `GET /sync/bootstrap` returns the minimum data for the user's scope: assigned assessments in editable states, their rosters (subject enrolments), template version definitions, and current score rows with versions.
3. Local store: SQLite file encrypted at rest (SQLCipher or an OS-keychain-wrapped key). Tables: `cache_*` (bootstrap data), `pending_ops` (queue), `meta` (cursor, device id).
4. On logout, device revocation (server returns `DEVICE_REVOKED`), or repeated auth failure, the local database is wiped.

### 11.2 Offline operations

Each local score edit becomes an operation:

```json
{
  "idempotency_key": "uuid",
  "op_type": "score.upsert",
  "assessment_id": "...",
  "subject_enrolment_id": "...",
  "component_key": "CA1",
  "status": "entered",
  "value": "8.00",
  "base_version": 3,
  "client_time": "2026-10-20T09:15:00Z"
}
```

`base_version` is the score row version the user last saw. Operations for the same cell collapse locally to the latest one before sync.

### 11.3 Push and server handling

`POST /sync/push` accepts an ordered batch. For each op, in its own savepoint:

1. Duplicate check: if `idempotency_key` already exists, return the stored result with status `duplicate`. No re-apply.
2. Device check: device must be active and belong to the user.
3. Re-authorise: `scores.enter` with scope against the assessment.
4. State check: assessment must still be in an editable state; otherwise `rejected: ASSESSMENT_NOT_EDITABLE`.
5. Validate value against the pinned template version (range, status rules).
6. Version check: if the server score's version differs from `base_version`, return `conflict` with the current server value. Never overwrite.
7. Otherwise apply, write `score_changes` (source `desktop_sync`) and an audit event, return `applied` with new version.

Results are persisted in `sync_operations` so retries return identical responses.

### 11.4 Conflict resolution

The client shows both values (mine vs server, with who changed it and when). The user picks one; the client sends a new op with `base_version` set to the server's current version and a `resolution` note. Auto-merge is never used for score values.

### 11.5 Pull

`GET /sync/pull?since=<cursor>` returns changed rows within scope (using an `updated_at, id` cursor) and tombstones for removed assignments. Revoked scope removes cached data locally.

## 12. Background Jobs and Events

- Queue: Redis-backed (Arq or RQ; choose one and record in an ADR). Workers are the same codebase, started with a different entrypoint.
- Job table: `jobs(id, school_id, type, status, params, result, error, created_by, created_at, finished_at)` so job status survives Redis loss.
- Job types: `results.process`, `scores.import`, `documents.report_cards`, `documents.transcript`, `audit.verify_chain`, `retention.cleanup`.
- Jobs are idempotent and re-runnable; they take row locks and check state at start.
- Outbox dispatcher: a worker polls `outbox_events` (using `FOR UPDATE SKIP LOCKED`), delivers to in-process handlers, and marks dispatched. Topics at launch: `assessment.state_changed`, `results.published`, `score.changed`. This is the seam where a broker such as RabbitMQ or Kafka plugs in later, and where parent notifications attach in the future.

## 13. Security and Threat Model

### 13.1 Controls checklist

- TLS everywhere; HSTS; secure cookies; strict CORS allowlist; CSP on web; security headers.
- Secrets from environment or a secret manager, never in the repo; pre-commit secret scanning.
- SQLAlchemy parameterised queries only; no string-built SQL.
- Pydantic validation on every input; request size limits; file upload type and size checks and virus scanning for imports.
- Rate limits: auth endpoints strict; sensitive endpoints (publish, export, role changes) moderate; global per-user default.
- Logs scrub passwords, tokens, and personal data fields by an allowlist logger.
- Backups encrypted, off-site, restore tested on a schedule (quarterly minimum, plus before each major release).
- Exports and downloads: signed short-lived URLs; each download audited; retention window defined and enforced by `retention.cleanup`.
- Dependency and container scanning in CI.

### 13.2 Threat model (STRIDE summary)

| Threat | Example | Mitigation |
| --- | --- | --- |
| Spoofing | Stolen password | Argon2id, MFA for privileged roles, throttling, session revocation |
| Tampering | Teacher edits another class's scores via API | Server-side scoped authorize on every route, RLS, route-coverage CI test |
| Tampering | Silent change to published result | Edit blocked after submit; corrections create new document versions; audit hash chain |
| Repudiation | "I didn't change that score" | `score_changes` and tamper-evident audit events with actor, time, IP, reason |
| Information disclosure | Student data in logs or exports | Log scrubbing, scoped queries, signed URLs, export audit |
| Information disclosure | Lost laptop with cached data | Encrypted local DB, device revocation wipe, minimal cache scope |
| Denial of service | Login flood, huge imports | Rate limits, upload limits, jobs for heavy work |
| Elevation of privilege | Admin weakens Super Admin | Protected role rules in service layer and DB trigger |
| Replay | Resent sync batch | Idempotency keys, server-side dedupe |

Maintain the full model in `docs/threat-model.md` and review it before every production release.

## 14. Testing Strategy

| Layer | Tooling | Must cover |
| --- | --- | --- |
| Engine unit tests | pytest, hypothesis | Golden examples from section 9.3; every boundary value; rounding modes; missing, absent, exempt policies; ties; property test that grade is always found and total stays within 0 to 100 |
| Repository/DB tests | pytest + real Postgres (testcontainers) | Constraints (zero vs missing CHECK, uniqueness), RLS isolation between two test schools, audit append-only grants |
| API tests | pytest + httpx | Every route: unauthenticated, wrong permission, wrong scope, valid; validation errors; pagination; idempotency |
| Authorization matrix | parametrised | Teacher A cannot read or write teacher B's class or subject; scoped list filtering |
| Workflow tests | pytest | Every legal transition; every illegal transition; separation of duties; edit blocked after submit; correction versioning |
| Sync tests | pytest | Duplicate op, retry after timeout, conflict, revoked device, revoked permission, locked assessment, stale base version |
| Route-coverage guard | CI test | Fails if any route lacks `require(...)` or `@public` |
| Frontend | Vitest + Testing Library | Score sheet validation UX, conflict dialog |
| E2E | Playwright | Teacher enters and submits; reviewer returns; admin approves, locks, publishes; correction after publish |
| Load | k6 | 500 concurrent teachers entering scores; result processing for a 1,500-student term |
| Operational | scripted | Backup restore into a clean environment and verification query suite |

CI gates: lint (ruff, mypy strict on `grading` and `access`), import-linter, tests with coverage minimum (90% on `grading`, `access`, `workflow`), OpenAPI breaking-change check, dependency scan.

## 15. Deployment and Operations

- Environments: `dev` (docker compose), `staging` (production-like, anonymised data), `prod`.
- Containers: one image, entrypoints `api` and `worker`. Run migrations as a release step before new instances take traffic.
- Hosting: managed Postgres with PITR backups and automated daily snapshots; managed Redis; S3-compatible storage; container platform with autoscaling on CPU and request latency; TLS terminated at the load balancer.
- Database connections: pooled (PgBouncer or provider pooler); API instances limited so total connections stay under the database limit.
- Zero-downtime releases: rolling deploys; migrations follow expand-migrate-contract.
- Observability: structured JSON logs with request id; metrics (latency, error rate, queue depth, job duration, sync conflict rate); error tracking; alerts on failed jobs, audit chain break, backup failure, and elevated 5xx.
- Runbooks (in `infra/runbooks/`): restore from backup, rotate secrets, revoke a compromised account or device, rerun a failed processing job, roll back a release.
- Backup policy: daily full plus continuous WAL; retention defined by school policy; restore drill documented with timings (RTO and RPO recorded).

## 16. Phased Build Plan with Completion Criteria

**Start of every phase: verification step.** Before building anything in a phase, run the check below to confirm what is already done, and only implement what is missing. Never assume a prior phase is complete because it was planned.

Verification step template (per phase):

1. List the phase's deliverables.
2. For each, confirm it exists (file, migration, route, test) and passes (`pytest -q`, `alembic upgrade head` on a clean DB, `ruff`, `mypy`).
3. Record the result as Done, Partial, or Missing.
4. Implement only Partial and Missing items, then re-run the phase exit checks.

### Phase 0: Foundations

Deliver: monorepo, docker compose (api, worker, postgres, redis, minio), config system, DB session with tenant context, Alembic baseline (`schools`, `audit_events`, `outbox_events`, `jobs`), logging with request ids, error format, pagination and idempotency helpers, CI pipeline, import-linter, ADRs 001 to 005. Exit: `docker compose up` works; health endpoint passes; CI green; RLS test with two schools passes; OpenAPI served.

### Phase 1: Identity, access, audit

Deliver: users, sessions, devices, roles, permissions seed, authorization engine, `require` dependency, route-coverage guard, login throttling, refresh rotation and reuse detection, MFA (TOTP), Super Admin protections, audit service with hash chain. Exit: authorization matrix tests pass; cannot delete or deactivate last Super Admin (API and DB trigger); revoked session fails immediately; audit chain verifier passes.

### Phase 2: People and academic structure

Deliver: students, guardians, duplicate detection, academic sessions, terms, levels, classes, sections, subjects, class\_subjects, enrolments, subject enrolments, teacher assignments, promotions, Nigerian default seed (Nursery, Primary 1 to 6, JSS 1 to 3, SS 1 to 3). Exit: student archive preserves history; promotion keeps old results context; scoped student lists respect teacher assignments; migrations apply on a clean DB.

### Phase 3: Assessment templates and score entry

Deliver: versioned templates (immutable once active), assessments, score batch upsert, zero vs missing vs absent vs exempt, `score_changes`, bulk import (as a job with row-level error report), validation. Exit: DB CHECK blocks invalid zero/missing combinations; editing a template creates a new version without altering existing assessments; teacher cannot enter scores outside assignment (tested via direct API).

### Phase 4: Calculation engine and processing

Deliver: pure engine, grading schemes (versioned), processing job, processed results, ranking, run history, recalculation action. Exit: all golden examples in section 9.3 pass; boundary and property tests pass; identical inputs produce identical `input_hash` and outputs; coverage on `grading` is at least 90%.

### Phase 5: Workflow, locking, publication, corrections, documents

Deliver: state machine with configurable stages, approval records, locks, publication with PDF generation job, report cards, transcripts, correction versioning, step-up auth and MFA on publish. Exit: every illegal transition rejected; edits blocked after submit; published documents immutable and corrections create a superseding version; every action present in the audit log.

### Phase 6: Web client

Deliver: React app with generated API client, auth flows, admin screens, score sheets with keyboard-friendly entry, review and approval screens, reports. Exit: Playwright E2E for teacher and admin flows pass; UI hides unauthorised actions but backend tests prove enforcement independently.

### Phase 7: Desktop client and sync

Deliver: Tauri shell, encrypted local store, bootstrap, offline queue, push/pull, conflict UI, device registration and revocation wipe. Exit: all sync tests in section 14 pass; duplicate prevention proven; revoked device wipes local data on next contact; online-only actions disabled offline.

### Phase 8: Hardening and pilot

Deliver: security review against the threat model, load tests, backup restore drill, runbooks, staging soak, production deployment, pilot rollout plan. Exit: no known critical security issues; restore drill succeeded with recorded RTO/RPO; load targets met; pilot checklist signed off.

## 17. Coding-Agent Instructions

Give the following to any coding agent as standing rules.

1. **Work one phase at a time.** Begin with the phase verification step. Do not start a later phase until the current phase exit criteria pass.
2. **Never put business rules in clients.** Permissions, calculations, workflow transitions, and locking live only in the backend.
3. **Every route must declare `require(...)` or `@public`.** The route-coverage test must stay green.
4. **Every tenant table needs `school_id`, a leading-`school_id` index, and an RLS policy.** Never read `school_id` from request input.
5. **Respect module boundaries.** Call other modules through their `service` interfaces only; keep import-linter passing.
6. **Use `Decimal` for scores and totals.** Never `float`.
7. **Never hard-delete academic data.** Archive.
8. **Never edit an applied migration.** Add a new one. Use expand-migrate-contract.
9. **Every state-changing action writes an audit event in the same transaction.**
10. **Write tests first for the engine, authorization, and workflow.** Add a test for every bug fix.
11. **Do not log secrets or personal data.**
12. **Do not add features outside the initial scope** (no fees, attendance, portals, multi-school UI) without an ADR.
13. **Record non-trivial decisions as ADRs** in `docs/adr/`.
14. **At the end of each phase,** report: deliverables done, tests added and passing, known gaps, and any deviations from this spec.

## 18. Open Decisions to Resolve Before or During Phase 0

| # | Question | Default if undecided |
| --- | --- | --- |
| 1 | Hosting provider and region (latency and data-residency considerations for Nigeria) | Managed Postgres and containers in the nearest low-latency region with a Nigeria-friendly provider |
| 2 | Job queue library | Arq |
| 3 | PDF generation approach | WeasyPrint (HTML to PDF) in worker |
| 4 | Exact retention periods for audit logs, exports, and archived students | Set by school policy; configurable per school |
| 5 | Whether separation of duties (submitter cannot approve) is strict | On by default, configurable |
| 6 | Local encryption method on desktop | SQLCipher with key held in OS keychain |
| 7 | Product name | Decided: Markbook. Package names stay neutral so a future rename stays cheap |
