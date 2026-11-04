"""Phase 3: Assessment templates and score entry.

Revision ID: 0004_assessment_scores
Revises: 0003_people_academic
Create Date: 2026-11-02

Phase 3 deliverables (spec §16, data model §6.4):
  - assessment_templates, assessment_template_versions (immutable once active)
  - assessments (per term/class/subject/section)
  - scores with CHECK zero-vs-missing constraint
  - score_changes (audit ledger)
  - Bulk import as an async job
  - DB CHECK blocks invalid zero/missing combinations (Phase 3 exit criterion)

Conventions (spec §6): UUIDv7 PKs, timestamptz UTC, archived_at not hard
deletes, school_id NOT NULL + leading index on every tenant table, RLS
`USING (school_id = current_setting('app.school_id', true)::uuid)`.
Scores are NUMERIC(6,2). Every state-changing action writes an audit event.
"""

from alembic import op

# revision identifiers
revision: str = "0004_assessment_scores"
down_revision: str | None = "0003_people_academic"


def upgrade() -> None:
    # --- enum types -------------------------------------------------------
    op.execute("CREATE TYPE templateversionstatus AS ENUM ('draft', 'active', 'retired')")
    op.execute(
        "CREATE TYPE workflowstate AS ENUM "
        "('draft','submitted','under_review','returned','approved','locked','published')"
    )
    op.execute("CREATE TYPE scorestatus AS ENUM ('entered','absent','exempt','missing')")
    op.execute("CREATE TYPE scorechangesource AS ENUM ('web','desktop_sync','import')")

    # --- assessment_templates -----------------------------------------------
    op.execute(
        """
        CREATE TABLE assessment_templates (
            id          UUID PRIMARY KEY,
            school_id   UUID NOT NULL REFERENCES schools(id),
            name        VARCHAR(255) NOT NULL,
            created_by  UUID REFERENCES users(id),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            version     INT NOT NULL DEFAULT 1
        )
        """
    )
    op.execute("CREATE INDEX ix_assessment_templates_school_id ON assessment_templates (school_id)")

    # --- assessment_template_versions ---------------------------------------
    op.execute(
        """
        CREATE TABLE assessment_template_versions (
            id              UUID PRIMARY KEY,
            school_id       UUID NOT NULL REFERENCES schools(id),
            template_id     UUID NOT NULL REFERENCES assessment_templates(id),
            version_no      INT NOT NULL,
            status          templateversionstatus NOT NULL DEFAULT 'draft',
            definition      JSONB NOT NULL,
            -- definition: {"components": [{"key","label","max_score","weight","required"}]}
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_by      UUID REFERENCES users(id),
            UNIQUE (school_id, template_id, version_no)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_assessment_template_versions_school_id "
        "ON assessment_template_versions (school_id)"
    )

    # --- assessments -------------------------------------------------------
    op.execute(
        """
        CREATE TABLE assessments (
            id                  UUID PRIMARY KEY,
            school_id           UUID NOT NULL REFERENCES schools(id),
            term_id            UUID NOT NULL REFERENCES terms(id),
            class_id           UUID NOT NULL REFERENCES classes(id),
            section_id         UUID REFERENCES sections(id),
            subject_id         UUID NOT NULL REFERENCES subjects(id),
            template_version_id UUID NOT NULL
                                REFERENCES assessment_template_versions(id),
            workflow_state     workflowstate NOT NULL DEFAULT 'draft',
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            version            INT NOT NULL DEFAULT 1,
            UNIQUE NULLS NOT DISTINCT
                (school_id, term_id, class_id, subject_id, section_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_assessments_school_id ON assessments (school_id)")
    op.execute(
        "CREATE INDEX ix_assessments_school_term_class "
        "ON assessments (school_id, term_id, class_id)"
    )

    # --- scores -----------------------------------------------------------
    op.execute(
        """
        CREATE TABLE scores (
            id                    UUID PRIMARY KEY,
            school_id             UUID NOT NULL REFERENCES schools(id),
            assessment_id         UUID NOT NULL REFERENCES assessments(id),
            subject_enrolment_id  UUID NOT NULL REFERENCES subject_enrolments(id),
            component_key         VARCHAR(100) NOT NULL,
            status                scorestatus NOT NULL DEFAULT 'missing',
            value                 NUMERIC(6,2),
            entered_by            UUID REFERENCES users(id),
            entered_at            TIMESTAMPTZ,
            updated_by            UUID REFERENCES users(id),
            updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            version               INT NOT NULL DEFAULT 1,
            -- DB-level guarantee that zero is distinct from missing (spec §6.4):
            -- entered status requires a non-NULL value; non-entered statuses must be NULL.
            CONSTRAINT chk_scores_entered_value
                CHECK ((status = 'entered') = (value IS NOT NULL)),
            UNIQUE (assessment_id, subject_enrolment_id, component_key)
        )
        """
    )
    op.execute("CREATE INDEX ix_scores_school_id ON scores (school_id)")
    op.execute(
        "CREATE INDEX ix_scores_school_enrolment ON scores (school_id, subject_enrolment_id)"
    )

    # --- score_changes ----------------------------------------------------
    # Append-only audit ledger. created_at/updated_at convention waived:
    # changed_at IS the ledger's "created at"; no UPDATE after insert.
    op.execute(
        """
        CREATE TABLE score_changes (
            id          UUID PRIMARY KEY,
            school_id   UUID NOT NULL REFERENCES schools(id),
            score_id    UUID NOT NULL REFERENCES scores(id),
            old_status  scorestatus,
            old_value   NUMERIC(6,2),
            new_status  scorestatus,
            new_value   NUMERIC(6,2),
            reason      TEXT,
            changed_by  UUID REFERENCES users(id),
            changed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            source      scorechangesource NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX ix_score_changes_school_id ON score_changes (school_id)")
    op.execute("CREATE INDEX ix_score_changes_score_id ON score_changes (score_id)")

    # --- RLS on every tenant table ---------------------------------------
    _rls_tables = (
        "assessment_templates",
        "assessment_template_versions",
        "assessments",
        "scores",
        "score_changes",
    )
    for table in _rls_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING (school_id = current_setting('app.school_id', true)::uuid)"
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS score_changes")
    op.execute("DROP TABLE IF EXISTS scores")
    op.execute("DROP TABLE IF EXISTS assessments")
    op.execute("DROP TABLE IF EXISTS assessment_template_versions")
    op.execute("DROP TABLE IF EXISTS assessment_templates")
    op.execute("DROP TYPE IF EXISTS scorechangesource")
    op.execute("DROP TYPE IF EXISTS scorestatus")
    op.execute("DROP TYPE IF EXISTS workflowstate")
    op.execute("DROP TYPE IF EXISTS templateversionstatus")
