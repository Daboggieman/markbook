"""Phase 4: Calculation engine and processing.

Revision ID: 0005_grading_results
Revises: 0004_assessment_scores
Create Date: 2026-11-09

Phase 4 deliverables (spec §16, data model §6.5, engine spec §9):
  - grading_schemes (row-per-version; family = (school_id, name))
  - result_processing_runs (determinism record: scheme version, template
    version, input_hash of every score consumed)
  - processed_results (immutable per run; latest succeeded run is current)

Deviation from the §6.5 sketch: result_processing_runs gains `error TEXT` —
a failed run must record WHY for the operator (the jobs row carries a copy,
but run history is the per-assessment record of record).

Conventions (spec §6): UUIDv7 PKs, timestamptz UTC, school_id NOT NULL +
leading index on every tenant table, RLS
`USING (school_id = current_setting('app.school_id', true)::uuid)`.
"""

from alembic import op

# revision identifiers
revision: str = "0005_grading_results"
down_revision: str | None = "0004_assessment_scores"


def upgrade() -> None:
    # --- enum types -------------------------------------------------------
    op.execute("CREATE TYPE schemestatus AS ENUM ('draft', 'active', 'retired')")
    op.execute("CREATE TYPE runstatus AS ENUM ('queued','running','succeeded','failed')")

    # --- grading_schemes ----------------------------------------------------
    op.execute(
        """
        CREATE TABLE grading_schemes (
            id          UUID PRIMARY KEY,
            school_id   UUID NOT NULL REFERENCES schools(id),
            name        VARCHAR(255) NOT NULL,
            version_no  INT NOT NULL,
            status      schemestatus NOT NULL DEFAULT 'draft',
            definition  JSONB NOT NULL,
            -- definition: {"rounding_mode","precision","missing_policy",
            --   "absent_policy","exempt_policy",
            --   "boundaries":[{"grade","min","max","remark"}],"tie_policy"}
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_by  UUID REFERENCES users(id),
            UNIQUE (school_id, name, version_no)
        )
        """
    )
    op.execute("CREATE INDEX ix_grading_schemes_school_id ON grading_schemes (school_id)")
    op.execute(
        "CREATE INDEX ix_grading_schemes_school_name ON grading_schemes (school_id, name)"
    )

    # --- result_processing_runs ---------------------------------------------
    op.execute(
        """
        CREATE TABLE result_processing_runs (
            id                  UUID PRIMARY KEY,
            school_id           UUID NOT NULL REFERENCES schools(id),
            assessment_id       UUID NOT NULL REFERENCES assessments(id),
            scheme_id           UUID NOT NULL REFERENCES grading_schemes(id),
            scheme_version      INT NOT NULL,
            template_version_id UUID NOT NULL
                                REFERENCES assessment_template_versions(id),
            status              runstatus NOT NULL DEFAULT 'queued',
            input_hash          VARCHAR(64),
            error               TEXT,
            started_at          TIMESTAMPTZ,
            finished_at         TIMESTAMPTZ,
            requested_by        UUID REFERENCES users(id),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_result_processing_runs_school_id "
        "ON result_processing_runs (school_id)"
    )
    op.execute(
        "CREATE INDEX ix_result_processing_runs_school_assessment "
        "ON result_processing_runs (school_id, assessment_id)"
    )

    # --- processed_results --------------------------------------------------
    # total/grade/position NULLable: a student with every component excluded
    # (flag no_scoreable_components) has no computable total — the row is
    # still stored so the run reports them.
    op.execute(
        """
        CREATE TABLE processed_results (
            id                    UUID PRIMARY KEY,
            school_id             UUID NOT NULL REFERENCES schools(id),
            run_id                UUID NOT NULL
                                  REFERENCES result_processing_runs(id) ON DELETE CASCADE,
            subject_enrolment_id  UUID NOT NULL REFERENCES subject_enrolments(id),
            total                 NUMERIC(6,2),
            grade                 TEXT,
            position              INT,
            breakdown             JSONB NOT NULL,
            flags                 JSONB NOT NULL,
            UNIQUE (run_id, subject_enrolment_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_processed_results_school_id ON processed_results (school_id)"
    )
    op.execute(
        "CREATE INDEX ix_processed_results_school_run "
        "ON processed_results (school_id, run_id)"
    )

    # --- RLS on every tenant table ---------------------------------------
    _rls_tables = ("grading_schemes", "result_processing_runs", "processed_results")
    for table in _rls_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING (school_id = current_setting('app.school_id', true)::uuid)"
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS processed_results")
    op.execute("DROP TABLE IF EXISTS result_processing_runs")
    op.execute("DROP TABLE IF EXISTS grading_schemes")
    op.execute("DROP TYPE IF EXISTS runstatus")
    op.execute("DROP TYPE IF EXISTS schemestatus")
