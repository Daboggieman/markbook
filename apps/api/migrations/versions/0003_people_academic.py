"""Phase 2: People and academic structure tables.

Revision ID: 0003_people_academic
Revises: 0002_identity_access
Create Date: 2026-10-28

Phase 2 deliverables (spec §16, data model §6.2/§6.3):
  - students, guardians, student_guardians (+ pg_trgm duplicate detection)
  - academic_sessions, terms, educational_levels, classes, sections,
    subjects, class_subjects
  - enrolments, subject_enrolments, teacher_assignments, promotion_records
  - RLS policies on every tenant table
  - Nigerian default seed: Nursery, Primary 1-6, JSS 1-3, SS 1-3

Conventions (spec §6): UUIDv7 PKs, timestamptz UTC, archived_at not hard
deletes, school_id NOT NULL + leading index on every tenant table, RLS
`USING (school_id = current_setting('app.school_id', true)::uuid)`.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_people_academic"
down_revision: str | None = "0002_identity_access"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _upgrade() -> None:
    # --- extensions -------------------------------------------------------
    # pg_trgm powers student duplicate detection (spec §6.2). (citext is
    # created by 0002, which uses it for users.email.)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # --- enum types -------------------------------------------------------
    op.execute(
        "CREATE TYPE studentstatus AS ENUM ('active', 'graduated', 'withdrawn', 'archived')"
    )
    op.execute(
        "CREATE TYPE enrolmentstatus AS ENUM "
        "('enrolled','promoted','repeated','graduated','withdrawn')"
    )
    op.execute("CREATE TYPE teacherrole AS ENUM ('subject','form')")

    # --- students ---------------------------------------------------------
    op.execute(
        """
        CREATE TABLE students (
            id            UUID PRIMARY KEY,
            school_id     UUID NOT NULL REFERENCES schools(id),
            system_id     TEXT,             -- school-assigned number, unique per school when set
            admission_no  VARCHAR(50),
            first_name    VARCHAR(100) NOT NULL,
            middle_name   VARCHAR(100),
            last_name     VARCHAR(100) NOT NULL,
            dob           DATE,
            sex           VARCHAR(10),
            status        studentstatus NOT NULL DEFAULT 'active',
            archived_at   TIMESTAMPTZ,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            version       INT NOT NULL DEFAULT 1
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_students_school_admission_no ON students (school_id, admission_no) "
        "WHERE admission_no IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_students_school_system_id ON students (school_id, system_id) "
        "WHERE system_id IS NOT NULL"
    )
    op.execute("CREATE INDEX ix_students_school_id ON students (school_id)")
    op.execute(
        "CREATE INDEX ix_students_school_names ON students (school_id, last_name, first_name)"
    )
    # Trigram index for duplicate detection (name similarity search).
    op.execute(
        "CREATE INDEX ix_students_name_trgm ON students "
        "USING gin (lower(first_name || ' ' || last_name) gin_trgm_ops)"
    )

    # --- guardians --------------------------------------------------------
    op.execute(
        """
        CREATE TABLE guardians (
            id          UUID PRIMARY KEY,
            school_id   UUID NOT NULL REFERENCES schools(id),
            name        VARCHAR(255) NOT NULL,
            phone       VARCHAR(30),
            email       CITEXT,
            address     VARCHAR(500),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            version     INT NOT NULL DEFAULT 1
        )
        """
    )
    op.execute("CREATE INDEX ix_guardians_school_id ON guardians (school_id)")

    # --- student_guardians (school_id denormalised for RLS, as user_roles) ---
    op.execute(
        """
        CREATE TABLE student_guardians (
            student_id    UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
            guardian_id   UUID NOT NULL REFERENCES guardians(id) ON DELETE CASCADE,
            school_id     UUID NOT NULL REFERENCES schools(id),
            relationship  VARCHAR(50),
            is_primary    BOOLEAN NOT NULL DEFAULT false,
            PRIMARY KEY (student_id, guardian_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_student_guardians_school_id ON student_guardians (school_id)")

    # --- academic structure -----------------------------------------------
    op.execute(
        """
        CREATE TABLE academic_sessions (
            id          UUID PRIMARY KEY,
            school_id   UUID NOT NULL REFERENCES schools(id),
            name        VARCHAR(100) NOT NULL,
            start_date  DATE,
            end_date    DATE,
            is_current  BOOLEAN NOT NULL DEFAULT false,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            version     INT NOT NULL DEFAULT 1,
            UNIQUE (school_id, name)
        )
        """
    )
    op.execute("CREATE INDEX ix_academic_sessions_school_id ON academic_sessions (school_id)")

    op.execute(
        """
        CREATE TABLE terms (
            id          UUID PRIMARY KEY,
            school_id   UUID NOT NULL REFERENCES schools(id),
            session_id  UUID NOT NULL REFERENCES academic_sessions(id) ON DELETE CASCADE,
            name        VARCHAR(100) NOT NULL,
            ordinal     INT NOT NULL,
            start_date  DATE,
            end_date    DATE,
            is_current  BOOLEAN NOT NULL DEFAULT false,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            version     INT NOT NULL DEFAULT 1,
            UNIQUE (school_id, session_id, name)
        )
        """
    )
    op.execute("CREATE INDEX ix_terms_school_id ON terms (school_id)")
    op.execute("CREATE INDEX ix_terms_session_id ON terms (session_id)")

    op.execute(
        """
        CREATE TABLE educational_levels (
            id          UUID PRIMARY KEY,
            school_id   UUID NOT NULL REFERENCES schools(id),
            name        VARCHAR(100) NOT NULL,
            ordinal     INT NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (school_id, name)
        )
        """
    )
    op.execute("CREATE INDEX ix_educational_levels_school_id ON educational_levels (school_id)")

    op.execute(
        """
        CREATE TABLE classes (
            id          UUID PRIMARY KEY,
            school_id   UUID NOT NULL REFERENCES schools(id),
            level_id    UUID NOT NULL REFERENCES educational_levels(id),
            name        VARCHAR(100) NOT NULL,
            ordinal     INT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (school_id, name)
        )
        """
    )
    op.execute("CREATE INDEX ix_classes_school_id ON classes (school_id)")
    op.execute("CREATE INDEX ix_classes_level_id ON classes (level_id)")

    op.execute(
        """
        CREATE TABLE sections (
            id          UUID PRIMARY KEY,
            school_id   UUID NOT NULL REFERENCES schools(id),
            class_id    UUID NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
            name        VARCHAR(100) NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (school_id, class_id, name)
        )
        """
    )
    op.execute("CREATE INDEX ix_sections_school_id ON sections (school_id)")
    op.execute("CREATE INDEX ix_sections_class_id ON sections (class_id)")

    op.execute(
        """
        CREATE TABLE subjects (
            id          UUID PRIMARY KEY,
            school_id   UUID NOT NULL REFERENCES schools(id),
            name        VARCHAR(200) NOT NULL,
            code        VARCHAR(20),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (school_id, name)
        )
        """
    )
    op.execute("CREATE INDEX ix_subjects_school_id ON subjects (school_id)")
    op.execute(
        "CREATE UNIQUE INDEX ux_subjects_school_code ON subjects (school_id, code) "
        "WHERE code IS NOT NULL"
    )

    op.execute(
        """
        CREATE TABLE class_subjects (
            id           UUID PRIMARY KEY,
            school_id    UUID NOT NULL REFERENCES schools(id),
            class_id     UUID NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
            subject_id   UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            is_optional  BOOLEAN NOT NULL DEFAULT false,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (class_id, subject_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_class_subjects_school_id ON class_subjects (school_id)")

    # --- enrolments -------------------------------------------------------
    op.execute(
        """
        CREATE TABLE enrolments (
            id          UUID PRIMARY KEY,
            school_id   UUID NOT NULL REFERENCES schools(id),
            student_id  UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
            session_id  UUID NOT NULL REFERENCES academic_sessions(id),
            class_id    UUID NOT NULL REFERENCES classes(id),
            section_id  UUID REFERENCES sections(id),
            status      enrolmentstatus NOT NULL DEFAULT 'enrolled',
            started_on  DATE,
            ended_on    DATE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            version     INT NOT NULL DEFAULT 1
        )
        """
    )
    # One live enrolment per student per session (spec §6.3).
    op.execute(
        "CREATE UNIQUE INDEX ux_enrolments_student_session ON enrolments (student_id, session_id) "
        "WHERE status = 'enrolled'"
    )
    op.execute("CREATE INDEX ix_enrolments_school_id ON enrolments (school_id)")
    op.execute("CREATE INDEX ix_enrolments_student_id ON enrolments (student_id)")
    op.execute("CREATE INDEX ix_enrolments_session_class ON enrolments (school_id, session_id, class_id)")

    op.execute(
        """
        CREATE TABLE subject_enrolments (
            id                UUID PRIMARY KEY,
            school_id         UUID NOT NULL REFERENCES schools(id),
            enrolment_id      UUID NOT NULL REFERENCES enrolments(id) ON DELETE CASCADE,
            class_subject_id  UUID NOT NULL REFERENCES class_subjects(id) ON DELETE CASCADE,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (enrolment_id, class_subject_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_subject_enrolments_school_id ON subject_enrolments (school_id)"
    )

    # --- teacher assignments ---------------------------------------------
    op.execute(
        """
        CREATE TABLE teacher_assignments (
            id              UUID PRIMARY KEY,
            school_id       UUID NOT NULL REFERENCES schools(id),
            teacher_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            session_id      UUID NOT NULL REFERENCES academic_sessions(id),
            class_id        UUID NOT NULL REFERENCES classes(id),
            section_id      UUID REFERENCES sections(id),
            subject_id      UUID REFERENCES subjects(id),
            role            teacherrole NOT NULL DEFAULT 'subject',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_teacher_assignments_school_teacher_session "
        "ON teacher_assignments (school_id, teacher_user_id, session_id)"
    )
    op.execute("CREATE INDEX ix_teacher_assignments_school_id ON teacher_assignments (school_id)")

    # --- promotions -------------------------------------------------------
    op.execute(
        """
        CREATE TABLE promotion_records (
            id                 UUID PRIMARY KEY,
            school_id          UUID NOT NULL REFERENCES schools(id),
            student_id         UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
            from_enrolment_id  UUID NOT NULL REFERENCES enrolments(id),
            to_enrolment_id    UUID REFERENCES enrolments(id),
            decision           VARCHAR(20) NOT NULL,
            decided_by         UUID REFERENCES users(id),
            decided_at         TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_promotion_records_school_id ON promotion_records (school_id)")
    op.execute(
        "CREATE INDEX ix_promotion_records_student ON promotion_records (student_id)"
    )

    # --- RLS --------------------------------------------------------------
    # sessions: no RLS — the refresh token hash IS the bearer credential.
    for table in (
        "students",
        "guardians",
        "student_guardians",
        "academic_sessions",
        "terms",
        "educational_levels",
        "classes",
        "sections",
        "subjects",
        "class_subjects",
        "enrolments",
        "subject_enrolments",
        "teacher_assignments",
        "promotion_records",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING (school_id = current_setting('app.school_id', true)::uuid)"
        )

    # --- Seed: Nigerian default structure (spec §6 Phase 2 seed) ----------
    # Levels and classes for the seeded school only; schools added later
    # create their own structure (or a later seed run per school).
    seed_school = "00000000-0000-7000-8000-000000000001"

    # Fixed UUIDs (same convention as the seeded Super Admin role in 0002).
    level_rows = [
        ("00000000-0000-7000-8000-000000000101", "Nursery", 0),
        ("00000000-0000-7000-8000-000000000102", "Primary", 1),
        ("00000000-0000-7000-8000-000000000103", "JSS", 2),
        ("00000000-0000-7000-8000-000000000104", "SS", 3),
    ]
    for level_id, name, ordinal in level_rows:
        op.execute(
            f"INSERT INTO educational_levels (id, school_id, name, ordinal) "
            f"VALUES ('{level_id}', '{seed_school}', '{name}', {ordinal}) "
            f"ON CONFLICT (school_id, name) DO NOTHING"
        )

    classes_seed: list[tuple[str, str, int]] = [
        ("Nursery 1", "00000000-0000-7000-8000-000000000101", 1),
        ("Nursery 2", "00000000-0000-7000-8000-000000000101", 2),
        ("Nursery 3", "00000000-0000-7000-8000-000000000101", 3),
        ("Primary 1", "00000000-0000-7000-8000-000000000102", 1),
        ("Primary 2", "00000000-0000-7000-8000-000000000102", 2),
        ("Primary 3", "00000000-0000-7000-8000-000000000102", 3),
        ("Primary 4", "00000000-0000-7000-8000-000000000102", 4),
        ("Primary 5", "00000000-0000-7000-8000-000000000102", 5),
        ("Primary 6", "00000000-0000-7000-8000-000000000102", 6),
        ("JSS 1", "00000000-0000-7000-8000-000000000103", 1),
        ("JSS 2", "00000000-0000-7000-8000-000000000103", 2),
        ("JSS 3", "00000000-0000-7000-8000-000000000103", 3),
        ("SS 1", "00000000-0000-7000-8000-000000000104", 1),
        ("SS 2", "00000000-0000-7000-8000-000000000104", 2),
        ("SS 3", "00000000-0000-7000-8000-000000000104", 3),
    ]
    for name, level_id, ordinal in classes_seed:
        op.execute(
            f"INSERT INTO classes (id, school_id, level_id, name, ordinal) "
            f"VALUES (gen_random_uuid(), '{seed_school}', '{level_id}', '{name}', {ordinal}) "
            f"ON CONFLICT (school_id, name) DO NOTHING"
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS promotion_records")
    op.execute("DROP TABLE IF EXISTS teacher_assignments")
    op.execute("DROP TABLE IF EXISTS subject_enrolments")
    op.execute("DROP TABLE IF EXISTS enrolments")
    op.execute("DROP TABLE IF EXISTS class_subjects")
    op.execute("DROP TABLE IF EXISTS subjects")
    op.execute("DROP TABLE IF EXISTS sections")
    op.execute("DROP TABLE IF EXISTS classes")
    op.execute("DROP TABLE IF EXISTS educational_levels")
    op.execute("DROP TABLE IF EXISTS terms")
    op.execute("DROP TABLE IF EXISTS academic_sessions")
    op.execute("DROP TABLE IF EXISTS student_guardians")
    op.execute("DROP TABLE IF EXISTS guardians")
    op.execute("DROP TABLE IF EXISTS students")
    op.execute("DROP TYPE IF EXISTS teacherrole")
    op.execute("DROP TYPE IF EXISTS enrolmentstatus")
    op.execute("DROP TYPE IF EXISTS studentstatus")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")


# Entry point called by Alembic
def upgrade() -> None:
    _upgrade()
