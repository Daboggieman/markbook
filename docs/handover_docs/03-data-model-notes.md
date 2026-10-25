# Data model notes — decisions embedded in the schema

The full schema lives in [`../build_docs/02-data-model.md`](../build_docs/02-data-model.md).
This file records the *decisions inside it* — the ones a future session would otherwise
question or "simplify" wrongly.

## Zero is distinct from missing — database-level

`scores` carries `CHECK ((status='entered') = (value IS NOT NULL))`. This is the database-level
guarantee that a real zero (`entered`, `0.00`) can never be confused with a missing score
(`missing`, NULL). The application layer must not try to be cleverer than the constraint. If a
test suggests the CHECK is in the way, the test is wrong.

## Enrolments, not "current class"

Results reference `enrolment_id` and `class_subject_id`, never a mutable "current class".
Promoting a student creates a new enrolment; old results stay attached to the old one. This is
why promotion_records carries `from_enrolment_id` and `to_enrolment_id` instead of mutating the
existing enrolment's class. If a query looks like it wants "the student's current class", it
almost certainly wants "the enrolment attached to this result" instead.

## Template versions are immutable once active

`assessment_template_versions.definition` is JSONB and becomes **immutable** when the version's
status leaves `draft`. Editing a template creates a new version; existing assessments keep
pointing at the version they were created with. Never "update in place" an active version.

## Duplicate detection is a 409, not a block

Creating a student runs pg_trgm similarity against normalized name + DOB. Above threshold, the
API returns `409 POSSIBLE_DUPLICATE` with the candidates. The client resubmits with
`confirm_not_duplicate=true`. The API never silently merges or blocks — it surfaces the
candidates and lets the operator decide.

## Uniqueness is composite with school_id

Admission numbers, emails, role names, assessment keys — every UNIQUE constraint that would
naively be global is scoped `(school_id, ...)`. This is the multi-school readiness layer and it
is not optional.

## UUIDv7 primary keys

Time-ordered, index-friendly, safe to expose in URLs and API responses, merge-safe across
schools later. Do not swap for serial ints or UUIDv4.

## No hard deletes for academic data

Archive via `archived_at`. The archive endpoint (`POST /students/{id}/archive`) preserves
history. `DELETE` routes for academic entities do not exist and should not be added.

## Scores are NUMERIC(6,2)

Never float, never integer cents. The calculation engine uses Python `Decimal`; the column is
`NUMERIC(6,2)`; the two agree.