"""Phase 4 API tests — schemes, processing, results over real HTTP (spec §16 Phase 4).

The centerpiece is the spec §9.3 golden example run end to end: scores entered
through the Phase 3 sheet API, a scheme saved through the Phase 4 API, the
process endpoint queueing a real Job, the worker's exact entry point
(`process_results`) applying it, and the results endpoint reading the run back.
Determinism (§9.4), the block-policy whole-run failure, and the permission
gates are proven on the same path.

Each test seeds its OWN school (fresh uuid4) so tests stay independent on the
session-scoped testcontainer.
"""

# ruff: noqa: S608  — fixed literal SQL seeding against the testcontainer owner.

import json
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.identity.tokens import create_access_token
from app.platform import db as platform_db

pytestmark = pytest.mark.db

GOLDEN_TEMPLATE = {
    "components": [
        {"key": "CA1", "label": "First CA", "max_score": "10.00", "weight": "10", "required": True},
        {
            "key": "CA2",
            "label": "Second CA",
            "max_score": "10.00",
            "weight": "10",
            "required": True,
        },
        {"key": "Test", "label": "Test", "max_score": "20.00", "weight": "20", "required": True},
        {"key": "Exam", "label": "Exam", "max_score": "60.00", "weight": "60", "required": True},
    ]
}

GOLDEN_SCHEME = {
    "rounding_mode": "ROUND_HALF_UP",
    "precision": 0,
    "missing_policy": "flag_incomplete",
    "absent_policy": "treat_zero",
    "exempt_policy": "exclude_and_renormalise",
    "boundaries": [
        {"grade": "A", "min": 70, "max": 100},
        {"grade": "B", "min": 60, "max": 69},
        {"grade": "C", "min": 50, "max": 59},
        {"grade": "D", "min": 45, "max": 49},
        {"grade": "E", "min": 40, "max": 44},
        {"grade": "F", "min": 0, "max": 39},
    ],
    "tie_policy": "dense",
}

# Spec §9.3's five students: (component_key, status, value). Dara's CA2 is
# absent (treat_zero), Efe's Test is exempt (excluded + renormalise).
GOLDEN_SCORES = {
    "ada": [
        ("CA1", "entered", "8.00"),
        ("CA2", "entered", "7.00"),
        ("Test", "entered", "15.00"),
        ("Exam", "entered", "48.00"),
    ],  # 78 → A
    "bayo": [
        ("CA1", "entered", "6.00"),
        ("CA2", "entered", "5.00"),
        ("Test", "entered", "12.00"),
        ("Exam", "entered", "40.00"),
    ],  # 63 → B
    "chidi": [
        ("CA1", "entered", "5.00"),
        ("CA2", "entered", "4.50"),
        ("Test", "entered", "9.00"),
        ("Exam", "entered", "31.00"),
    ],  # 49.5 → HALF_UP 50 → C
    "dara": [
        ("CA1", "entered", "9.00"),
        ("CA2", "absent", None),
        ("Test", "entered", "18.00"),
        ("Exam", "entered", "52.00"),
    ],  # absent→0: 79 → A
    "efe": [
        ("CA1", "entered", "7.00"),
        ("CA2", "entered", "6.00"),
        ("Test", "exempt", None),
        ("Exam", "entered", "45.00"),
    ],  # (7+6+45)/80*100 = 72.5 → 73 → A, renormalised
}
GOLDEN_EXPECTED = {
    "ada": (78, "A"),
    "bayo": (63, "B"),
    "chidi": (50, "C"),
    "dara": (79, "A"),
    "efe": (73, "A"),
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
    students = {name: uuid4() for name in GOLDEN_SCORES}
    enrols = {name: uuid4() for name in GOLDEN_SCORES}
    ses = {name: uuid4() for name in GOLDEN_SCORES}

    async with maker() as s:
        stmts: list[tuple[str, dict]] = [
            ("INSERT INTO schools (id, name) VALUES (:id, 'Phase 4 API')", {"id": school}),
            *[
                (
                    "INSERT INTO users (id, school_id, email, username, password_hash, "
                    "is_super_admin, status, token_version, failed_login_count) "
                    "VALUES (:id, :s, :email, :username, 'x', false, 'active', 1, 0)",
                    {
                        "id": user,
                        "s": school,
                        "email": f"{user.hex[:8]}@phase4.local",
                        "username": f"u{user.hex[:8]}",
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
                    "VALUES (:r, :p, 'school')",
                    {"r": admin_role, "p": code},
                )
                for code in (
                    "assessments.view",
                    "assessments.manage",
                    "scores.enter",
                    "scores.view",
                    "results.process",
                )
            ],
            *[
                (
                    "INSERT INTO role_permissions (role_id, permission_code, scope_type) "
                    "VALUES (:r, :p, 'assigned')",
                    {"r": teacher_role, "p": code},
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
                {"id": version, "s": school, "t": template, "def": json.dumps(GOLDEN_TEMPLATE)},
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
                        "id": students[name],
                        "s": school,
                        "fn": name.capitalize(),
                        "ln": "Test",
                        "adm": f"ADM-{n}",
                    },
                )
                for n, name in enumerate(GOLDEN_SCORES, start=1)
            ],
            *[
                (
                    "INSERT INTO enrolments (id, school_id, student_id, session_id, class_id, "
                    "status) VALUES (:id, :s, :st, :a, :c, 'enrolled')",
                    {
                        "id": enrols[name],
                        "s": school,
                        "st": students[name],
                        "a": session_,
                        "c": klass,
                    },
                )
                for name in GOLDEN_SCORES
            ],
            *[
                (
                    "INSERT INTO subject_enrolments (id, school_id, enrolment_id, "
                    "class_subject_id) VALUES (:id, :s, :e, :cs)",
                    {"id": ses[name], "s": school, "e": enrols[name], "cs": class_subject},
                )
                for name in GOLDEN_SCORES
            ]
        ]
        for stmt, params in stmts:
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
        client=None,  # set by the fixture
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
        se_ids=[ses[name] for name in GOLDEN_SCORES],
    )


@pytest.fixture
async def world(migrated_url: str, monkeypatch):
    """App wired at the testcontainer DB + one fully seeded school."""
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


def _cell(se_id: UUID, key: str, status: str, value=None) -> dict:
    return {
        "subject_enrolment_id": str(se_id),
        "component_key": key,
        "status": status,
        "value": value,
    }


async def _enter_golden(world: World) -> None:
    """Enter the §9.3 scores through the real sheet API."""
    rows = []
    for se_id, cells in zip(world.se_ids, GOLDEN_SCORES.values(), strict=True):
        rows.extend(_cell(se_id, key, status, value) for key, status, value in cells)
    r = await world.client.put(
        f"/api/v1/assessments/{world.assessment_id}/scores",
        json={"rows": rows},
        headers=world.auth(world.admin_token),
    )
    assert r.status_code == 200


async def _create_scheme(
    world: World, name: str = "WAEC standard", definition: dict | None = None
) -> UUID:
    r = await world.client.post(
        "/api/v1/grading-schemes",
        json={"name": name, "definition": definition or GOLDEN_SCHEME},
        headers=world.auth(world.admin_token),
    )
    assert r.status_code == 201
    return UUID(r.json()["id"])


async def _activate(world: World, scheme_id: UUID) -> None:
    r = await world.client.post(
        f"/api/v1/grading-schemes/{scheme_id}/activate",
        headers=world.auth(world.admin_token),
    )
    assert r.status_code == 200


async def _process(world: World, scheme_id: UUID) -> dict:
    """POST /process (202), run the worker's exact entry point, return the job."""
    r = await world.client.post(
        f"/api/v1/assessments/{world.assessment_id}/process",
        json={"scheme_id": str(scheme_id)},
        headers=world.auth(world.admin_token),
    )
    assert r.status_code == 202
    body = r.json()
    assert body["status_url"] == f"/api/v1/jobs/{body['job_id']}"

    from app.grading.jobs import process_results

    await process_results({}, job_id=body["job_id"])  # the worker's exact entry point
    job = await world.client.get(
        f"/api/v1/jobs/{body['job_id']}", headers=world.auth(world.admin_token)
    )
    assert job.status_code == 200
    return job.json()


async def _results(world: World) -> dict:
    r = await world.client.get(
        f"/api/v1/assessments/{world.assessment_id}/results",
        headers=world.auth(world.admin_token),
    )
    assert r.status_code == 200
    return r.json()


class TestSchemeLifecycle:
    async def test_create_starts_draft_v1_and_lists(self, world) -> None:
        scheme_id = await _create_scheme(world)
        got = await world.client.get(
            f"/api/v1/grading-schemes/{scheme_id}", headers=world.auth(world.admin_token)
        )
        assert got.status_code == 200
        body = got.json()
        assert body["status"] == "draft"
        assert body["version_no"] == 1
        assert body["definition"]["boundaries"][0]["grade"] == "A"

        listing = await world.client.get(
            "/api/v1/grading-schemes", headers=world.auth(world.admin_token)
        )
        assert [s["id"] for s in listing.json()] == [str(scheme_id)]

    async def test_same_name_creates_next_version(self, world) -> None:
        """Editing a scheme never rewrites a version — a new name under the
        same name creates the NEXT version (spec §9.4)."""
        v1 = await _create_scheme(world)
        changed = {**GOLDEN_SCHEME, "missing_policy": "treat_zero"}
        v2 = await _create_scheme(world, definition=changed)
        assert v2 != v1

        listing = await world.client.get(
            "/api/v1/grading-schemes", headers=world.auth(world.admin_token)
        )
        by_no = {s["version_no"]: s for s in listing.json()}
        assert set(by_no) == {1, 2}
        assert by_no[1]["definition"]["missing_policy"] == "flag_incomplete"  # untouched
        assert by_no[2]["definition"]["missing_policy"] == "treat_zero"

    async def test_gapped_boundaries_rejected(self, world) -> None:
        gapped = {
            **GOLDEN_SCHEME,
            "boundaries": [
                {"grade": "A", "min": 70, "max": 100},
                {"grade": "F", "min": 0, "max": 39},  # 40–69 uncovered
            ],
        }
        r = await world.client.post(
            "/api/v1/grading-schemes",
            json={"name": "Broken", "definition": gapped},
            headers=world.auth(world.admin_token),
        )
        assert r.status_code == 422
        assert r.json()["code"] == "VALIDATION_ERROR"
        assert "contiguous" in r.json()["detail"]

    async def test_activate_retires_previous_and_blocks_retired(self, world) -> None:
        v1 = await _create_scheme(world)
        await _activate(world, v1)
        v2 = await _create_scheme(world)
        await _activate(world, v2)

        listing = (
            await world.client.get(
                "/api/v1/grading-schemes", headers=world.auth(world.admin_token)
            )
        ).json()
        by_no = {s["version_no"]: s["status"] for s in listing.json()}
        assert by_no == {1: "retired", 2: "active"}

        r = await world.client.post(
            f"/api/v1/grading-schemes/{v1}/activate", headers=world.auth(world.admin_token)
        )
        assert r.status_code == 409
        assert r.json()["code"] == "INVALID_STATE_TRANSITION"

    async def test_process_with_draft_scheme_rejected(self, world) -> None:
        scheme_id = await _create_scheme(world)  # never activated
        r = await world.client.post(
            f"/api/v1/assessments/{world.assessment_id}/process",
            json={"scheme_id": str(scheme_id)},
            headers=world.auth(world.admin_token),
        )
        assert r.status_code == 422
        assert "not active" in r.json()["detail"]


class TestGoldenFlow:
    async def test_golden_example_end_to_end(self, world) -> None:
        """THE Phase 4 exit criterion: spec §9.3's five students, through the
        real HTTP surface, produce the spec's totals, grades, flags and ranks."""
        await _enter_golden(world)
        scheme_id = await _create_scheme(world)
        await _activate(world, scheme_id)

        job = await _process(world, scheme_id)
        assert job["status"] == "succeeded"
        assert job["type"] == "process_results"
        assert job["result"]["processed"] == 5
        assert len(job["result"]["input_hash"]) == 64

        body = await _results(world)
        assert body["run"]["status"] == "succeeded"
        assert body["run"]["scheme_version"] == 1
        assert body["run"]["template_version_id"] == str(world.version_id)
        assert len(body["run"]["input_hash"]) == 64
        assert body["run"]["error"] is None

        by_name = {row["student_name"]: row for row in body["results"]}
        assert set(by_name) == {n.capitalize() + " Test" for n in GOLDEN_SCORES}
        for name, (total, grade) in GOLDEN_EXPECTED.items():
            row = by_name[f"{name.capitalize()} Test"]
            assert float(row["total"]) == total, name
            assert row["grade"] == grade, name

        # Positions (dense, total DESC): Dara 79, Ada 78, Efe 73, Bayo 63, Chidi 50.
        positions = {row["student_name"]: row["position"] for row in body["results"]}
        assert positions == {
            "Dara Test": 1,
            "Ada Test": 2,
            "Efe Test": 3,
            "Bayo Test": 4,
            "Chidi Test": 5,
        }

        # Only Efe carries a flag: renormalised (exempt Test excluded).
        for name, row in by_name.items():
            expected_flags = ["renormalised"] if name == "Efe Test" else []
            assert row["flags"] == expected_flags, name

        # Efe's breakdown shows the exempt Test excluded with no contribution,
        # and the CA1 entry as a real included component.
        efe = by_name["Efe Test"]
        by_key = {b["component_key"]: b for b in efe["breakdown"]}
        assert by_key["Test"]["excluded"] is True
        assert by_key["Test"]["status"] == "exempt"
        assert by_key["CA1"]["excluded"] is False
        assert float(by_key["CA1"]["contribution"]) == 7.0
        # Dara's absent CA2 was treated as zero, not excluded.
        dara = by_name["Dara Test"]
        dara_by_key = {b["component_key"]: b for b in dara["breakdown"]}
        assert dara_by_key["CA2"]["excluded"] is False
        assert float(dara_by_key["CA2"]["contribution"]) == 0.0

    async def test_run_history_records_hash_and_versions(self, world) -> None:
        await _enter_golden(world)
        scheme_id = await _create_scheme(world)
        await _activate(world, scheme_id)
        await _process(world, scheme_id)

        runs = await world.client.get(
            f"/api/v1/assessments/{world.assessment_id}/processing-runs",
            headers=world.auth(world.admin_token),
        )
        assert runs.status_code == 200
        rows = runs.json()
        assert len(rows) == 1
        assert rows[0]["status"] == "succeeded"
        assert rows[0]["scheme_id"] == str(scheme_id)
        assert rows[0]["scheme_version"] == 1
        assert rows[0]["template_version_id"] == str(world.version_id)
        assert len(rows[0]["input_hash"]) == 64


class TestDeterminism:
    async def test_identical_inputs_produce_identical_outputs(self, world) -> None:
        """Spec §9.4: same scores + same scheme version → a second run with
        the same input_hash and byte-identical results; both runs retained."""
        await _enter_golden(world)
        scheme_id = await _create_scheme(world)
        await _activate(world, scheme_id)

        first_job = await _process(world, scheme_id)
        first = await _results(world)

        second_job = await _process(world, scheme_id)  # explicit recalculation
        second = await _results(world)

        assert first_job["result"]["input_hash"] == second_job["result"]["input_hash"]
        assert second["run"]["id"] != first["run"]["id"]  # a NEW run, not a rewrite
        assert second["run"]["input_hash"] == first["run"]["input_hash"]

        def _fingerprint(payload: dict) -> list:
            return [
                (r["subject_enrolment_id"], str(r["total"]), r["grade"], r["position"], r["flags"])
                for r in payload["results"]
            ]

        assert _fingerprint(second) == _fingerprint(first)

        runs = (
            await world.client.get(
                f"/api/v1/assessments/{world.assessment_id}/processing-runs",
                headers=world.auth(world.admin_token),
            )
        ).json()
        assert len(runs) == 2
        assert all(r["status"] == "succeeded" for r in runs)


class TestBlockedRun:
    async def test_block_policy_fails_run_current_results_survive(self, world) -> None:
        """missing_policy=block fails the WHOLE run when a student has
        unresolvable components — and the previous successful run stays
        current (spec §9.4: failed runs never become current)."""
        # Four students scored; Chidi's sheet is left entirely empty → his
        # components resolve to `missing`.
        rows = []
        for se_id, cells in zip(world.se_ids, GOLDEN_SCORES.values(), strict=True):
            if se_id == world.se_ids[2]:  # chidi skipped
                continue
            rows.extend(_cell(se_id, key, status, value) for key, status, value in cells)
        r = await world.client.put(
            f"/api/v1/assessments/{world.assessment_id}/scores",
            json={"rows": rows},
            headers=world.auth(world.admin_token),
        )
        assert r.status_code == 200

        scheme_id = await _create_scheme(world)
        await _activate(world, scheme_id)
        first = await _process(world, scheme_id)
        assert first["status"] == "succeeded"  # flag_incomplete tolerates it

        # v2 of the same scheme name flips to block; activate it (v1 retires).
        blocked_scheme = await _create_scheme(
            world, definition={**GOLDEN_SCHEME, "missing_policy": "block"}
        )
        await _activate(world, blocked_scheme)
        second = await _process(world, blocked_scheme)
        assert second["status"] == "failed"
        assert "missing_policy=block" in second["error"]
        assert str(world.se_ids[2]) in second["error"]

        # The failed run is in history — but the CURRENT results are still
        # run 1's, untouched.
        runs = (
            await world.client.get(
                f"/api/v1/assessments/{world.assessment_id}/processing-runs",
                headers=world.auth(world.admin_token),
            )
        ).json()
        assert [r["status"] for r in runs] == ["failed", "succeeded"]

        body = await _results(world)
        assert body["run"]["id"] == runs[1]["id"]  # the succeeded one
        assert len(body["results"]) == 5
        by_name = {row["student_name"]: row for row in body["results"]}
        assert float(by_name["Chidi Test"]["total"]) == 0.0  # all-missing → zeros, F
        assert by_name["Chidi Test"]["grade"] == "F"
        assert by_name["Chidi Test"]["flags"] == ["incomplete"]


class TestPermissions:
    async def test_teacher_cannot_process(self, world) -> None:
        """The teacher holds scores.enter/view but NOT results.process — the
        recalculation door is checked at the route (403 before any run row)."""
        r = await world.client.post(
            f"/api/v1/assessments/{world.assessment_id}/process",
            json={"scheme_id": str(uuid4())},
            headers=world.auth(world.teacher_token),
        )
        assert r.status_code == 403
        assert r.json()["code"] == "PERMISSION_DENIED"

    async def test_results_before_any_run_404(self, world) -> None:
        r = await world.client.get(
            f"/api/v1/assessments/{world.assessment_id}/results",
            headers=world.auth(world.admin_token),
        )
        assert r.status_code == 404
        assert "No successful processing run" in r.json()["detail"]

    async def test_process_unknown_scheme_404(self, world) -> None:
        r = await world.client.post(
            f"/api/v1/assessments/{world.assessment_id}/process",
            json={"scheme_id": str(uuid4())},
            headers=world.auth(world.admin_token),
        )
        assert r.status_code == 404

    async def test_process_unknown_assessment_404(self, world) -> None:
        scheme_id = await _create_scheme(world)
        r = await world.client.post(
            f"/api/v1/assessments/{uuid4()}/process",
            json={"scheme_id": str(scheme_id)},
            headers=world.auth(world.admin_token),
        )
        assert r.status_code == 404

    async def test_get_unknown_scheme_404(self, world) -> None:
        r = await world.client.get(
            f"/api/v1/grading-schemes/{uuid4()}", headers=world.auth(world.admin_token)
        )
        assert r.status_code == 404


class TestJobReplay:
    async def test_settled_job_is_skipped_not_recomputed(self, world) -> None:
        """A re-delivered process job settles without recomputing — the run
        stays at one succeeded execution and the job result is unchanged."""
        await _enter_golden(world)
        scheme_id = await _create_scheme(world)
        await _activate(world, scheme_id)

        job = await _process(world, scheme_id)
        assert job["status"] == "succeeded"

        from app.grading.jobs import process_results

        await process_results({}, job_id=job["id"])  # re-delivery
        again = await world.client.get(
            f"/api/v1/jobs/{job['id']}", headers=world.auth(world.admin_token)
        )
        assert again.status_code == 200
        assert again.json()["status"] == "succeeded"
        assert again.json()["result"] == job["result"]  # untouched

        runs = (
            await world.client.get(
                f"/api/v1/assessments/{world.assessment_id}/processing-runs",
                headers=world.auth(world.admin_token),
            )
        ).json()
        assert len(runs) == 1  # no second run materialised
