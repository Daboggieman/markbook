# Markbook — Build Roadmap

Source of record: spec §16 (Phased Build Plan with Completion Criteria). This doc restates the
phases and their exit criteria; the per-phase deliverable detail is in the spec.

**Start of every phase: verification step.** Before building anything in a phase, run the check
below to confirm what is already done, and only implement what is missing. Never assume a prior
phase is complete because it was planned.

## Verification step template (per phase)

1. List the phase's deliverables.
2. For each, confirm it exists (file, migration, route, test) and passes (`pytest -q`,
   `alembic upgrade head` on a clean DB, `ruff`, `mypy`).
3. Record the result as Done, Partial, or Missing.
4. Implement only Partial and Missing items, then re-run the phase exit checks.

## The phases

### Phase 0: Foundations

Deliver: monorepo, docker compose (api, worker, postgres, redis, minio), config system, DB
session with tenant context, Alembic baseline (`schools`, `audit_events`, `outbox_events`,
`jobs`), logging with request ids, error format, pagination and idempotency helpers, CI
pipeline, import-linter, ADRs 001 to 005.

**Exit:** `docker compose up` works; health endpoint passes; CI green; RLS test with two
schools passes; OpenAPI served.

### Phase 1: Identity, access, audit

Deliver: users, sessions, devices, roles, permissions seed, authorization engine, `require`
dependency, route-coverage guard, login throttling, refresh rotation and reuse detection, MFA
(TOTP), Super Admin protections, audit service with hash chain.

**Exit:** authorization matrix tests pass; cannot delete or deactivate last Super Admin (API
and DB trigger); revoked session fails immediately; audit chain verifier passes.

### Phase 2: People and academic structure

Deliver: students, guardians, duplicate detection, academic sessions, terms, levels, classes,
sections, subjects, class_subjects, enrolments, subject enrolments, teacher assignments,
promotions, Nigerian default seed (Nursery, Primary 1 to 6, JSS 1 to 3, SS 1 to 3).

**Exit:** student archive preserves history; promotion keeps old results context; scoped
student lists respect teacher assignments; migrations apply on a clean DB.

### Phase 3: Assessment templates and score entry

Deliver: versioned templates (immutable once active), assessments, score batch upsert, zero vs
missing vs absent vs exempt, `score_changes`, bulk import (as a job with row-level error
report), validation.

**Exit:** DB CHECK blocks invalid zero/missing combinations; editing a template creates a new
version without altering existing assessments; teacher cannot enter scores outside assignment
(tested via direct API).

### Phase 4: Calculation engine and processing

Deliver: pure engine, grading schemes (versioned), processing job, processed results, ranking,
run history, recalculation action.

**Exit:** all golden examples from §9.3 pass; boundary and property tests pass; identical
inputs produce identical `input_hash` and outputs; coverage on `grading` is at least 90%.

### Phase 5: Workflow, locking, publication, corrections, documents

Deliver: state machine with configurable stages, approval records, locks, publication with PDF
generation job, report cards, transcripts, correction versioning, step-up auth and MFA on
publish.

**Exit:** every illegal transition rejected; edits blocked after submit; published documents
immutable and corrections create a superseding version; every action present in the audit log.

### Phase 6: Web client

Deliver: React app with generated API client, auth flows, admin screens, score sheets with
keyboard-friendly entry, review and approval screens, reports.

**Exit:** Playwright E2E for teacher and admin flows pass; UI hides unauthorised actions but
backend tests prove enforcement independently.

### Phase 7: Desktop client and sync

Deliver: Tauri shell, encrypted local store, bootstrap, offline queue, push/pull, conflict UI,
device registration and revocation wipe.

**Exit:** all sync tests pass (see [`05-testing-strategy.md`](05-testing-strategy.md));
duplicate prevention proven; revoked device wipes local data on next contact; online-only
actions disabled offline.

### Phase 8: Hardening and pilot

Deliver: security review against the threat model, load tests, backup restore drill, runbooks,
staging soak, production deployment, pilot rollout plan.

**Exit:** no known critical security issues; restore drill succeeded with recorded RTO/RPO;
load targets met; pilot checklist signed off.

## Current status

Planning phase. Phase 0 not started. The running record of where the build actually is lives in
[`../handover_docs/01-current-state.md`](../handover_docs/01-current-state.md) — this roadmap
holds the plan, never the status.
