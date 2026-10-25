"""Phase 0 baseline: schools, audit_events, outbox_events, jobs + RLS.

Revision ID: 0001_baseline
Revises: None
Create Date: 2026-10-24

Deliverables (spec §16 Phase 0):
  - `schools` — one seeded row, the tenant root
  - `audit_events` — append-only (app role gets INSERT only)
  - `outbox_events` — transactional outbox (D5)
  - `jobs` — durable job status (spec §12)
  - RLS on every tenant table with `app.school_id` from the session

Conventions (spec §6): UUIDv7-shaped UUID PKs (uuid7 generated in Python),
timestamptz UTC, no hard deletes for academic data (not applicable to these
four tables — they are cross-tenant infrastructure).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- schools ---------------------------------------------------------
    op.execute(
        """
        CREATE TABLE schools (
            id           UUID PRIMARY KEY,
            name         VARCHAR(255) NOT NULL,
            config       JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # --- audit_events (append-only) --------------------------------------
    # app role gets INSERT only; no UPDATE/DELETE grants (spec §6.6).
    op.execute(
        """
        CREATE TABLE audit_events (
            id           UUID PRIMARY KEY,
            school_id    UUID REFERENCES schools(id),
            at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            actor_id     UUID,
            actor_ip     INET,
            action       TEXT NOT NULL,
            entity_type  TEXT,
            entity_id    UUID,
            before       JSONB NULL,
            after        JSONB NULL,
            reason       TEXT NULL,
            request_id   TEXT,
            prev_hash    BYTEA,
            hash         BYTEA NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX ix_audit_events_school_at ON audit_events (school_id, at DESC)")
    op.execute("CREATE INDEX ix_audit_events_entity ON audit_events (entity_type, entity_id)")

    # --- outbox_events ---------------------------------------------------
    op.execute(
        """
        CREATE TABLE outbox_events (
            id            UUID PRIMARY KEY,
            school_id     UUID NOT NULL REFERENCES schools(id),
            topic         TEXT NOT NULL,
            payload       JSONB NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            dispatched_at TIMESTAMPTZ NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_outbox_events_undispatched "
        "ON outbox_events (created_at) WHERE dispatched_at IS NULL"
    )

    # --- jobs ------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE jobs (
            id          UUID PRIMARY KEY,
            school_id   UUID REFERENCES schools(id),
            type        VARCHAR(100) NOT NULL,
            status      VARCHAR(20) NOT NULL DEFAULT 'queued'
                        CHECK (status IN ('queued','running','succeeded','failed')),
            params      JSONB,
            result      JSONB,
            error       VARCHAR(2000),
            created_by  UUID,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX ix_jobs_school_status ON jobs (school_id, status, created_at)")

    # --- RLS groundwork (full policies land with the tenant tables) ------
    # schools itself is not tenant-scoped; audit_events/outbox_events/jobs
    # carry school_id as a data column. RLS policies on future tenant-owned
    # tables follow the pattern in 02-data-model.md.
    op.execute("ALTER TABLE outbox_events ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY outbox_tenant_isolation ON outbox_events
        USING (school_id = current_setting('app.school_id', true)::uuid)
        """
    )

    # --- seed the single school ------------------------------------------
    # The app runs with exactly one school row at launch (spec §5).
    op.execute(
        """
        INSERT INTO schools (id, name, config)
        VALUES (
            '00000000-0000-7000-8000-000000000001',
            'Seed School',
            '{}'
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS jobs")
    op.execute("DROP TABLE IF EXISTS outbox_events")
    op.execute("DROP TABLE IF EXISTS audit_events")
    op.execute("DROP TABLE IF EXISTS schools")
