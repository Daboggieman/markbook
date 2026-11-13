"""Phase 5 API tests — workflow, publication, documents over real HTTP.

The exit criteria (spec §16 Phase 5) proven end to end:

  - every LEGAL transition lands (the §10 table walked draft → published,
    including the return → resubmit cycle);
  - every ILLEGAL transition is rejected with 409 INVALID_STATE_TRANSITION;
  - edits are blocked after submit and allowed again after return;
  - the guards: unresolved required components, reviewer ≠ submitter,
    separation of duties (configurable, on by default), a current
    successful processing run before approval;
  - step-up auth: lock demands a fresh re-auth, publish demands re-auth
    WITH MFA; a plain login token never satisfies either;
  - published documents are immutable: identical regeneration is
    idempotent, a correction INSERTs version N+1 superseding N;
  - every action leaves an approval_record, an audit event and an outbox
    event in the ONE transition transaction.

Rendering runs through the worker's exact entry point
(`documents.jobs.report_cards` / `transcripts`) with the seams patched —
no WeasyPrint, no S3, but the real service, repository and SQL.
"""

# ruff: noqa: S608  — fixed literal SQL seeding against the testcontainer owner.

import json
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pyotp
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.documents.storage import checksum_of
from app.identity.service import hash_password
from app.identity.tokens import create_access_token
from app.platform import db as platform_db
from app.platform.outbox import TOPIC_ASSESSMENT_STATE_CHANGED, TOPIC_RESULTS_PUBLISHED

pytestmark = pytest.mark.db

PASSWORD = "Correct-Horse-9"

TEMPLATE = {
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

SCHEME = {
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

# Three students, everything entered — the submit guard passes on these.
STUDENTS = ("ada", "bayo", "chidi")
SCORES = {
    "ada": [
        ("CA1", "entered", "8.00"),
        ("CA2", "entered", "7.00"),
        ("Test", "entered", "15.00"),
        ("Exam", "entered", "48.00"),
    ],
    "bayo": [
        ("CA1", "entered", "6.00"),
        ("CA2", "entered", "5.00"),
        ("Test", "entered", "12.00"),
        ("Exam", "entered", "40.00"),
    ],
    "chidi": [
        ("CA1", "entered", "5.00"),
        ("CA2", "entered", "4.50"),
        ("Test", "entered", "9.00"),
        ("Exam", "entered", "31.00"),
    ],
}

ADMIN_PERMS = (
    "assessments.view",
    "assessments.manage",
    "scores.enter",
    "scores.view",
    "scores.submit",
    "scores.review",
    "results.process",
    "results.approve",
    "results.lock",
    "results.publish",
    "results.correct",
    "reports.view",
    "transcripts.generate",
)
REGISTRAR_PERMS = (
    "assessments.view",
    "scores.view",
    "scores.review",
    "results.approve",
    "results.lock",
    "results.publish",
    "results.correct",
    "reports.view",
    "transcripts.generate",
)
TEACHER_PERMS = ("assessments.view", "scores.enter", "scores.view", "scores.submit")
VIEWER_PERMS = ("assessments.view", "reports.view")


@dataclass
class World:
    maker: async_sessionmaker
    client: AsyncClient | None = None
    school_id: UUID = field(default_factory=uuid4)
    users: dict = field(default_factory=dict)  # name → (user_id, token)
    template_id: UUID = field(default_factory=uuid4)
    version_id: UUID = field(default_factory=uuid4)
    session_id: UUID = field(default_factory=uuid4)
    term_id: UUID = field(default_factory=uuid4)
    class_id: UUID = field(default_factory=uuid4)
    subject_id: UUID = field(default_factory=uuid4)
    class_subject_id: UUID = field(default_factory=uuid4)
    assessment_id: UUID = field(default_factory=uuid4)
    se_ids: dict = field(default_factory=dict)  # student name → subject_enrolment_id
    scheme_id: UUID | None = None

    def auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def token(self, who: str) -> str:
        return self.users[who][1]

    def uid(self, who: str) -> UUID:
        return self.users[who][0]


async def _seed_world(maker: async_sessionmaker) -> World:
    w = World(maker=maker)
    user_ids = {who: uuid4() for who in ("admin", "registrar", "teacher", "viewer")}
    w.users = {who: (uid, "") for who, uid in user_ids.items()}
    ids = {name: uuid4() for name in STUDENTS}
    enrols = {name: uuid4() for name in STUDENTS}
    w.se_ids = {name: uuid4() for name in STUDENTS}
    role_ids = {name: uuid4() for name in ("Admin", "Registrar", "Teacher", "Viewer")}
    role_perms = {
        "Admin": ADMIN_PERMS,
        "Registrar": REGISTRAR_PERMS,
        "Teacher": TEACHER_PERMS,
        "Viewer": VIEWER_PERMS,
    }
    pw_hash = hash_password(PASSWORD)

    stmts: list[tuple[str, dict]] = [
        ("INSERT INTO schools (id, name) VALUES (:id, 'Phase 5 API')", {"id": w.school_id}),
        *[
            (
                "INSERT INTO users (id, school_id, email, username, password_hash, "
                "is_super_admin, status, token_version, failed_login_count) "
                "VALUES (:id, :s, :email, :username, :pw, false, 'active', 1, 0)",
                {
                    "id": uid,
                    "s": w.school_id,
                    "email": f"{who}@phase5.local",
                    "username": f"u_{who}",
                    "pw": pw_hash,
                },
            )
            for who, uid in user_ids.items()
        ],
        *[
            (
                "INSERT INTO roles (id, school_id, name) VALUES (:id, :s, :n)",
                {"id": rid, "s": w.school_id, "n": name},
            )
            for name, rid in role_ids.items()
        ],
        *[
            (
                "INSERT INTO role_permissions (role_id, permission_code, scope_type) "
                "VALUES (:r, :p, :sc)",
                {"r": role_ids[role], "p": perm, "sc": scope},
            )
            for role, perms in role_perms.items()
            for perm in perms
            for scope in (["assigned"] if role == "Teacher" else ["school"])
        ],
        *[
            (
                "INSERT INTO user_roles (user_id, role_id, school_id) VALUES (:u, :r, :s)",
                {"u": w.uid(role.lower()), "r": rid, "s": w.school_id},
            )
            for role, rid in role_ids.items()
        ],
        (
            "INSERT INTO educational_levels (id, school_id, name, ordinal) "
            "VALUES (:id, :s, 'JSS', 2)",
            {"id": uuid4(), "s": w.school_id},
        ),
        (
            "INSERT INTO classes (id, school_id, level_id, name, ordinal) "
            "SELECT :id, :s, id, 'JSS 1', 1 FROM educational_levels WHERE school_id = :s",
            {"id": w.class_id, "s": w.school_id},
        ),
        (
            "INSERT INTO subjects (id, school_id, name) VALUES (:id, :s, 'Mathematics')",
            {"id": w.subject_id, "s": w.school_id},
        ),
        (
            "INSERT INTO class_subjects (id, school_id, class_id, subject_id) "
            "VALUES (:id, :s, :c, :sub)",
            {"id": w.class_subject_id, "s": w.school_id, "c": w.class_id, "sub": w.subject_id},
        ),
        (
            "INSERT INTO academic_sessions (id, school_id, name, is_current) "
            "VALUES (:id, :s, '2025/2026', true)",
            {"id": w.session_id, "s": w.school_id},
        ),
        (
            "INSERT INTO terms (id, school_id, session_id, name, ordinal) "
            "VALUES (:id, :s, :a, 'First Term', 1)",
            {"id": w.term_id, "s": w.school_id, "a": w.session_id},
        ),
        (
            "INSERT INTO assessment_templates (id, school_id, name) VALUES (:id, :s, 'Default')",
            {"id": w.template_id, "s": w.school_id},
        ),
        (
            "INSERT INTO assessment_template_versions "
            "(id, school_id, template_id, version_no, status, definition) "
            "VALUES (:id, :s, :t, 1, 'active', :def)",
            {"id": w.version_id, "s": w.school_id, "t": w.template_id, "def": json.dumps(TEMPLATE)},
        ),
    ]

    async with maker() as s:
        for stmt, params in stmts:
            await s.execute(text(stmt), params)
        for stmt, params in (
            [
                (
                    "INSERT INTO students (id, school_id, first_name, last_name, "
                    "admission_no, status) "
                    "VALUES (:id, :s, :fn, 'Test', :adm, 'active')",
                    {"id": ids[n], "s": w.school_id, "fn": n.capitalize(), "adm": f"ADM-{i}"},
                )
                for i, n in enumerate(STUDENTS, start=1)
            ]
            + [
                (
                    "INSERT INTO enrolments (id, school_id, student_id, session_id, "
                    "class_id, status) "
                    "VALUES (:id, :s, :st, :a, :c, 'enrolled')",
                    {
                        "id": enrols[n],
                        "s": w.school_id,
                        "st": ids[n],
                        "a": w.session_id,
                        "c": w.class_id,
                    },
                )
                for n in STUDENTS
            ]
            + [
                (
                    "INSERT INTO subject_enrolments (id, school_id, enrolment_id, "
                    "class_subject_id) "
                    "VALUES (:id, :s, :e, :cs)",
                    {"id": w.se_ids[n], "s": w.school_id, "e": enrols[n], "cs": w.class_subject_id},
                )
                for n in STUDENTS
            ]
        ):
            await s.execute(text(stmt), params)
        await s.commit()

    w.assessment_id = await _add_assessment(w, w.term_id)

    for who, uid in user_ids.items():
        token, _ = create_access_token(
            user_id=uid, school_id=w.school_id, token_version=1, session_id=uuid4()
        )
        w.users[who] = (uid, token)
    return w


async def _add_assessment(w: World, term_id: UUID) -> UUID:
    assessment = uuid4()
    async with w.maker() as s:
        await s.execute(
            text(
                "INSERT INTO assessments (id, school_id, term_id, class_id, section_id, "
                "subject_id, template_version_id, workflow_state) "
                "VALUES (:id, :s, :t, :c, NULL, :sub, :v, 'draft')"
            ),
            {
                "id": assessment,
                "s": w.school_id,
                "t": term_id,
                "c": w.class_id,
                "sub": w.subject_id,
                "v": w.version_id,
            },
        )
        await s.commit()
    return assessment


def _world_client(world: World, app) -> None:
    world.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def world(migrated_url: str, monkeypatch):
    """App wired at the testcontainer DB + one fully seeded school."""
    engine = create_async_engine(migrated_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(platform_db, "_sessionmaker", maker)
    from app.main import create_app

    w = await _seed_world(maker)
    app = create_app()
    _world_client(w, app)
    async with w.client:
        yield w
    await engine.dispose()


# ---- helpers ---------------------------------------------------------------------


class FakeStorage:
    """In-memory stand-in for S3 — records every put, serves fake URLs."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> str:
        self.objects[key] = data
        return checksum_of(data)

    def presigned_get(self, key: str, expires_in: int) -> str:
        return f"https://objects.test/{key}?expires={expires_in}"


def _cell(se_id: UUID, key: str, status: str, value=None) -> dict:
    return {
        "subject_enrolment_id": str(se_id),
        "component_key": key,
        "status": status,
        "value": value,
    }


async def _enter_scores(w: World, assessment_id: UUID | None = None, *, only=None) -> None:
    assessment_id = assessment_id or w.assessment_id
    # Existing cells carry a version — overwriting one (the return → edit
    # cycle) requires its current version as base_version (Phase 3 contract).
    r = await w.client.get(
        f"/api/v1/assessments/{assessment_id}/sheet", headers=w.auth(w.token("admin"))
    )
    assert r.status_code == 200, r.text
    versions = {
        (str(row["subject_enrolment_id"]), key): cell["version"]
        for row in r.json()["rows"]
        for key, cell in row["scores"].items()
    }
    rows = []
    for name in only or STUDENTS:
        for key, status, value in SCORES[name]:
            cell = _cell(w.se_ids[name], key, status, value)
            prior = versions.get((cell["subject_enrolment_id"], key))
            if prior is not None:
                cell["base_version"] = prior
            rows.append(cell)
    r = await w.client.put(
        f"/api/v1/assessments/{assessment_id}/scores",
        json={"rows": rows},
        headers=w.auth(w.token("admin")),
    )
    assert r.status_code == 200, r.text


async def _process_ready(w: World, assessment_id: UUID | None = None) -> None:
    """Create + activate the scheme once, then run a processing job."""
    if w.scheme_id is None:
        r = await w.client.post(
            "/api/v1/grading-schemes",
            json={"name": "WAEC standard", "definition": SCHEME},
            headers=w.auth(w.token("admin")),
        )
        assert r.status_code == 201, r.text
        w.scheme_id = UUID(r.json()["id"])
        r = await w.client.post(
            f"/api/v1/grading-schemes/{w.scheme_id}/activate", headers=w.auth(w.token("admin"))
        )
        assert r.status_code == 200, r.text
    r = await w.client.post(
        f"/api/v1/assessments/{assessment_id or w.assessment_id}/process",
        json={"scheme_id": str(w.scheme_id)},
        headers=w.auth(w.token("admin")),
    )
    assert r.status_code == 202, r.text
    from app.grading.jobs import process_results

    await process_results({}, job_id=r.json()["job_id"])


async def _post_transition(
    w: World,
    action: str,
    token: str,
    *,
    reason: str | None = None,
    assessment_id: UUID | None = None,
    expect: int = 200,
) -> dict:
    r = await w.client.post(
        f"/api/v1/assessments/{assessment_id or w.assessment_id}/{action}",
        json={"reason": reason} if reason else {},
        headers=w.auth(token),
    )
    assert r.status_code == expect, f"{action}: {r.status_code} {r.text}"
    return r.json()


async def _enable_mfa(w: World, who: str) -> str:
    secret = pyotp.random_base32()
    async with w.maker() as s:
        await s.execute(
            text("UPDATE users SET mfa_enabled = true, mfa_secret = :sec WHERE id = :u"),
            {"sec": secret, "u": w.uid(who)},
        )
        await s.commit()
    return secret


async def _get_mfa_secret(w: World, who: str) -> str:
    secret = await _scalar(w, "SELECT mfa_secret FROM users WHERE id = :u", {"u": w.uid(who)})
    assert secret, f"{who} has no MFA secret seeded"
    return str(secret)


async def _reauthed(
    w: World, who: str, *, password: str = PASSWORD, totp: str | None = None
) -> str:
    body: dict = {"password": password}
    if totp:
        body["totp_code"] = totp
    r = await w.client.post("/api/v1/auth/reauth", json=body, headers=w.auth(w.token(who)))
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _drive_to(w: World, target: str, *, assessment_id: UUID | None = None) -> dict[str, UUID]:
    """Walk the §10 machine from draft to the requested state; return the
    documents jobs the walk enqueued (publish only)."""
    aid = assessment_id or w.assessment_id
    await _enter_scores(w, aid)
    await _post_transition(w, "submit", w.token("admin"), assessment_id=aid)
    if target == "submitted":
        return {}
    await _post_transition(w, "start-review", w.token("registrar"), assessment_id=aid)
    if target == "under_review":
        return {}
    await _process_ready(w, aid)
    await _post_transition(w, "approve", w.token("registrar"), assessment_id=aid)
    if target == "approved":
        return {}
    token = await _reauthed(w, "admin")
    await _post_transition(w, "lock", token, assessment_id=aid)
    if target == "locked":
        return {}
    secret = await _enable_mfa(w, "admin")
    token = await _reauthed(w, "admin", totp=pyotp.TOTP(secret).now())
    await _post_transition(w, "publish", token, assessment_id=aid)
    job_id = await _scalar(
        w,
        "SELECT id FROM jobs WHERE school_id = :s AND type = 'documents.report_cards' "
        "ORDER BY created_at DESC, id DESC LIMIT 1",
        {"s": w.school_id},
    )
    return {"report_cards": UUID(str(job_id))}


async def _scalar(w: World, sql: str, params: dict):
    async with w.maker() as s:
        return await s.scalar(text(sql), params)


async def _rows(w: World, sql: str, params: dict) -> list:
    async with w.maker() as s:
        return (await s.execute(text(sql), params)).fetchall()


async def _state(w: World, assessment_id: UUID | None = None) -> str:
    return str(
        await _scalar(
            w,
            "SELECT workflow_state FROM assessments WHERE id = :a",
            {"a": assessment_id or w.assessment_id},
        )
    )


async def _new_doc_job(
    w: World, assessment_id: UUID, *, correction: bool = False, reason: str | None = None
) -> UUID:
    """A manually queued report-cards job (for re-running the worker)."""
    job_id = uuid4()
    async with w.maker() as s:
        await s.execute(
            text(
                "INSERT INTO jobs (id, school_id, type, status, params, created_by) "
                "VALUES (:id, :s, 'documents.report_cards', 'queued', :p, NULL)"
            ),
            {
                "id": job_id,
                "s": w.school_id,
                "p": json.dumps(
                    {
                        "assessment_id": str(assessment_id),
                        "correction": correction,
                        "correction_reason": reason,
                    }
                ),
            },
        )
        await s.commit()
    return job_id


async def _run_doc_worker(monkeypatch, w: World, job_id: UUID, kind: str = "report_cards") -> dict:
    """The worker's exact entry point with seams patched; asserts success."""
    from app.documents import jobs as doc_jobs

    storage = FakeStorage()
    monkeypatch.setattr(doc_jobs, "_renderer", lambda html: html.encode("utf-8"))
    monkeypatch.setattr(doc_jobs, "_storage_factory", lambda: storage)
    entry = doc_jobs.report_cards if kind == "report_cards" else doc_jobs.transcripts
    await entry({}, job_id=str(job_id))
    r = await w.client.get(f"/api/v1/jobs/{job_id}", headers=w.auth(w.token("registrar")))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "succeeded", body
    return body.get("result") or {}


# ---- the happy path --------------------------------------------------------------


class TestLifecycle:
    async def test_full_walk_draft_to_published(self, world) -> None:
        w = world
        await _drive_to(w, "published")

        assert await _state(w) == "published"

        # Eight approval records: submit, start-review, return, resubmit is NOT
        # part of _drive_to — _drive_to does 7 (no return cycle); assert 7.
        records = await _rows(
            w,
            "SELECT from_state, to_state, actor_id, reason FROM approval_records "
            "WHERE assessment_id = :a ORDER BY at, id",
            {"a": w.assessment_id},
        )
        assert [(r[0], r[1]) for r in records] == [
            ("draft", "submitted"),
            ("submitted", "under_review"),
            ("under_review", "approved"),
            ("approved", "locked"),
            ("locked", "published"),
        ]
        assert records[4][2] == w.uid("admin")  # publish actor

        # Every action audited.
        actions = {
            r[0]
            for r in await _rows(
                w, "SELECT action FROM audit_events WHERE school_id = :s", {"s": w.school_id}
            )
        }
        assert {
            "workflow.submit",
            "workflow.start_review",
            "workflow.approve",
            "workflow.lock",
            "workflow.publish",
            "documents.generation_requested",
        } <= actions

        # Outbox events in the same transactions.
        topics = {
            r[0]
            for r in await _rows(
                w, "SELECT topic FROM outbox_events WHERE school_id = :s", {"s": w.school_id}
            )
        }
        assert TOPIC_ASSESSMENT_STATE_CHANGED in topics
        assert TOPIC_RESULTS_PUBLISHED in topics

    async def test_return_and_resubmit_cycle(self, world) -> None:
        w = world
        await _enter_scores(w)
        await _post_transition(w, "submit", w.token("admin"))
        await _post_transition(w, "start-review", w.token("registrar"))
        body = await _post_transition(
            w, "return", w.token("registrar"), reason="CA2 for bayo looks transposed"
        )
        assert body["workflow_state"] == "returned"
        # Editing is allowed again in returned.
        await _enter_scores(w)
        await _post_transition(w, "submit", w.token("admin"))  # resubmit → fresh review
        assert await _state(w) == "submitted"

        records = await _rows(
            w,
            "SELECT from_state, to_state, reason FROM approval_records "
            "WHERE assessment_id = :a ORDER BY at, id",
            {"a": w.assessment_id},
        )
        assert [(r[0], r[1]) for r in records] == [
            ("draft", "submitted"),
            ("submitted", "under_review"),
            ("under_review", "returned"),
            ("returned", "submitted"),
        ]
        assert records[2][2] == "CA2 for bayo looks transposed"

    async def test_return_requires_reason(self, world) -> None:
        w = world
        await _drive_to(w, "under_review")
        await _post_transition(w, "return", w.token("registrar"), expect=422)

    async def test_correct_requires_reason_and_skips_reauth(self, world) -> None:
        """Spec §10: correct needs a reason but — unlike lock/publish — no
        step-up; a plain (un-reauthed) token is enough."""
        w = world
        await _drive_to(w, "published")
        body = await _post_transition(
            w, "correct", w.token("registrar"), reason="Ada's Exam entered wrong"
        )
        assert body["from_state"] == "published"
        assert body["to_state"] == "published"
        assert await _state(w) == "published"


# ---- illegal transitions ----------------------------------------------------------


class TestIllegalTransitions:
    async def test_draft_rejects_everything_but_submit(self, world) -> None:
        w = world
        for action in ("start-review", "return", "approve", "lock", "publish", "correct"):
            r = await w.client.post(
                f"/api/v1/assessments/{w.assessment_id}/{action}",
                json={},
                headers=w.auth(w.token("admin")),
            )
            assert r.status_code == 409, f"{action}: {r.status_code} {r.text}"
            assert r.json()["code"] == "INVALID_STATE_TRANSITION"

    async def test_submitted_rejects_submit_approve_lock_publish_correct(self, world) -> None:
        w = world
        await _drive_to(w, "submitted")
        for action in ("submit", "approve", "lock", "publish", "correct"):
            r = await w.client.post(
                f"/api/v1/assessments/{w.assessment_id}/{action}",
                json={},
                headers=w.auth(w.token("admin")),
            )
            assert r.status_code == 409, f"{action}: {r.status_code}"

    async def test_approved_rejects_submit_and_publish(self, world) -> None:
        w = world
        await _drive_to(w, "approved")
        for action in ("submit", "start-review", "publish"):
            assert (
                await w.client.post(
                    f"/api/v1/assessments/{w.assessment_id}/{action}",
                    json={},
                    headers=w.auth(w.token("admin")),
                )
            ).status_code == 409

    async def test_locked_rejects_lock_approve_correct(self, world) -> None:
        w = world
        await _drive_to(w, "locked")
        # lock/publish carry a re-auth dependency that fires before the state
        # check, so the lock attempt needs a step-up token to reach the 409.
        reauthed = await _reauthed(w, "admin")
        r = await w.client.post(
            f"/api/v1/assessments/{w.assessment_id}/lock", json={}, headers=w.auth(reauthed)
        )
        assert r.status_code == 409, r.text
        for action in ("approve", "correct"):
            assert (
                await w.client.post(
                    f"/api/v1/assessments/{w.assessment_id}/{action}",
                    json={},
                    headers=w.auth(w.token("admin")),
                )
            ).status_code == 409

    async def test_published_rejects_publish_and_lock(self, world) -> None:
        w = world
        await _drive_to(w, "published")
        # Both attempts need MFA-reauthed tokens to get past the route's
        # step-up dependency and reach the state check.
        secret = await _get_mfa_secret(w, "admin")
        token = await _reauthed(w, "admin", totp=pyotp.TOTP(secret).now())
        for action in ("lock", "publish"):
            r = await w.client.post(
                f"/api/v1/assessments/{w.assessment_id}/{action}", json={}, headers=w.auth(token)
            )
            assert r.status_code == 409, f"{action}: {r.status_code} {r.text}"

    async def test_unknown_assessment_is_404(self, world) -> None:
        r = await world.client.post(
            f"/api/v1/assessments/{uuid4()}/submit",
            json={},
            headers=world.auth(world.token("admin")),
        )
        assert r.status_code == 404


# ---- the guards -------------------------------------------------------------------


class TestGuards:
    async def test_submit_blocked_until_required_components_resolved(self, world) -> None:
        w = world
        await _enter_scores(w, only=("ada", "bayo"))  # chidi's cells stay missing
        r = await w.client.post(
            f"/api/v1/assessments/{w.assessment_id}/submit",
            json={},
            headers=w.auth(w.token("admin")),
        )
        assert r.status_code == 422, r.text
        assert "unresolved" in r.json()["detail"].lower()
        await _enter_scores(w)  # finish chidi
        await _post_transition(w, "submit", w.token("admin"))
        assert await _state(w) == "submitted"

    async def test_scores_frozen_after_submit_editable_after_return(self, world) -> None:
        w = world
        await _enter_scores(w)
        await _post_transition(w, "submit", w.token("admin"))
        r = await w.client.put(
            f"/api/v1/assessments/{w.assessment_id}/scores",
            json={"rows": [_cell(w.se_ids["ada"], "CA1", "entered", "9.00")]},
            headers=w.auth(w.token("admin")),
        )
        assert r.status_code == 409, r.text  # SUBMITTED is not editable
        await _post_transition(w, "start-review", w.token("registrar"))
        await _post_transition(w, "return", w.token("registrar"), reason="fix CA1")
        r = await w.client.put(
            f"/api/v1/assessments/{w.assessment_id}/scores",
            json={"rows": [_cell(w.se_ids["ada"], "CA1", "entered", "9.00")]},
            headers=w.auth(w.token("admin")),
        )
        assert r.status_code == 200, r.text  # RETURNED is editable again

    async def test_approve_requires_a_current_successful_run(self, world) -> None:
        w = world
        await _enter_scores(w)
        await _post_transition(w, "submit", w.token("admin"))
        await _post_transition(w, "start-review", w.token("registrar"))
        # No processing run at all yet.
        r = await w.client.post(
            f"/api/v1/assessments/{w.assessment_id}/approve",
            json={},
            headers=w.auth(w.token("registrar")),
        )
        assert r.status_code == 409, r.text
        assert r.json()["code"] == "INVALID_STATE_TRANSITION"
        await _process_ready(w)
        await _post_transition(w, "approve", w.token("registrar"))
        assert await _state(w) == "approved"

    async def test_reviewer_cannot_be_the_submitter(self, world) -> None:
        w = world
        await _drive_to(w, "submitted")
        # The submitter cannot start the review of their own submission (hard
        # rule — not the configurable SoD); the registrar can.
        await _post_transition(w, "start-review", w.token("admin"), expect=403)
        await _post_transition(w, "start-review", w.token("registrar"))
        assert await _state(w) == "under_review"

    async def test_submitter_cannot_approve_by_default(self, world) -> None:
        w = world
        await _enter_scores(w)
        await _post_transition(w, "submit", w.token("admin"))
        await _post_transition(w, "start-review", w.token("registrar"))
        await _process_ready(w)
        # Admin submitted, so admin may not approve (SoD on by default)...
        r = await w.client.post(
            f"/api/v1/assessments/{w.assessment_id}/approve",
            json={},
            headers=w.auth(w.token("admin")),
        )
        assert r.status_code == 403, r.text
        # ...but the registrar (not the submitter) can.
        await _post_transition(w, "approve", w.token("registrar"))

    async def test_separation_of_duties_can_be_disabled_per_school(self, world) -> None:
        w = world
        async with w.maker() as s:
            await s.execute(
                text(
                    "UPDATE schools SET config = '{\"separation_of_duties\": false}'::jsonb "
                    "WHERE id = :s"
                ),
                {"s": w.school_id},
            )
            await s.commit()
        await _enter_scores(w)
        await _post_transition(w, "submit", w.token("admin"))
        await _post_transition(w, "start-review", w.token("registrar"))
        await _process_ready(w)
        await _post_transition(w, "approve", w.token("admin"))  # submitter approves: allowed now
        assert await _state(w) == "approved"


# ---- step-up auth (lock, publish) --------------------------------------------------


class TestStepUp:
    async def test_lock_requires_reauth(self, world) -> None:
        w = world
        await _drive_to(w, "approved")
        # The plain login token (no reauth_at claim) is refused outright.
        r = await w.client.post(
            f"/api/v1/assessments/{w.assessment_id}/lock", json={}, headers=w.auth(w.token("admin"))
        )
        assert r.status_code == 401, r.text
        assert r.json()["code"] == "REAUTH_REQUIRED"

    async def test_reauth_verifies_password(self, world) -> None:
        w = world
        r = await w.client.post(
            "/api/v1/auth/reauth",
            json={"password": "wrong-password"},
            headers=w.auth(w.token("admin")),
        )
        assert r.status_code == 401
        assert r.json()["code"] == "INVALID_CREDENTIALS"
        # The right password mints a same-session token carrying reauth_at.
        token = await _reauthed(w, "admin")
        await _post_transition(w, "lock", token)  # — which satisfies the lock gate

    async def test_publish_demands_mfa_on_the_reauth(self, world) -> None:
        w = world
        await _drive_to(w, "locked")
        # Admin has no MFA enrolled: reauth succeeds but the claim says
        # reauth_mfa was never verified, so publish stays closed.
        token = await _reauthed(w, "admin")
        r = await w.client.post(
            f"/api/v1/assessments/{w.assessment_id}/publish", json={}, headers=w.auth(token)
        )
        assert r.status_code == 401, r.text
        assert r.json()["code"] == "MFA_REQUIRED"

        # Enroll MFA: reauth WITHOUT a code is refused, a wrong code is
        # refused, a correct code opens publish.
        secret = await _enable_mfa(w, "admin")
        r = await w.client.post(
            "/api/v1/auth/reauth", json={"password": PASSWORD}, headers=w.auth(w.token("admin"))
        )
        assert r.status_code == 401
        assert r.json()["code"] == "MFA_REQUIRED"
        r = await w.client.post(
            "/api/v1/auth/reauth",
            json={"password": PASSWORD, "totp_code": "000000"},
            headers=w.auth(w.token("admin")),
        )
        assert r.status_code == 401
        token = await _reauthed(w, "admin", totp=pyotp.TOTP(secret).now())
        await _post_transition(w, "publish", token)
        assert await _state(w) == "published"


# ---- documents: immutability, corrections, transcripts ------------------------------


class TestDocuments:
    async def test_report_cards_only_from_published(self, world) -> None:
        w = world
        r = await w.client.post(
            "/api/v1/documents/report-cards",
            json={"assessment_id": str(w.assessment_id)},
            headers=w.auth(w.token("registrar")),
        )
        assert r.status_code == 409, r.text  # draft → not printable

    async def test_generation_writes_immutable_v1_rows_and_is_idempotent(
        self, world, monkeypatch
    ) -> None:
        w = world
        jobs = await _drive_to(w, "published")
        result = await _run_doc_worker(monkeypatch, w, jobs["report_cards"])
        assert result["generated"] == 3 and result["skipped"] == 0

        rows = await _rows(
            w,
            "SELECT enrolment_id, doc_version, supersedes_id, correction_reason, storage_key "
            "FROM published_documents WHERE school_id = :s AND kind = 'report_card' "
            "ORDER BY enrolment_id, doc_version",
            {"s": w.school_id},
        )
        assert len(rows) == 3
        assert all(r[1] == 1 and r[2] is None and r[3] is None for r in rows)
        assert all("/v1.pdf" in r[4] for r in rows)

        # Re-generating identical content writes NOTHING (checksum match).
        again = await _run_doc_worker(monkeypatch, w, await _new_doc_job(w, w.assessment_id))
        assert again["generated"] == 0 and again["skipped"] == 3
        count = await _scalar(
            w, "SELECT count(*) FROM published_documents WHERE school_id = :s", {"s": w.school_id}
        )
        assert count == 3

    async def test_correction_creates_superseding_version(self, world, monkeypatch) -> None:
        w = world
        jobs = await _drive_to(w, "published")
        await _run_doc_worker(monkeypatch, w, jobs["report_cards"])
        v1 = await _rows(
            w,
            "SELECT id, enrolment_id, checksum FROM published_documents "
            "WHERE school_id = :s AND doc_version = 1 ORDER BY enrolment_id",
            {"s": w.school_id},
        )

        # Correct — plain token, no step-up (spec §10 marks no re-auth here).
        await _post_transition(
            w, "correct", w.token("registrar"), reason="Ada's exam was 58, not 48"
        )
        correction_job = await _scalar(
            w,
            "SELECT id FROM jobs WHERE school_id = :s AND type = 'documents.report_cards' "
            "ORDER BY created_at DESC, id DESC LIMIT 1",
            {"s": w.school_id},
        )
        result = await _run_doc_worker(monkeypatch, w, UUID(str(correction_job)))
        assert result["generated"] == 3

        v2 = await _rows(
            w,
            "SELECT doc_version, supersedes_id, correction_reason, checksum, enrolment_id "
            "FROM published_documents WHERE school_id = :s AND doc_version = 2 "
            "ORDER BY enrolment_id",
            {"s": w.school_id},
        )
        assert len(v2) == 3
        by_se = {r[1]: r for r in v1}
        for _version, supersedes, reason, _checksum, seid in v2:
            assert supersedes == by_se[seid][0]  # supersedes_id → that student's v1 row
            assert reason == "Ada's exam was 58, not 48"
        # v1 rows untouched — INSERT-only, never updated.
        v1_after = await _rows(
            w,
            "SELECT id, checksum FROM published_documents "
            "WHERE school_id = :s AND doc_version = 1 ORDER BY enrolment_id",
            {"s": w.school_id},
        )
        assert v1_after == v1
        # Identical content between v1 and v2 — the correction forced a new
        # version even though the checksum matched.
        assert {r[3] for r in v2} == {r[2] for r in v1}

    async def test_download_returns_signed_url_and_audits(self, world, monkeypatch) -> None:
        w = world
        jobs = await _drive_to(w, "published")
        await _run_doc_worker(monkeypatch, w, jobs["report_cards"])
        doc_id = await _scalar(
            w,
            "SELECT id FROM published_documents WHERE school_id = :s LIMIT 1",
            {"s": w.school_id},
        )
        fake = FakeStorage()
        monkeypatch.setattr("app.documents.storage.get_storage", lambda: fake)
        r = await w.client.get(
            f"/api/v1/documents/{doc_id}/download", headers=w.auth(w.token("registrar"))
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["url"].startswith("https://objects.test/")
        assert body["expires_in"] == 300
        audited = await _rows(
            w,
            "SELECT action FROM audit_events "
            "WHERE school_id = :s AND action = 'documents.downloaded'",
            {"s": w.school_id},
        )
        assert len(audited) == 1

    async def test_transcript_download_needs_transcripts_permission(
        self, world, monkeypatch
    ) -> None:
        """reports.view alone cannot download a transcript — the require()
        dependency itself re-checks the kind-specific permission."""
        w = world
        seid = w.se_ids["ada"]
        r = await w.client.post(
            "/api/v1/documents/transcripts",
            json={"enrolment_id": str(seid)},
            headers=w.auth(w.token("registrar")),
        )
        assert r.status_code == 409, r.text  # nothing published yet

        jobs = await _drive_to(w, "published")
        await _run_doc_worker(monkeypatch, w, jobs["report_cards"])
        r = await w.client.post(
            "/api/v1/documents/transcripts",
            json={"enrolment_id": str(seid)},
            headers=w.auth(w.token("registrar")),
        )
        assert r.status_code == 202, r.text
        transcript_job = UUID(r.json()["job_id"])
        result = await _run_doc_worker(monkeypatch, w, transcript_job, kind="transcripts")
        assert result["generated"] == 1

        # viewer holds reports.view (school scope) but NOT transcripts.generate.
        doc_id = await _scalar(
            w,
            "SELECT id FROM published_documents WHERE school_id = :s AND kind = 'transcript'",
            {"s": w.school_id},
        )
        fake = FakeStorage()
        monkeypatch.setattr("app.documents.storage.get_storage", lambda: fake)
        r = await w.client.get(
            f"/api/v1/documents/{doc_id}/download", headers=w.auth(w.token("viewer"))
        )
        assert r.status_code == 403, r.text
        r = await w.client.get(
            f"/api/v1/documents/{doc_id}/download", headers=w.auth(w.token("registrar"))
        )
        assert r.status_code == 200, r.text

    async def test_transcript_collects_every_published_term_in_order(
        self, world, monkeypatch
    ) -> None:
        """Two published assessments (First + Second Term) of the SAME
        class+subject: one transcript, term-ordered, idempotent."""
        w = world
        await _drive_to(w, "published")
        await _run_doc_worker(monkeypatch, w, await _latest_doc_job(w))

        # Second term, same class_subject (the subject_enrolments are shared).
        term2 = await _add_term(w, "Second Term", 2)
        aid2 = await _add_assessment(w, term2)
        await _enter_scores(w, aid2)
        await _process_ready(w, aid2)
        await _post_transition(w, "submit", w.token("admin"), assessment_id=aid2)
        await _post_transition(w, "start-review", w.token("registrar"), assessment_id=aid2)
        await _post_transition(w, "approve", w.token("registrar"), assessment_id=aid2)
        token = await _reauthed(w, "admin")
        await _post_transition(w, "lock", token, assessment_id=aid2)
        secret = await _enable_mfa(w, "admin")
        token = await _reauthed(w, "admin", totp=pyotp.TOTP(secret).now())
        await _post_transition(w, "publish", token, assessment_id=aid2)

        seid = w.se_ids["ada"]
        r = await w.client.post(
            "/api/v1/documents/transcripts",
            json={"enrolment_id": str(seid)},
            headers=w.auth(w.token("registrar")),
        )
        assert r.status_code == 202, r.text

        # Patch the seams here (not via _run_doc_worker) so the rendered
        # content can be inspected for the term ordering.
        from app.documents import jobs as doc_jobs

        fake = FakeStorage()
        monkeypatch.setattr(doc_jobs, "_renderer", lambda html: html.encode("utf-8"))
        monkeypatch.setattr(doc_jobs, "_storage_factory", lambda: fake)
        await doc_jobs.transcripts({}, job_id=r.json()["job_id"])
        assert len(fake.objects) == 1
        html = next(iter(fake.objects.values())).decode("utf-8")
        first, second = html.index("First Term"), html.index("Second Term")
        assert first < second, "transcript rows must be term-ordered"

        # Re-run: identical content → skipped (no v2).
        again = await _run_doc_worker(
            monkeypatch, w, await _new_transcript_job(w, seid), kind="transcripts"
        )
        assert again["generated"] == 0
        count = await _scalar(
            w,
            "SELECT count(*) FROM published_documents WHERE school_id = :s AND kind = 'transcript'",
            {"s": w.school_id},
        )
        assert count == 1


# ---- small seed helpers used only by the document tests -----------------------------


async def _add_term(w: World, name: str, ordinal: int) -> UUID:
    term = uuid4()
    async with w.maker() as s:
        await s.execute(
            text(
                "INSERT INTO terms (id, school_id, session_id, name, ordinal) "
                "VALUES (:id, :s, :a, :n, :o)"
            ),
            {"id": term, "s": w.school_id, "a": w.session_id, "n": name, "o": ordinal},
        )
        await s.commit()
    return term


async def _latest_doc_job(w: World) -> UUID:
    job_id = await _scalar(
        w,
        "SELECT id FROM jobs WHERE school_id = :s AND type = 'documents.report_cards' "
        "ORDER BY created_at DESC, id DESC LIMIT 1",
        {"s": w.school_id},
    )
    return UUID(str(job_id))


async def _new_transcript_job(w: World, seid: UUID) -> UUID:
    job_id = uuid4()
    async with w.maker() as s:
        await s.execute(
            text(
                "INSERT INTO jobs (id, school_id, type, status, params, created_by) "
                "VALUES (:id, :s, 'documents.transcripts', 'queued', :p, NULL)"
            ),
            {"id": job_id, "s": w.school_id, "p": json.dumps({"enrolment_id": str(seid)})},
        )
        await s.commit()
    return job_id


# ---- configurable stage definitions + assigned scope -------------------------------


class TestDefinitionsAndScope:
    async def test_definition_upsert_and_unknown_state_rejected(self, world) -> None:
        from uuid import uuid4 as new_uuid

        from app.access.service import Actor
        from app.platform.db import set_tenant_context
        from app.platform.errors import ProblemError
        from app.workflow.schemas import StageDef, WorkflowDefinitionCreate
        from app.workflow.service import WorkflowService

        w = world
        actor = Actor(
            user_id=w.uid("admin"), school_id=w.school_id, token_version=1, session_id=new_uuid()
        )
        data = WorkflowDefinitionCreate(
            name="Registrar-first",
            stages=[StageDef(state="submitted", requires="scores.submit")],
        )
        async with w.maker() as s:
            await set_tenant_context(s, str(w.school_id))
            service = WorkflowService(s)
            created = await service.save_definition(w.school_id, data, actor)
            await s.commit()
            replaced = await service.save_definition(
                w.school_id,
                WorkflowDefinitionCreate(
                    name="Registrar-first",
                    stages=[
                        StageDef(state="submitted", requires="scores.submit"),
                        StageDef(state="under_review", requires="scores.review"),
                    ],
                ),
                actor,
            )
            await s.commit()
        assert replaced.id == created.id  # upsert: same row, stages replaced
        stages = await _scalar(
            w, "SELECT stages FROM workflow_definitions WHERE id = :d", {"d": created.id}
        )
        assert len(stages) == 2 and stages[1]["state"] == "under_review"

        with pytest.raises(ProblemError) as excinfo:
            async with w.maker() as s:
                await set_tenant_context(s, str(w.school_id))
                await WorkflowService(s).save_definition(
                    w.school_id,
                    WorkflowDefinitionCreate(name="Bad", stages=[StageDef(state="sideways")]),
                    actor,
                )
        assert excinfo.value.status == 422

    async def test_teacher_submits_within_assignment_but_cannot_approve(self, world) -> None:
        w = world
        await _enter_scores(w)
        # Teacher holds scores.submit in the ASSIGNED scope and teaches this
        # class_subject — the transition honours the scope.
        await _post_transition(w, "submit", w.token("teacher"))
        assert await _state(w) == "submitted"
        await _process_ready(w)
        await _post_transition(w, "start-review", w.token("registrar"))
        # results.approve is school-scope only: require() denies the
        # assigned-scope teacher outright (no resource context).
        r = await w.client.post(
            f"/api/v1/assessments/{w.assessment_id}/approve",
            json={},
            headers=w.auth(w.token("teacher")),
        )
        assert r.status_code == 403, r.text
