# Module reference

The module list, their owned tables, their service-layer public interface, and the cross-module
calls each makes. Source of record for module purpose: spec §3 and
[`../build_docs/01-architecture-and-stack.md`](../build_docs/01-architecture-and-stack.md).

## Module overview

| Module | Owns | Depends on |
| --- | --- | --- |
| `platform` | config, db session, redis, jobs, outbox, logging, errors, pagination | nothing |
| `audit` | `audit_events` | nothing |
| `identity` | `users`, `sessions`, `devices` | `platform`, `audit` |
| `access` | `roles`, `permissions`, `role_permissions`, `user_roles` | `platform`, `audit` |
| `people` | `students`, `guardians`, `student_guardians` | `platform`, `audit` |
| `academic` | `academic_sessions`, `terms`, `educational_levels`, `classes`, `sections`, `subjects`, `class_subjects`, `enrolments`, `subject_enrolments`, `teacher_assignments`, `promotion_records` | `platform`, `audit`, `people` (read) |
| `assessment` | `assessment_templates`, `assessment_template_versions`, `assessments`, `scores`, `score_changes` | `platform`, `audit`, `academic` (models), `people` (models, read) |
| `grading` | `grading_schemes`, `result_processing_runs`, `processed_results` | `platform`, `audit`, `assessment` |
| `workflow` | `workflow_definitions`, `approval_records`, `published_documents` | `platform`, `audit`, `assessment`, `grading` |
| `documents` | (storage only — PDFs live in S3) | `platform`, `audit`, `workflow` |
| `sync` | `sync_operations` | `platform`, `audit`, `identity`, `assessment` |

## Key service interfaces (Phase 1+)

*To be populated as each module is built. This file is the living reference; it is written as
modules ship.*

### identity service

- `create_user(...)` → `User`
- `authenticate(email, password)` → `(User, AccessToken, RefreshToken)`
- `refresh_access_token(refresh_token)` → `(AccessToken, RefreshToken)`  # rotates old
- `revoke_session(session_id, actor_id)`
- `get_devices(user_id)` → list[`Device`]
- `revoke_device(device_id)`

### access service

- `authorize(actor, permission, resource)` → `Decision`  # the one function used everywhere
- `get_effective_permissions(actor)` → list[`Permission`]
- `scope_filter(actor, permission)` → `SQLExpression`  # for list queries
- `grant_role(user_id, role_id, granted_by)`
- `revoke_role(user_id, role_id)`

### assessment service (Phase 3)

- `create_template(school_id, data, actor)` → (`AssessmentTemplate`, draft v1)
- `create_template_version(school_id, template_id, data)` → `AssessmentTemplateVersion`  # editing creates a NEW version
- `activate_template_version(school_id, version_id)` → `AssessmentTemplateVersion`  # retires the previous active
- `create_assessment(school_id, data)` → `Assessment`  # requires an active template version
- `list_assessments(school_id, *, scope, actor, ...)` → list[`Assessment`]  # assigned scope → teacher assignments filter
- `get_sheet(school_id, assessment_id)` → `ScoreSheetResponse`  # roster + entered cells
- `batch_upsert_scores(school_id, assessment_id, rows, actor, *, scope, source, reason)` → list[`Score`]  # all-or-nothing; per-cell `base_version`; stale → 409 (422 when validation also failed)
- `apply_import(school_id, assessment_id, csv_text, actor)` → dict  # row-level partial success; runs in the worker job `assessment.jobs::import_scores`
- `enqueue_import(school_id, assessment_id, csv_text, actor, *, scope)` → `Job`  # scope checked at enqueue time
- `get_score_history(school_id, score_id)` → list[`ScoreChange`]
- `get_job(school_id, job_id)` → `Job`

Read edges: `assessment.repository` joins `academic.models` (Enrolment, ClassSubject,
SubjectEnrolment, Term, TeacherAssignment) and `people.models` (Student) for the score-sheet
roster — models only, never another module's repository (the Phase 2 precedent).

### grading service (Phase 4)

- `create_scheme(school_id, data, actor)` → `GradingScheme`  # new name → draft v1; same name → the NEXT version (editing never rewrites, spec §9.4)
- `list_schemes(school_id)` → list[`GradingScheme`] / `get_scheme(school_id, scheme_id)` → `GradingScheme`
- `activate_scheme(school_id, scheme_id, actor)` → `GradingScheme`  # draft → active, retires the previous active of the same name; retired can't reactivate (409)
- `enqueue_process(school_id, assessment_id, scheme_id, actor)` → (`Job`, `ResultProcessingRun`)  # scheme version must be active; run pins scheme version + the assessment's template version
- `apply_run(school_id, run_id, actor)` → dict  # the deterministic core — worker-side only (`grading.jobs::process_results`); idempotent on already-settled runs
- `list_runs(school_id, assessment_id)` → list[`ResultProcessingRun`]  # run history, newest first
- `get_results(school_id, assessment_id)` → (`ResultProcessingRun`, list[(`ProcessedResult`, `student_name`)])  # the latest SUCCEEDED run in report-card order; 404 before any

The pure engine (`grading/engine/`, mypy-strict, fenced by the `engine-is-pure` import-linter
contract): `compute(student_scores, template, scheme)` → `ComputedResult` (one student);
`rank(results, scheme)` → list[`RankedResult`] (dense/competition); `build_scheme` /
`validate_scheme` (contiguous integer bands 0..100 — the single authority on scheme validity);
`input_hash(scores)` → 64-hex SHA-256 over the canonical score serialization (spec §9.4).

*Cross-module call note:* `grading.service` consumes `AssessmentService.get_sheet()` — a
service-interface edge (legal under `no-cross-repository`), so there is one definition of
"what is on the sheet" with two consumers. `grading.repository` joins `academic.models`
(SubjectEnrolment, Enrolment) and `people.models` (Student) for display names — models only,
never another module's repository. `missing_policy=block` fails the WHOLE run (blocked
students listed in the run's `error`); a student with every component excluded is stored
with NULL total/grade/position and the `no_scoreable_components` flag.

### workflow service

- `submit(assessment_id, actor)` → `ApprovalRecord`
- `start_review(assessment_id, actor)` → `ApprovalRecord`
- `return_for_editing(assessment_id, reason, actor)` → `ApprovalRecord`
- `approve(assessment_id, actor)` → `ApprovalRecord`
- `lock(assessment_id, actor)` → `ApprovalRecord`
- `publish(assessment_id, actor)` → `PublishedDocument`
- `correct(assessment_id, reason, actor)` → `PublishedDocument`

*Cross-module call note:* `workflow.publish` calls `documents.generate_report_card(...)`. The
outbox event `results.published` is the trigger; the worker handles the delivery.