# Markbook — Data Model

Source of record: spec §5 (Multi-Tenancy Readiness), §6 (Database Design).

## Conventions

- Primary keys are **UUIDv7** (time-ordered): index-friendly, safe to expose, merge-safe across
  schools later.
- Every table carries `created_at`, `updated_at`.
- Mutable records carry `version INT` for optimistic concurrency.
- Academic data is archived via `archived_at` — **no hard deletes**.
- Timestamps are `timestamptz` in UTC.
- Scores are `NUMERIC(6,2)`. Never float (rule 6,
  [`10-coding-agent-rules.md`](10-coding-agent-rules.md)).

## Multi-tenancy foundations (non-negotiable)

- `schools` table with one seeded row.
- Every tenant-owned table has `school_id UUID NOT NULL REFERENCES schools(id)` and an index
  starting with `school_id`.
- Request context carries `school_id` (derived from the authenticated user, never from client
  input).
- The DB session sets `SET LOCAL app.school_id = '<uuid>'` at transaction start. RLS policies
  on every tenant table: `USING (school_id = current_setting('app.school_id')::uuid)`.
- The application DB role is not a superuser and does not bypass RLS. Migrations and ops use a
  separate role.
- Uniqueness rules are composite with `school_id` (for example, admission number unique per
  school).

## 6.1 Identity and access

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

**Scope model.** `role_permissions.scope_type` expresses breadth. `school` means all records.
`assigned` means only records tied to the user's `teacher_assignments`. `own` means records the
user created. Narrower, record-specific scope (individual classes) is resolved through
`teacher_assignments`, so no separate scope table is needed in v1. If arbitrary scopes are
needed later, add `permission_scopes` without changing the check interface.

**Protected Super Admin rules** are enforced in `access.service` and by a DB trigger that
blocks deleting, deactivating, or demoting the last active Super Admin.

## 6.2 People

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

**Duplicate detection:** before create, query by normalized name plus DOB with `pg_trgm`
similarity; if any candidate scores above threshold, the API returns `409 POSSIBLE_DUPLICATE`
with candidates; the client resubmits with `confirm_not_duplicate=true`.

## 6.3 Academic structure

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

**Historical context invariant:** results reference `enrolment_id` and `class_subject_id`,
never a mutable "current class". Promoting a student creates a new enrolment; old results stay
attached to the old one. (Phase 2 exit criterion: promotion keeps old results context.)

## 6.4 Assessment and scores

```sql
assessment_templates(id, school_id, name, created_by)
assessment_template_versions(id, school_id, template_id, version_no,
                             status ENUM('draft','active','retired'),
                             definition JSONB, created_at, created_by)
  -- definition: components [{key,label,max_score,weight,required}]
  -- active versions are IMMUTABLE

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

The `CHECK` constraint is the database-level guarantee that **zero is distinct from missing**:
`entered` with value `0.00` is a real zero; `missing` has NULL. This is a Phase 3 exit
criterion — the DB CHECK blocks invalid zero/missing combinations.

## 6.5 Grading, results, workflow

```sql
grading_schemes(id, school_id, name, version_no, status, definition JSONB)
  -- definition: rounding, missing_policy, absent_policy, exempt_policy,
  --             boundaries [{grade,min,max,remark}], tie_policy

result_processing_runs(id, school_id, assessment_id, scheme_id, scheme_version,
                       template_version_id,
                       status ENUM('queued','running','succeeded','failed'),
                       input_hash TEXT, started_at, finished_at, requested_by)
processed_results(id, school_id, run_id, subject_enrolment_id, total NUMERIC(6,2),
                  grade TEXT, position INT NULL, breakdown JSONB, flags JSONB)
  INDEX (school_id, run_id)

workflow_definitions(id, school_id, name, stages JSONB)
  -- configurable stage list + required permissions
approval_records(id, school_id, assessment_id, from_state, to_state, actor_id, reason, at)
published_documents(id, school_id, assessment_id NULL, enrolment_id NULL, kind,
                    doc_version INT, supersedes_id NULL, storage_key, checksum,
                    published_by, published_at, correction_reason)
```

## 6.6 Audit and sync

```sql
audit_events(id, school_id, at, actor_id NULL, actor_ip, action TEXT, entity_type, entity_id,
             before JSONB NULL, after JSONB NULL, reason TEXT NULL, request_id,
             prev_hash BYTEA, hash BYTEA)
  -- append-only: app role has INSERT only; no UPDATE/DELETE grants

sync_operations(id, school_id, device_id, user_id, idempotency_key UNIQUE, op_type,
                payload JSONB, base_version INT NULL,
                status ENUM('applied','conflict','rejected','duplicate'),
                result JSONB, received_at, processed_at)

outbox_events(id, school_id, topic, payload JSONB, created_at, dispatched_at NULL)
```

**Audit hash chain:** each event stores `hash = SHA256(prev_hash || canonical_json(event))`. A
nightly job (`audit.verify_chain`) verifies the chain; a break raises an alert. This makes
tampering detectable.

## Phase 2 seed data

The Nigerian default seed ships with Phase 2: Nursery, Primary 1–6, JSS 1–3, SS 1–3 as
educational levels and classes.
