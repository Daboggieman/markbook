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
| `assessment` | `assessment_templates`, `assessment_template_versions`, `assessments`, `scores`, `score_changes` | `platform`, `audit`, `academic` |
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

### assessment service

- `create_assessment(...)` → `Assessment`
- `batch_upsert_scores(assessment_id, score_rows, actor)` → list[`Score`]
- `import_scores(assessment_id, file_bytes, actor)` → `Job`  # async
- `get_score_history(score_id)` → list[`ScoreChange`]

### grading service

- `process_results(assessment_id, scheme_id, actor)` → `Job`  # async
- `get_processing_runs(assessment_id)` → list[`ResultProcessingRun`]
- `get_processed_results(assessment_id)` → list[`ProcessedResult`]

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