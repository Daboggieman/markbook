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
| docker compose up | — | — |
| health endpoint | — | — |
| CI green | — | — |
| RLS test (two schools) | — | — |
| OpenAPI at /openapi.json | — | — |

ADRs 001–005 in `docs/adr/`.

---

### Phase 1: Identity, access, audit

**Exit criteria:**
- Authorization matrix tests pass
- Cannot delete or deactivate last Super Admin (API and DB trigger)
- Revoked session fails immediately
- Audit chain verifier passes

| Criterion | Verified | Command + result |
| --- | --- | --- |
| Authorization matrix tests | — | — |
| Super Admin delete block (API) | — | — |
| Super Admin delete block (trigger) | — | — |
| Revoked session fails | — | — |
| Audit chain verifier | — | — |

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

| Criterion | Verified | Command + result |
| --- | --- | --- |
| Security review | — | — |
| Backup restore drill | — | — |
| Load: 500 concurrent teachers | — | — |
| Load: 1,500-student processing | — | — |
| Pilot checklist | — | — |