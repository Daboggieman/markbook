"""Phase 5: Workflow, approval, publication and documents.

Revision ID: 0006_workflow_documents
Revises: 0005_grading_results
Create Date: 2026-11-11

Phase 5 deliverables (spec §16, data model §6.5):
  - workflow_definitions (per-school configurable stage order)
  - approval_records (who approved which transition, when, why)
  - published_documents (immutable published artifacts; corrections create a
    superseding version — doc_version increments, supersedes_id points at the
    row being corrected, and the superseded row is never modified)

The assessment's own state machine lives on assessments.workflow_state
(migration 0004's workflowstate enum); this migration adds the supporting
records. approval_records.from_state/to_state reuse that enum.

Conventions (spec §6): UUIDv7 PKs, timestamptz UTC, school_id NOT NULL +
leading index on every tenant table, RLS
`USING (school_id = current_setting('app.school_id', true)::uuid)`.
"""

from alembic import op

# revision identifiers
revision: str = "0006_workflow_documents"
down_revision: str | None = "0005_grading_results"


def upgrade() -> None:
    # --- enum types -------------------------------------------------------
    op.execute("CREATE TYPE documentkind AS ENUM ('report_card', 'transcript')")

    # --- workflow_definitions ----------------------------------------------
    # stages: JSONB list of {"state": <workflowstate>, "requires": [permission]}
    # describing the school's path from draft to published. The mandatory
    # invariants (spec §10) are NOT configurable — they live in code.
    op.execute(
        """
        CREATE TABLE workflow_definitions (
            id          UUID PRIMARY KEY,
            school_id   UUID NOT NULL REFERENCES schools(id),
            name        VARCHAR(255) NOT NULL,
            stages      JSONB NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_by  UUID REFERENCES users(id),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (school_id, name)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_workflow_definitions_school_id ON workflow_definitions (school_id)"
    )

    # --- approval_records ---------------------------------------------------
    # One row per successful transition — the durable "who approved what"
    # record the audit log cross-references. Reason is required for
    # return/correct transitions by the service, optional elsewhere.
    op.execute(
        """
        CREATE TABLE approval_records (
            id            UUID PRIMARY KEY,
            school_id     UUID NOT NULL REFERENCES schools(id),
            assessment_id UUID NOT NULL REFERENCES assessments(id),
            from_state    workflowstate NOT NULL,
            to_state      workflowstate NOT NULL,
            actor_id      UUID REFERENCES users(id),
            reason        TEXT,
            at            TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_approval_records_school_id ON approval_records (school_id)"
    )
    op.execute(
        "CREATE INDEX ix_approval_records_school_assessment "
        "ON approval_records (school_id, assessment_id)"
    )

    # --- published_documents -------------------------------------------------
    # Immutable once inserted: a correction inserts a NEW row with
    # doc_version = prior + 1 and supersedes_id = prior.id. There is no
    # UPDATE path and no DELETE path in the application.
    op.execute(
        """
        CREATE TABLE published_documents (
            id                UUID PRIMARY KEY,
            school_id         UUID NOT NULL REFERENCES schools(id),
            assessment_id     UUID REFERENCES assessments(id),
            enrolment_id      UUID REFERENCES subject_enrolments(id),
            kind              documentkind NOT NULL,
            doc_version       INT NOT NULL DEFAULT 1,
            supersedes_id     UUID REFERENCES published_documents(id),
            storage_key       TEXT NOT NULL,
            checksum          VARCHAR(64) NOT NULL,
            published_by      UUID REFERENCES users(id),
            published_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            correction_reason TEXT,
            CONSTRAINT chk_published_documents_target
                CHECK (assessment_id IS NOT NULL OR enrolment_id IS NOT NULL),
            CONSTRAINT uq_published_documents_version
                -- NULLS NOT DISTINCT: a plain UNIQUE treats NULLs as distinct,
                -- which would let two transcript v1 rows coexist (PG 15+).
                UNIQUE NULLS NOT DISTINCT (school_id, assessment_id, enrolment_id, kind, doc_version)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_published_documents_school_id ON published_documents (school_id)"
    )
    op.execute(
        "CREATE INDEX ix_published_documents_school_assessment "
        "ON published_documents (school_id, assessment_id)"
    )

    # --- RLS on every tenant table ---------------------------------------
    _rls_tables = ("workflow_definitions", "approval_records", "published_documents")
    for table in _rls_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING (school_id = current_setting('app.school_id', true)::uuid)"
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS published_documents")
    op.execute("DROP TABLE IF EXISTS approval_records")
    op.execute("DROP TABLE IF EXISTS workflow_definitions")
    op.execute("DROP TYPE IF EXISTS documentkind")
