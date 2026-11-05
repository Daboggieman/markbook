"""Phase 3 API tests — direct HTTP through the app (spec §16 Phase 3 exit).

The exit criterion "teacher cannot enter scores outside assignment" is proven
HERE, over the real app: real Postgres (testcontainers), grants loaded by the
`require` dependency from seeded role_permissions, cryptographically valid
JWTs, RLS tenant context set from the token — the production path end to end.

Each test seeds its OWN school (fresh uuid4) so tests stay independent on the
session-scoped testcontainer.
"""

# ruff: noqa: S608  — fixed literal SQL seeding against the testcontainer owner.

import json
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.identity.tokens import create_access_token
from app.platform import db as platform_db

pytestmark = pytest.mark.db

DEFINITION = {
    "components": [
        {"key": "CA1", "label": "First CA", "max_score": "10.00", "weight": "10", "required": True},
        {"key": "Exam", "label": "Exam", "max_score": "60.00", "weight": "60", "required": True},
    ]
}


@dataclass
class World:
    maker: async_sessionmaker
    client: AsyncClient
    school_id: UUID
    admin_token: str
    teacher_token: str
    template_id: UUID
    version_id: UUID
    assessment_id: UUID
    session_id: UUID
    term_id: UUID
    class_id: UUID
    subject_id: UUID
    se_ids: list[UUID] = field(default_factory=list)

    def auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}


async def _seed_world(maker: async_sessionmaker) -> World:
    school, admin, teacher = uuid4(), uuid4(), uuid4()
    admin_role, teacher_role = uuid4(), uuid4()
    level, klass, subject, class_subject = uuid4(), uuid4(), uuid4(), uuid4()
    session_, term = uuid4(), uuid4()
    template, version, assessment = uuid4(), uuid4(), uuid4()
    student1, student2 = uuid4(), uuid4()
    enrol1, enrol2 = uuid4(), uuid4()
    se1, se2 = uuid4(), uuid4()

    async with maker() as s:
        for stmt, params in [
            (
                "INSERT INTO schools (id, name) VALUES (:id, 'Phase 3 API')",
                {"id": school},
            ),
            *[
                (
                    "INSERT INTO users (id, school_id, email, username, password_hash, "
                    "is_super_admin, status, token_version, failed_login_count) "
                    "VALUES (:id, :s, :email, :username, 'x', false, 'active', 1, 0)",
                    {
                        "id": user,
                        "s": school,
                        "email": f"{UUID(user).hex[:8]}@phase3.local",
                        "username": f"u{UUID(user).hex[:8]}",
                    },
                )
                for user in (admin, teacher)
            ],
            (
                "INSERT INTO roles (id, school_id, name) VALUES (:id, :s, 'Admin')",
                {"id": admin_role, "s": school},
            ),
            (
                "INSERT INTO roles (id, school_id, name) VALUES (:id, :s, 'Teacher')",
                {"id": teacher_role, "s": school},
            ),
            *[
                (
                    "INSERT INTO role_permissions (role_id, permission_code, scope_type) "
                    "VALUES (:r, :p, :scope)",
                    {"r": admin_role, "p": code, "scope": "school"},
                )
                for code in (
                    "assessments.view",
                    "assessments.manage",
                    "scores.enter",
                    "scores.view",
                )
            ],
            *[
                (
                    "INSERT INTO role_permissions (role_id, permission_code, scope_type) "
                    "VALUES (:r, :p, :scope)",
                    {"r": teacher_role, "p": code, "scope": "assigned"},
                )
                for code in ("assessments.view", "scores.enter", "scores.view")
            ],
            (
                "INSERT INTO user_roles (user_id, role_id, school_id) VALUES (:u, :r, :s)",
                {"u": admin, "r": admin_role, "s": school},
            ),
            (
                "INSERT INTO user_roles (user_id, role_id, school_id) VALUES (:u, :r, :s)",
                {"u": teacher, "r": teacher_role, "s": school},
            ),
            (
                "INSERT INTO educational_levels (id, school_id, name, ordinal) "
                "VALUES (:id, :s, 'JSS', 2)",
                {"id": level, "s": school},
            ),
            (
                "INSERT INTO classes (id, school_id, level_id, name, ordinal) "
                "VALUES (:id, :s, :l, 'JSS 1', 1)",
                {"id": klass, "s": school, "l": level},
            ),
            (
                "INSERT INTO subjects (id, school_id, name) VALUES (:id, :s, 'Mathematics')",
                {"id": subject, "s": school},
            ),
            (
                "INSERT INTO class_subjects (id, school_id, class_id, subject_id) "
                "VALUES (:id, :s, :c, :sub)",
                {"id": class_subject, "s": school, "c": klass, "sub": subject},
            ),
            (
                "INSERT INTO academic_sessions (id, school_id, name, is_current) "
                "VALUES (:id, :s, '2025/2026', true)",
                {"id": session_, "s": school},
            ),
            (
                "INSERT INTO terms (id, school_id, session_id, name, ordinal) "
                "VALUES (:id, :s, :a, 'First Term', 1)",
                {"id": term, "s": school, "a": session_},
            ),
            (
                "INSERT INTO assessment_templates (id, school_id, name) "
                "VALUES (:id, :s, 'Default template')",
                {"id": template, "s": school},
            ),
            (
                "INSERT INTO assessment_template_versions "
                "(id, school_id, template_id, version_no, status, definition) "
                "VALUES (:id, :s, :t, 1, 'active', :def)",
                {"id": version, "s": school, "t": template, "def": json.dumps(DEFINITION)},
            ),
            (
                "INSERT INTO assessments (id, school_id, term_id, class_id, section_id, "
                "subject_id, template_version_id) "
                "VALUES (:id, :s, :t, :c, NULL, :sub, :v)",
                {
                    "id": assessment,
                    "s": school,
                    "t": term,
                    "c": klass,
                    "sub": subject,
                    "v": version,
                },
            ),
            *[
                (
                    "INSERT INTO students (id, school_id, first_name, last_name, admission_no, "
                    "status) VALUES (:id, :s, :fn, :ln, :adm, 'active')",
                    {
                        "id": student,
                        "s": school,
                        "fn": fn,
                        "ln": ln,
                        "adm": f"ADM-{n}",
                    },
                )
                for n, (student, fn, ln) in enumerate(
                    [(student1, "Adaeze", "Okafor"), (student2, "Chidi", "Bello")], start=1
                )
            ],
            *[
                (
                    "INSERT INTO enrolments (id, school_id, student_id, session_id, class_id, "
                    "status) VALUES (:id, :s, :st, :a, :c, 'enrolled')",
                    {"id": enrol, "s": school, "st": student, "a": session_, "c": klass},
                )
                for enrol, student in [(enrol1, student1), (enrol2, student2)]
            ],
            *[
                (
                    "INSERT INTO subject_enrolments (id, school_id, enrolment_id, "
                    "class_subject_id) VALUES (:id, :s, :e, :cs)",
                    {"id": se, "s": school, "e": enrol, "cs": class_subject},
                )
                for se, enrol in [(se1, enrol1), (se2, enrol2)]
            ],
        ]:
            await s.execute(text(stmt), params)
        await s.commit()

    admin_token, _ = create_access_token(
        user_id=admin, school_id=school, token_version=1, session_id=uuid4()
    )
    teacher_token, _ = create_access_token(
        user_id=teacher, school_id=school, token_version=1, session_id=uuid4()
    )
    return World(
        maker=maker,
        client=None,  # set by the fixture below
        school_id=school,
        admin_token=admin_token,
        teacher_token=teacher_token,
        template_id=template,
        version_id=version,
        assessment_id=assessment,
        session_id=session_,
        term_id=term,
        class_id=klass,
        subject_id=subject,
        se_ids=[se1, se2],
    )


@pytest.fixture
async def world(migrated_url: str, monkeypatch):
    """App wired at the testcontainer DB + one fully seeded school.

    The app's platform sessionmaker is redirected to the testcontainer so the
    `require` dependency and `get_actor_db` both hit the migrated database —
    the same seam production uses (the engine built from settings).
    """
    engine = create_async_engine(migrated_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(platform_db, "_sessionmaker", maker)
    from app.main import create_app

    w = await _seed_world(maker)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        w.client = client
        yield w
    await engine.dispose()


def _cell(se_id: UUID, key: str, status: str, value=None, base_version=None) -> dict:
    return {
        "subject_enrolment_id": str(se_id),
        "component_key": key,
        "status": status,
        "value": value,
        "base_version": base_version,
    }


class TestTemplatesAndVersions:
    async def test_create_template_makes_draft_version(self, world) -> None:
        r = await world.client.post(
            "/api/v1/assessment-templates",
            json={"name": "Nursery template", "definition": DEFINITION},
            headers=world.auth(world.admin_token),
        )
        assert r.status_code == 201
        versions = await world.client.get(
            f"/api/v1/assessment-templates/{r.json()['id']}/versions",
            headers=world.auth(world.admin_token),
        )
        assert versions.status_code == 200
        rows = versions.json()
        assert len(rows) == 1
        assert rows[0]["version_no"] == 1 and rows[0]["status"] == "draft"

    async def test_editing_creates_new_version_and_activate_retires_old(self, world) -> None:
        """The Phase 3 exit criterion at the template level: editing creates a
        NEW version; activating one retires the previous active; existing
        assessments keep their pinned version."""
        r1 = await world.client.post(
            f"/api/v1/assessment-templates/{world.template_id}/versions",
            json={"definition": DEFINITION},
            headers=world.auth(world.admin_token),
        )
        assert r1.status_code == 201
        v2 = r1.json()
        assert v2["version_no"] == 2 and v2["status"] == "draft"

        r2 = await world.client.post(
            f"/api/v1/template-versions/{world.version_id}/activate",
            headers=world.auth(world.admin_token),
        )
        assert r2.status_code == 200  # idempotent: already active

        r3 = await world.client.post(
            f"/api/v1/template-versions/{v2['id']}/activate",
            headers=world.auth(world.admin_token),
        )
        assert r3.status_code == 200 and r3.json()["status"] == "active"

        versions = (
            await world.client.get(
                f"/api/v1/assessment-templates/{world.template_id}/versions",
                headers=world.auth(world.admin_token),
            )
        ).json()
        by_no = {v["version_no"]: v["status"] for v in versions}
        assert by_no == {1: "retired", 2: "active"}

        retired = await world.client.post(
            f"/api/v1/template-versions/{world.version_id}/activate",
            headers=world.auth(world.admin_token),
        )
        assert retired.status_code == 409
        assert retired.json()["code"] == "INVALID_STATE_TRANSITION"


class TestAssessments:
    async def test_draft_version_rejected_for_assessment(self, world) -> None:
        r1 = await world.client.post(
            f"/api/v1/assessment-templates/{world.template_id}/versions",
            json={"definition": DEFINITION},
            headers=world.auth(world.admin_token),
        )
        r2 = await world.client.post(
            "/api/v1/assessments",
            json={
                "term_id": str(world.term_id),
                "class_id": str(world.class_id),
                "subject_id": str(world.subject_id),
                "template_version_id": r1.json()["id"],
            },
            headers=world.auth(world.admin_token),
        )
        assert r2.status_code == 422
        assert r2.json()["code"] == "VALIDATION_ERROR"

    async def test_duplicate_assessment_conflict(self, world) -> None:
        r = await world.client.post(
            "/api/v1/assessments",
            json={
                "term_id": str(world.term_id),
                "class_id": str(world.class_id),
                "subject_id": str(world.subject_id),
                "template_version_id": str(world.version_id),
            },
            headers=world.auth(world.admin_token),
        )
        assert r.status_code == 409
        assert r.json()["code"] == "CONFLICT"

    async def test_list_respects_assigned_scope(self, world) -> None:
        """Assigned-scope teacher sees only assessments their assignments
        cover; before any assignment exists, that is none."""
        r = await world.client.get(
            "/api/v1/assessments", headers=world.auth(world.teacher_token)
        )
        assert r.status_code == 200
        assert r.json() == []


class TestScoreEntry:
    async def test_zero_is_real_and_roundtrips_through_the_sheet(self, world) -> None:
        """The zero-vs-missing invariant over HTTP: ('entered', 0.00) persists
        and reads back as a real value, not NULL."""
        r = await world.client.put(
            f"/api/v1/assessments/{world.assessment_id}/scores",
            json={
                "rows": [
                    _cell(world.se_ids[0], "CA1", "entered", "0.00"),
                    _cell(world.se_ids[1], "CA1", "absent"),
                ]
            },
            headers=world.auth(world.admin_token),
        )
        assert r.status_code == 200
        cells = {(c["component_key"], c["subject_enrolment_id"]): c for c in r.json()}
        assert len(cells) == 2
        entered = next(iter(cells.values()))
        assert entered["status"] == "entered"
        assert float(entered["value"]) == 0.0  # JSON transport check only; domain stays Decimal
        assert entered["version"] == 1

        sheet = await world.client.get(
            f"/api/v1/assessments/{world.assessment_id}/sheet",
            headers=world.auth(world.admin_token),
        )
        assert sheet.status_code == 200
        body = sheet.json()
        assert body["workflow_state"] == "draft"
        assert {c["key"] for c in body["components"]} == {"CA1", "Exam"}
        by_se = {row["subject_enrolment_id"]: row for row in body["rows"]}
        assert len(by_se) == 2
        assert by_se[str(world.se_ids[0])]["scores"]["CA1"]["status"] == "entered"
        assert by_se[str(world.se_ids[1])]["scores"]["CA1"]["status"] == "absent"
        assert "value" not in by_se[str(world.se_ids[1])]["scores"]["CA1"] or (
            by_se[str(world.se_ids[1])]["scores"]["CA1"]["value"] is None
        )

    async def test_stale_base_version_conflicts(self, world) -> None:
        first = await world.client.put(
            f"/api/v1/assessments/{world.assessment_id}/scores",
            json={"rows": [_cell(world.se_ids[0], "Exam", "entered", "40.00")]},
            headers=world.auth(world.admin_token),
        )
        assert first.status_code == 200
        version = first.json()[0]["version"]

        stale = await world.client.put(
            f"/api/v1/assessments/{world.assessment_id}/scores",
            json={
                "rows": [
                    _cell(world.se_ids[0], "Exam", "entered", "45.00", base_version=version)
                ]
            },
            headers=world.auth(world.admin_token),
        )
        assert stale.status_code == 200
        assert stale.json()[0]["version"] == version + 1

        replay = await world.client.put(
            f"/api/v1/assessments/{world.assessment_id}/scores",
            json={
                "rows": [
                    _cell(world.se_ids[0], "Exam", "entered", "50.00", base_version=version)
                ]
            },
            headers=world.auth(world.admin_token),
        )
        assert replay.status_code == 409
        assert replay.json()["code"] == "VERSION_CONFLICT"

    async def test_existing_cell_requires_base_version(self, world) -> None:
        await world.client.put(
            f"/api/v1/assessments/{world.assessment_id}/scores",
            json={"rows": [_cell(world.se_ids[0], "Exam", "entered", "40.00")]},
            headers=world.auth(world.admin_token),
        )
        r = await world.client.put(
            f"/api/v1/assessments/{world.assessment_id}/scores",
            json={"rows": [_cell(world.se_ids[0], "Exam", "entered", "41.00")]},
            headers=world.auth(world.admin_token),
        )
        assert r.status_code == 409
        assert r.json()["code"] == "VERSION_CONFLICT"

    async def test_validation_rejects_bad_cells(self, world) -> None:
        cases = [
            _cell(world.se_ids[0], "Quiz", "entered", "5.00"),  # unknown component
            _cell(world.se_ids[0], "CA1", "entered", "11.00"),  # above max 10
            _cell(world.se_ids[0], "CA1", "entered", None),  # entered without value
            _cell(world.se_ids[0], "CA1", "missing", "5.00"),  # value on missing
            _cell(uuid4(), "CA1", "entered", "5.00"),  # off-sheet enrolment
        ]
        r = await world.client.put(
            f"/api/v1/assessments/{world.assessment_id}/scores",
            json={"rows": cases},
            headers=world.auth(world.admin_token),
        )
        assert r.status_code == 422
        body = r.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert len(body["errors"]) == 5  # ALL bad cells reported, not just the first

    async def test_history_endpoint(self, world) -> None:
        first = await world.client.put(
            f"/api/v1/assessments/{world.assessment_id}/scores",
            json={"rows": [_cell(world.se_ids[0], "Exam", "entered", "40.00")]},
            headers=world.auth(world.admin_token),
        )
        score_id = first.json()[0]["id"]
        await world.client.put(
            f"/api/v1/assessments/{world.assessment_id}/scores",
            json={"rows": [_cell(world.se_ids[0], "Exam", "entered", "45.00", base_version=1)]},
            headers=world.auth(world.admin_token),
        )
        history = await world.client.get(
            f"/api/v1/scores/{score_id}/history", headers=world.auth(world.admin_token)
        )
        assert history.status_code == 200
        entries = history.json()
        assert len(entries) == 2
        assert entries[0]["old_status"] is None and entries[0]["new_status"] == "entered"
        assert entries[1]["old_value"] == "40.00" or float(entries[1]["old_value"]) == 40.0
        assert entries[1]["source"] == "web"

    async def test_scores_frozen_once_submitted(self, world) -> None:
        async with world.maker() as s:
            await s.execute(
                text("UPDATE assessments SET workflow_state = 'submitted' WHERE id = :id"),
                {"id": world.assessment_id},
            )
            await s.commit()
        r = await world.client.put(
            f"/api/v1/assessments/{world.assessment_id}/scores",
            json={"rows": [_cell(world.se_ids[0], "CA1", "entered", "5.00")]},
            headers=world.auth(world.admin_token),
        )
        assert r.status_code == 409
        assert r.json()["code"] == "INVALID_STATE_TRANSITION"


class TestTeacherScope:
    async def test_teacher_outside_assignment_cannot_enter(self, world) -> None:
        """THE Phase 3 exit criterion: a teacher holding scores.enter with the
        `assigned` scope gets 403 against an assessment they are not assigned
        to — proven over direct HTTP, not by unit-call."""
        r = await world.client.put(
            f"/api/v1/assessments/{world.assessment_id}/scores",
            json={"rows": [_cell(world.se_ids[0], "CA1", "entered", "5.00")]},
            headers=world.auth(world.teacher_token),
        )
        assert r.status_code == 403
        assert r.json()["code"] == "PERMISSION_DENIED"

        # The import door is checked at enqueue time too.
        imp = await world.client.post(
            f"/api/v1/assessments/{world.assessment_id}/scores/import",
            json={"csv": "subject_enrolment_id,component_key,status,value\n"},
            headers=world.auth(world.teacher_token),
        )
        assert imp.status_code == 403

    async def test_teacher_inside_assignment_can_enter(self, world) -> None:
        """The mirror image: with a covering assignment (whole class, whole
        subject), the same teacher scores the same sheet with 200."""
        async with world.maker() as s:
            await s.execute(
                text(
                    "INSERT INTO teacher_assignments (id, school_id, teacher_user_id, "
                    "session_id, class_id, section_id, subject_id, role) "
                    "VALUES (:id, :s, :t, :a, :c, NULL, :sub, 'subject')"
                ),
                {
                    "id": uuid4(),
                    "s": world.school_id,
                    "t": _teacher_user_id(world),
                    "a": world.session_id,
                    "c": world.class_id,
                    "sub": world.subject_id,
                },
            )
            await s.commit()
        r = await world.client.put(
            f"/api/v1/assessments/{world.assessment_id}/scores",
            json={"rows": [_cell(world.se_ids[0], "CA1", "entered", "5.00")]},
            headers=world.auth(world.teacher_token),
        )
        assert r.status_code == 200
        assert r.json()[0]["status"] == "entered"

        listing = await world.client.get(
            "/api/v1/assessments", headers=world.auth(world.teacher_token)
        )
        assert [a["id"] for a in listing.json()] == [str(world.assessment_id)]


def _teacher_user_id(world: World) -> UUID:
    """The teacher user's id, recovered from their token claims."""
    from app.identity.tokens import decode_access_token

    return UUID(decode_access_token(world.teacher_token)["sub"])


class TestBulkImport:
    async def test_import_applies_valid_rows_and_reports_bad_ones(self, world) -> None:
        """Row-level partial success (spec §16 Phase 3): one valid row, one
        invalid combo ('missing' with a value), one unparseable uuid."""
        csv_text = (
            "subject_enrolment_id,component_key,status,value\n"
            f"{world.se_ids[0]},CA1,entered,7.50\n"
            f"{world.se_ids[1]},CA1,missing,5.00\n"
            "not-a-uuid,CA1,entered,1.00\n"
        )
        r = await world.client.post(
            f"/api/v1/assessments/{world.assessment_id}/scores/import",
            json={"csv": csv_text},
            headers=world.auth(world.admin_token),
        )
        assert r.status_code == 202
        job_id = r.json()["job_id"]
        assert r.json()["status_url"] == f"/api/v1/jobs/{job_id}"

        from app.assessment.jobs import import_scores

        await import_scores({}, job_id=job_id)  # the worker's exact entry point

        job = await world.client.get(
            f"/api/v1/jobs/{job_id}", headers=world.auth(world.admin_token)
        )
        assert job.status_code == 200
        body = job.json()
        assert body["status"] == "succeeded"
        assert body["type"] == "import_scores"
        assert body["result"]["applied"] == 1
        # Row numbers are 1-based CSV DATA rows (header unnumbered): row 2 is
        # the 'missing' row carrying a value, row 3 the unparseable uuid.
        assert {e["row"] for e in body["result"]["errors"]} == {2, 3}

        sheet = await world.client.get(
            f"/api/v1/assessments/{world.assessment_id}/sheet",
            headers=world.auth(world.admin_token),
        )
        by_se = {row["subject_enrolment_id"]: row for row in sheet.json()["rows"]}
        cell = by_se[str(world.se_ids[0])]["scores"]["CA1"]
        assert cell["status"] == "entered" and float(cell["value"]) == 7.5

        # ...and the ledger records the import as the source.
        history = await world.client.get(
            f"/api/v1/scores/{cell['id']}/history", headers=world.auth(world.admin_token)
        )
        assert history.json()[0]["source"] == "import"
        assert history.json()[0]["reason"] == "bulk import"

    async def test_import_of_score_that_already_exists_reports_not_overwrites(
        self, world
    ) -> None:
        """A re-import without base_version must NOT silently overwrite
        entered scores — the row is reported instead."""
        await world.client.put(
            f"/api/v1/assessments/{world.assessment_id}/scores",
            json={"rows": [_cell(world.se_ids[0], "CA1", "entered", "5.00")]},
            headers=world.auth(world.admin_token),
        )
        csv_text = (
            "subject_enrolment_id,component_key,status,value\n"
            f"{world.se_ids[0]},CA1,entered,9.99\n"
        )
        r = await world.client.post(
            f"/api/v1/assessments/{world.assessment_id}/scores/import",
            json={"csv": csv_text},
            headers=world.auth(world.admin_token),
        )
        job_id = r.json()["job_id"]
        from app.assessment.jobs import import_scores

        await import_scores({}, job_id=job_id)

        job = await world.client.get(
            f"/api/v1/jobs/{job_id}", headers=world.auth(world.admin_token)
        )
        body = job.json()
        assert body["status"] == "succeeded"  # the RUN succeeded; the row was reported
        assert body["result"]["applied"] == 0
        assert "base_version" in body["result"]["errors"][0]["detail"]

        # The original value survived untouched.
        sheet = await world.client.get(
            f"/api/v1/assessments/{world.assessment_id}/sheet",
            headers=world.auth(world.admin_token),
        )
        by_se = {row["subject_enrolment_id"]: row for row in sheet.json()["rows"]}
        assert float(by_se[str(world.se_ids[0])]["scores"]["CA1"]["value"]) == 5.0


class TestJobRoute:
    async def test_unknown_job_404(self, world) -> None:
        r = await world.client.get(
            f"/api/v1/jobs/{uuid4()}", headers=world.auth(world.admin_token)
        )
        assert r.status_code == 404
