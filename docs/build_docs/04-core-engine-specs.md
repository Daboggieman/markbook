# Markbook — Core Engine Specs

Three components are specified to a level of detail where implementation must follow the text
closely. This doc reproduces that text. Source of record: spec §9 (Result Calculation Engine),
§10 (Workflow State Machine), §11 (Offline Desktop Sync Protocol).

---

# 9. The result calculation engine

Location: `apps/api/src/app/grading/engine/`. **Pure functions, no I/O, no framework imports,
`Decimal` arithmetic only (never float).**

## 9.1 Inputs and outputs

```python
compute(student_scores: list[ScoreInput], template: TemplateDef, scheme: SchemeDef) -> ComputedResult
rank(results: list[ComputedResult], scheme: SchemeDef) -> list[RankedResult]
```

## 9.2 Algorithm

1. For each component, resolve status: `entered`, `absent`, `exempt`, `missing`.
2. Apply policies from the scheme:
   - `missing_policy`: `block` (cannot process), `treat_zero`, or `flag_incomplete`.
   - `absent_policy`: `treat_zero` or `exclude_and_renormalise`.
   - `exempt_policy`: `exclude_and_renormalise` (default).
3. Component contribution = `(value / max_score) * weight`, kept at full precision.
4. Total = sum of contributions (if excluded components exist, renormalise:
   `sum / sum_of_included_weights * 100`).
5. **Round once, at the end,** using the scheme's rounding mode (default `ROUND_HALF_UP`,
   0 decimal places) to the scheme's precision.
6. Grade = first boundary where `min <= total <= max`. Boundaries must be validated at scheme
   creation to be contiguous and non-overlapping across 0 to 100.
7. Positions: dense or competition ranking per `tie_policy`; ties share a position.
8. Output includes the full `breakdown` and any `flags` (incomplete, renormalised).

## 9.3 Worked example (these rows are the first golden tests)

Template (weights sum to 100): CA1 max 10 weight 10; CA2 max 10 weight 10; Test max 20 weight
20; Exam max 60 weight 60. Scheme: rounding HALF_UP to 0 dp; absent policy `treat_zero`;
boundaries A 70–100, B 60–69, C 50–59, D 45–49, E 40–44, F 0–39.

| Student | CA1 | CA2 | Test | Exam | Computation | Total | Grade |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Ada | 8 | 7 | 15 | 48 | 8 + 7 + 15 + 48 | 78 | A |
| Bayo | 6 | 5 | 12 | 40 | 6 + 5 + 12 + 40 | 63 | B |
| Chidi | 5 | 4.5 | 9 | 31 | 5 + 4.5 + 9 + 31 = 49.5 | 50 (HALF_UP) | C |
| Dara | 9 | absent | 18 | 52 | 9 + 0 + 18 + 52 | 79 | A |
| Efe | 7 | 6 | exempt | 45 | contributions 7 + 6 + 45 = 58 over included weight 80, so 58 / 80 * 100 | 72.5 rounds to 73 | A |

Chidi demonstrates that rounding happens **once at the end**, so 49.5 becomes 50 (grade C), not
49. These rows, plus boundary edge values (39, 40, 44, 45, 69, 70, 100), become the first
golden tests (Phase 4 exit criterion).

## 9.4 Determinism and recalculation

- Each processing run stores `template_version_id`, `scheme_id`, `scheme_version`, and an
  `input_hash` of all scores consumed. Same inputs and versions always produce byte-identical
  `processed_results`.
- Editing a template or scheme creates a new version. Existing runs are untouched.
- Recalculation is an explicit action (`POST /process` with a chosen version), creates a new
  run, and is audited. The latest successful run for an assessment is the "current" one; older
  runs are retained.

---

# 10. The workflow state machine

Default states per assessment (result set): `DRAFT -> SUBMITTED -> UNDER_REVIEW -> APPROVED ->
LOCKED -> PUBLISHED`, plus `RETURNED` (back to editing).

| From | To | Action | Required permission | Constraints |
| --- | --- | --- | --- | --- |
| DRAFT | SUBMITTED | submit | `scores.submit` (scoped) | All required components resolved (no `missing` unless policy allows); validation passes |
| SUBMITTED | UNDER_REVIEW | start-review | `scores.review` | Reviewer is not the submitter |
| UNDER_REVIEW | RETURNED | return | `scores.review` | Reason required |
| RETURNED | SUBMITTED | resubmit | `scores.submit` | Fresh submission and fresh review |
| UNDER_REVIEW | APPROVED | approve | `results.approve` | A successful processing run exists and is current |
| APPROVED | LOCKED | lock | `results.lock` | Online only; re-auth |
| LOCKED | PUBLISHED | publish | `results.publish` | Online only; re-auth; MFA; generates documents |
| PUBLISHED | PUBLISHED (v+1) | correct | `results.correct` | Reason required; creates corrected document version, supersedes the old one, never overwrites |

## Implementation notes

- The transition table lives in code as data (`TRANSITIONS`) combined with per-school
  `workflow_definitions` that can add or skip optional intermediate stages and set required
  permissions. Mandatory invariants (permission check, audit event, no silent change, locks
  block edits) are **not** configurable.
- Every transition runs in one DB transaction: row lock on the assessment (`SELECT ... FOR
  UPDATE`), state check, permission check, side effects, `approval_records` insert,
  `audit_events` insert, `outbox_events` insert.
- Score edits are only allowed in `DRAFT` and `RETURNED`. Edits in later states are rejected;
  post-publication change goes only through `correct`.
- Invalid transitions return `409 INVALID_STATE_TRANSITION`.
- Separation of duties (submitter cannot approve own work) is a configurable rule, on by
  default.

---

# 11. Offline desktop sync protocol

**Scope: offline is limited to entering CA scores. Everything else is online-only.**

## 11.1 Device lifecycle

1. User logs in online; `POST /sync/devices/register` creates a `devices` row and returns a
   device id and a per-device key.
2. `GET /sync/bootstrap` returns the minimum data for the user's scope: assigned assessments in
   editable states, their rosters (subject enrolments), template version definitions, and
   current score rows with versions.
3. Local store: SQLite file encrypted at rest (SQLCipher or an OS-keychain-wrapped key).
   Tables: `cache_*` (bootstrap data), `pending_ops` (queue), `meta` (cursor, device id).
4. On logout, device revocation (server returns `DEVICE_REVOKED`), or repeated auth failure,
   the local database is **wiped**.

## 11.2 Offline operations

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

`base_version` is the score row version the user last saw. Operations for the same cell
collapse locally to the latest one before sync.

## 11.3 Push and server handling

`POST /sync/push` accepts an ordered batch. For each op, in its own savepoint:

1. **Duplicate check:** if `idempotency_key` already exists, return the stored result with
   status `duplicate`. No re-apply.
2. **Device check:** device must be active and belong to the user.
3. **Re-authorise:** `scores.enter` with scope against the assessment.
4. **State check:** assessment must still be in an editable state; otherwise
   `rejected: ASSESSMENT_NOT_EDITABLE`.
5. **Validate value** against the pinned template version (range, status rules).
6. **Version check:** if the server score's version differs from `base_version`, return
   `conflict` with the current server value. **Never overwrite.**
7. Otherwise apply, write `score_changes` (source `desktop_sync`) and an audit event, return
   `applied` with new version.

Results are persisted in `sync_operations` so retries return identical responses.

## 11.4 Conflict resolution

The client shows both values (mine vs server, with who changed it and when). The user picks
one; the client sends a new op with `base_version` set to the server's current version and a
`resolution` note. **Auto-merge is never used for score values.**

## 11.5 Pull

`GET /sync/pull?since=<cursor>` returns changed rows within scope (using an `updated_at, id`
cursor) and tombstones for removed assignments. Revoked scope removes cached data locally.
