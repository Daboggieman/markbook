"""Phase 1: Identity, access, and audit tables.

Revision ID: 0002_identity_access
Revises: 0001_baseline
Create Date: 2026-10-25

Phase 1 deliverables (spec §16):
  - users, sessions, devices
  - roles, permissions (seeded), role_permissions, user_roles
  - Super Admin protected role with DB-level trigger
  - RLS policies on all tenant tables
  - Seeding: permissions catalogue + default Super Admin role

Conventions (spec §6): UUIDv7 PKs, timestamptz UTC, no hard deletes for
academic data; users/sessions/devices archive rather than delete.
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "0002_identity_access"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# Helper: enum types
# ---------------------------------------------------------------------------


def _upgrade() -> None:
    # --- enum types -------------------------------------------------------
    op.execute("CREATE TYPE userstatus AS ENUM ('active', 'suspended', 'deactivated')")
    op.execute("CREATE TYPE scopetype AS ENUM ('school', 'assigned', 'own')")
    op.execute("CREATE TYPE devicelabel AS ENUM ('web', 'desktop', 'mobile')")

    # --- users ------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE users (
            id                  UUID PRIMARY KEY,
            school_id           UUID NOT NULL REFERENCES schools(id),
            email               CITEXT NOT NULL,
            username            VARCHAR(50) NOT NULL,
            password_hash       VARCHAR(200) NOT NULL,
            is_super_admin      BOOLEAN NOT NULL DEFAULT false,
            status              userstatus NOT NULL DEFAULT 'active',
            mfa_enabled         BOOLEAN NOT NULL DEFAULT false,
            mfa_secret          VARCHAR(32),          -- encrypted TOTP secret, null when disabled
            failed_login_count  INT NOT NULL DEFAULT 0,
            locked_until        TIMESTAMPTZ,
            token_version       INT NOT NULL DEFAULT 1,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            version             INT NOT NULL DEFAULT 1,
            UNIQUE (school_id, email)
        )
        """
    )
    op.execute("CREATE INDEX ix_users_school_id ON users (school_id)")
    op.execute("CREATE INDEX ix_users_email ON users (school_id, email)")

    # --- sessions ---------------------------------------------------------
    op.execute(
        """
        CREATE TABLE sessions (
            id                  UUID PRIMARY KEY,
            school_id           UUID NOT NULL REFERENCES schools(id),
            user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            device_id           UUID,
            refresh_token_hash  BYTEA NOT NULL,       -- SHA-256 of the opaque refresh token
            issued_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at          TIMESTAMPTZ NOT NULL,
            revoked_at          TIMESTAMPTZ,
            ip                  INET,
            user_agent          VARCHAR(500)
        )
        """
    )
    op.execute("CREATE INDEX ix_sessions_user_id ON sessions (user_id)")
    op.execute("CREATE INDEX ix_sessions_school_id ON sessions (school_id)")
    op.execute("CREATE INDEX ix_sessions_refresh_hash ON sessions (refresh_token_hash)")

    # --- devices ----------------------------------------------------------
    op.execute(
        """
        CREATE TABLE devices (
            id             UUID PRIMARY KEY,
            user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            school_id      UUID NOT NULL REFERENCES schools(id),
            label          VARCHAR(100),
            platform       VARCHAR(50),
            registered_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_seen_at  TIMESTAMPTZ,
            revoked_at    TIMESTAMPTZ,
            device_key    BYTEA                      -- per-device encryption key (desktop only)
        )
        """
    )
    op.execute("CREATE INDEX ix_devices_user_id ON devices (user_id)")
    op.execute("CREATE INDEX ix_devices_school_id ON devices (school_id)")

    # --- roles ------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE roles (
            id           UUID PRIMARY KEY,
            school_id    UUID NOT NULL REFERENCES schools(id),
            name         VARCHAR(100) NOT NULL,
            is_super_admin BOOLEAN NOT NULL DEFAULT false,
            description  VARCHAR(500),
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (school_id, name)
        )
        """
    )
    op.execute("CREATE INDEX ix_roles_school_id ON roles (school_id)")

    # --- permissions (global catalogue, seeded) ---------------------------
    op.execute(
        """
        CREATE TABLE permissions (
            code        VARCHAR(100) PRIMARY KEY,
            description VARCHAR(500)
        )
        """
    )

    # --- role_permissions -------------------------------------------------
    op.execute(
        """
        CREATE TABLE role_permissions (
            role_id      UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            permission_code VARCHAR(100) NOT NULL REFERENCES permissions(code),
            scope_type   scopetype NOT NULL DEFAULT 'school',
            PRIMARY KEY (role_id, permission_code)
        )
        """
    )

    # --- user_roles -------------------------------------------------------
    op.execute(
        """
        CREATE TABLE user_roles (
            user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role_id     UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            school_id   UUID NOT NULL REFERENCES schools(id),
            granted_by  UUID REFERENCES users(id),
            granted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, role_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_user_roles_school_id ON user_roles (school_id)")

    # --- RLS --------------------------------------------------------------
    # sessions: no RLS — the refresh token hash IS the bearer credential.
    # school_id is denormalised for audit trail only; the user_id FK ensures
    # a session can only belong to a user of the matching school.
    for table in ("users", "devices", "roles", "user_roles"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING (school_id = current_setting('app.school_id', true)::uuid)"
        )

    # Also add school_id + RLS to role_permissions (joins through roles → school_id)
    op.execute("ALTER TABLE role_permissions ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY role_permissions_tenant_isolation ON role_permissions "
        "USING (role_id IN ("
        "SELECT id FROM roles WHERE school_id = current_setting('app.school_id', true)::uuid)"
        ")"
    )

    # --- Super Admin protection trigger ------------------------------------
    # Blocks DELETE, UPDATE to status='deactivated', and demotion of the last
    # active super-admin (spec §7.1, decision D9).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_super_admin()
        RETURNS TRIGGER AS $$
        DECLARE
            active_super_admins INT;
        BEGIN
            IF TG_OP = 'DELETE' AND OLD.is_super_admin AND OLD.status = 'active' THEN
                SELECT COUNT(*) INTO active_super_admins
                FROM users
                WHERE school_id = OLD.school_id
                  AND is_super_admin
                  AND status = 'active'
                  AND id != OLD.id;
                IF active_super_admins = 0 THEN
                    RAISE EXCEPTION 'Cannot delete the last active Super Admin';
                END IF;
            END IF;
            IF TG_OP = 'UPDATE' THEN
                IF OLD.is_super_admin AND NEW.is_super_admin
                   AND OLD.status = 'active' AND NEW.status != 'active' THEN
                    SELECT COUNT(*) INTO active_super_admins
                    FROM users
                    WHERE school_id = OLD.school_id
                      AND is_super_admin
                      AND status = 'active'
                      AND id != OLD.id;
                    IF active_super_admins = 0 THEN
                        RAISE EXCEPTION 'Cannot deactivate the last active Super Admin';
                    END IF;
                END IF;
                IF OLD.is_super_admin AND OLD.status = 'active'
                   AND NEW.is_super_admin != OLD.is_super_admin THEN
                    SELECT COUNT(*) INTO active_super_admins
                    FROM users
                    WHERE school_id = OLD.school_id
                      AND is_super_admin
                      AND status = 'active'
                      AND id != OLD.id;
                    IF active_super_admins = 0 THEN
                        RAISE EXCEPTION 'Cannot demote the last active Super Admin';
                    END IF;
                END IF;
            END IF;
            RETURN COALESCE(NEW, OLD);
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_protect_super_admin "
        "BEFORE UPDATE OR DELETE ON users "
        "FOR EACH ROW EXECUTE FUNCTION protect_super_admin()"
    )

    # --- Seed: permissions catalogue -------------------------------------
    permissions_seed = [
        # --- users ---
        ("users.view", "View users"),
        ("users.create", "Create users"),
        ("users.edit", "Edit user details and status"),
        ("users.delete", "Delete users (respects Super Admin rule)"),
        # --- roles ---
        ("roles.view", "View roles"),
        ("roles.manage", "Create and update roles"),
        ("roles.delete", "Delete roles"),
        # --- permissions ---
        ("permissions.view", "View permission catalogue"),
        ("permissions.manage", "Assign/unassign permissions to roles"),
        # --- students ---
        ("students.view", "View student records"),
        ("students.create", "Create student records"),
        ("students.edit", "Edit student records"),
        ("students.archive", "Archive students"),
        ("students.check-duplicates", "Run duplicate detection"),
        # --- academic ---
        ("academic.view", "View academic structure"),
        ("academic.manage", "Create/update sessions, terms, levels, classes"),
        # --- assessments ---
        ("assessments.view", "View assessments and templates"),
        ("assessments.manage", "Create and edit assessment templates"),
        # --- scores ---
        ("scores.view", "View scores"),
        ("scores.enter", "Enter scores"),
        ("scores.edit", "Edit entered scores (draft/returned states)"),
        ("scores.submit", "Submit scores for review"),
        ("scores.review", "Start review / return scores"),
        # --- results ---
        ("results.process", "Trigger result processing"),
        ("results.approve", "Approve results"),
        ("results.lock", "Lock results (online only, re-auth required)"),
        ("results.publish", "Publish results (online only, re-auth + MFA required)"),
        ("results.correct", "Issue a correction to published results"),
        # --- reports ---
        ("reports.view", "View report cards and documents"),
        ("transcripts.generate", "Generate transcripts"),
        # --- audit ---
        ("audit_logs.view", "View audit events"),
    ]
    for code, desc in permissions_seed:
        op.execute(
            text(
                "INSERT INTO permissions (code, description) VALUES (:code, :desc) "
                "ON CONFLICT (code) DO NOTHING"
            ).bindparams(code=code, desc=desc)
        )

    # --- Seed: Super Admin role -------------------------------------------
    op.execute(
        """
        INSERT INTO roles (id, school_id, name, is_super_admin, description)
        VALUES (
            '00000000-0000-7000-8000-000000001001',
            '00000000-0000-7000-8000-000000000001',
            'Super Admin',
            true,
            'Full access to all resources; cannot be deleted or deactivated if last active'
        )
        ON CONFLICT (school_id, name) DO NOTHING
        """
    )
    # Grant all permissions to Super Admin with 'school' scope
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_code, scope_type)
        SELECT
            '00000000-0000-7000-8000-000000001001',
            code,
            'school'
        FROM permissions
        ON CONFLICT (role_id, permission_code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_protect_super_admin ON users")
    op.execute("DROP FUNCTION IF EXISTS protect_super_admin()")
    op.execute("DROP TABLE IF EXISTS user_roles")
    op.execute("DROP TABLE IF EXISTS role_permissions")
    op.execute("DROP TABLE IF EXISTS permissions")
    op.execute("DROP TABLE IF EXISTS roles")
    op.execute("DROP TABLE IF EXISTS devices")
    op.execute("DROP TABLE IF EXISTS sessions")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP TYPE IF EXISTS devicelabel")
    op.execute("DROP TYPE IF EXISTS scopetype")
    op.execute("DROP TYPE IF EXISTS userstatus")


# Entry point called by Alembic
def upgrade() -> None:
    _upgrade()
