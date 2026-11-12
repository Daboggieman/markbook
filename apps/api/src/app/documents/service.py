"""Documents service — report cards and transcripts (Phase 5).

API side: request validation + a durable jobs row (202 pattern — rendering
is never inline, ADR 005). Worker side: `generate_report_cards` /
`generate_transcript` render from the CURRENT processed results, store the
PDF, and write the immutable published_documents row.

Immutability and correction versioning (spec §10 — the exit criterion):
published_documents rows are INSERT-only. A regeneration of the same content
is idempotent (checksum match → no new row); a CORRECTION always creates the
next version with `supersedes_id` → previous row and `correction_reason`
stamped from the transition. Nothing ever UPDATEs or DELETEs a row.

`enrolment_id` throughout is a subject_enrolments.id — the same FK the
published_documents table carries (one document per student per subject).

Cross-module edges (all legal): grading.service (results), assessment +
academic + people models (models-only reads, the Phase 2 precedent),
platform.models (Job/School).
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.academic.models import (
    AcademicSession,
    ClassSubject,
    Enrolment,
    Student,
    Subject,
    SubjectEnrolment,
    Term,
)
from app.access.service import Actor
from app.assessment.models import Assessment
from app.audit.service import AuditService
from app.documents.render import render_result_document_html
from app.documents.storage import checksum_of
from app.grading.models import ProcessedResult, ResultProcessingRun
from app.grading.service import GradingService
from app.platform.errors import NOT_FOUND, VALIDATION_ERROR, ProblemError
from app.platform.logging import get_logger
from app.platform.models import Job, School
from app.workflow.models import PublishedDocument

log = get_logger("documents")

REPORT_CARDS_JOB = "documents.report_cards"
TRANSCRIPTS_JOB = "documents.transcripts"


class DocumentService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ---- API side: job requests -------------------------------------------------

    async def create_report_card_job(
        self, school_id: UUID, assessment_id: UUID, actor: Actor
    ) -> Job:
        """Queue report-card generation for a PUBLISHED assessment (202).
        Only published results may be printed — a report card is a published
        artifact, not a draft preview."""
        assessment = await self._s.scalar(
            select(Assessment).where(
                Assessment.school_id == school_id, Assessment.id == assessment_id
            )
        )
        if assessment is None:
            raise ProblemError(NOT_FOUND, "Assessment not found", status=404)
        if assessment.workflow_state != "published":
            raise ProblemError(
                VALIDATION_ERROR,
                f"Report cards can only be generated for published assessments "
                f"(this one is {assessment.workflow_state})",
            )
        job = Job(
            school_id=school_id,
            type=REPORT_CARDS_JOB,
            status="queued",
            params={"assessment_id": str(assessment_id), "correction_reason": None},
            created_by=actor.user_id,
        )
        self._s.add(job)
        await self._s.flush()
        await AuditService(self._s, actor).write(
            "documents.report_cards_requested",
            entity_type="job",
            entity_id=job.id,
            after={"assessment_id": str(assessment_id)},
        )
        return job

    async def create_transcript_job(self, school_id: UUID, enrolment_id: UUID, actor: Actor) -> Job:
        """Queue a transcript for one subject enrolment (202): every PUBLISHED
        result the student has for that class+subject, term-ordered, one PDF."""
        if await self._get_subject_enrolment(school_id, enrolment_id) is None:
            raise ProblemError(NOT_FOUND, "Subject enrolment not found", status=404)
        published = await self._published_results_for_enrolment(school_id, enrolment_id)
        if not published:
            raise ProblemError(
                VALIDATION_ERROR, "No published results exist for this subject enrolment"
            )
        job = Job(
            school_id=school_id,
            type=TRANSCRIPTS_JOB,
            status="queued",
            params={"enrolment_id": str(enrolment_id)},
            created_by=actor.user_id,
        )
        self._s.add(job)
        await self._s.flush()
        await AuditService(self._s, actor).write(
            "documents.transcript_requested",
            entity_type="job",
            entity_id=job.id,
            after={"enrolment_id": str(enrolment_id)},
        )
        return job

    # ---- worker side: generation -------------------------------------------------

    async def generate_report_cards(
        self,
        school_id: UUID,
        job: Job,
        actor: Actor,
        *,
        storage: Any,
        renderer: Callable[[str], bytes],
    ) -> dict[str, Any]:
        """Render one PDF per enrolled student from the CURRENT results and
        write the immutable published_documents rows. Idempotent on identical
        content (checksum match → no new version); a correction (job params
        carry a reason) always creates the next version."""
        params = job.params or {}
        assessment_id = UUID(str(params["assessment_id"]))
        correction_reason: str | None = params.get("correction_reason")

        assessment = await self._s.scalar(
            select(Assessment).where(
                Assessment.school_id == school_id, Assessment.id == assessment_id
            )
        )
        if assessment is None:
            raise ProblemError(NOT_FOUND, "Assessment not found", status=404)
        run, rows = await GradingService(self._s).get_results(school_id, assessment_id)
        school_name, subject_name, term_name = await self._assessment_labels(assessment)

        generated: list[str] = []
        skipped = 0
        for result_row, student_name in rows:
            html = render_result_document_html(
                kind="report_card",
                school_name=school_name,
                student_name=student_name,
                subject_name=subject_name,
                term_name=term_name,
                rows=[
                    {
                        "assessment_label": f"{subject_name} — {term_name}",
                        "total": result_row.total,
                        "grade": result_row.grade,
                        "position": result_row.position,
                        "flags": list(result_row.flags),
                    }
                ],
            )
            pdf = renderer(html)
            seid = result_row.subject_enrolment_id
            document = await self._version_and_store(
                school_id=school_id,
                kind="report_card",
                assessment_id=assessment_id,
                enrolment_id=seid,
                pdf=pdf,
                key_template=f"schools/{school_id}/report_card/{assessment_id}/{seid}/v{{version}}.pdf",
                storage=storage,
                published_by=actor.user_id,
                correction_reason=correction_reason,
                force_new=correction_reason is not None,
            )
            if document is None:
                skipped += 1
            else:
                generated.append(str(document.id))

        await AuditService(self._s, actor).write(
            "documents.report_cards_generated",
            entity_type="job",
            entity_id=job.id,
            after={
                "assessment_id": str(assessment_id),
                "run_id": str(run.id),
                "generated": len(generated),
                "skipped": skipped,
            },
        )
        return {
            "assessment_id": str(assessment_id),
            "generated": len(generated),
            "skipped": skipped,
            "document_ids": generated,
        }

    async def generate_transcript(
        self,
        school_id: UUID,
        job: Job,
        actor: Actor,
        *,
        storage: Any,
        renderer: Callable[[str], bytes],
    ) -> dict[str, Any]:
        """One transcript PDF for one subject enrolment: every PUBLISHED
        result for that student+subject, term-ordered."""
        params = job.params or {}
        enrolment_id = UUID(str(params["enrolment_id"]))
        published = await self._published_results_for_enrolment(school_id, enrolment_id)
        if not published:
            raise ProblemError(
                VALIDATION_ERROR, "No published results exist for this subject enrolment"
            )

        names = await self._enrolment_labels(school_id, enrolment_id)
        html = render_result_document_html(
            kind="transcript",
            school_name=names["school_name"],
            student_name=names["student_name"],
            subject_name=names["subject_name"],
            term_name=names["session_name"],
            rows=published,
        )
        pdf = renderer(html)
        document = await self._version_and_store(
            school_id=school_id,
            kind="transcript",
            assessment_id=None,
            enrolment_id=enrolment_id,
            pdf=pdf,
            key_template=f"schools/{school_id}/transcript/{enrolment_id}/v{{version}}.pdf",
            storage=storage,
            published_by=actor.user_id,
            correction_reason=None,
            force_new=False,
        )
        await AuditService(self._s, actor).write(
            "documents.transcript_generated",
            entity_type="job",
            entity_id=job.id,
            after={
                "enrolment_id": str(enrolment_id),
                "document_id": str(document.id) if document is not None else None,
            },
        )
        return {
            "enrolment_id": str(enrolment_id),
            "generated": 1 if document is not None else 0,
            "skipped": 0 if document is not None else 1,
            "document_ids": [str(document.id)] if document is not None else [],
        }

    # ---- internals -----------------------------------------------------------------

    async def _get_subject_enrolment(
        self, school_id: UUID, enrolment_id: UUID
    ) -> SubjectEnrolment | None:
        return await self._s.scalar(
            select(SubjectEnrolment).where(
                SubjectEnrolment.school_id == school_id, SubjectEnrolment.id == enrolment_id
            )
        )

    async def _version_and_store(
        self,
        *,
        school_id: UUID,
        kind: str,
        assessment_id: UUID | None,
        enrolment_id: UUID,
        pdf: bytes,
        key_template: str,
        storage: Any,
        published_by: UUID | None,
        correction_reason: str | None,
        force_new: bool,
    ) -> PublishedDocument | None:
        """The immutability core. Finds the current version, decides whether
        this render is a no-op, else INSERTs the next version superseding it.

        - checksum matches the latest row and not force_new → None (skip).
        - otherwise version = latest + 1, supersedes_id = latest.id.

        `key_template` carries a `{version}` placeholder — every version is a
        distinct object, and a superseded object is never overwritten.
        """
        latest = await self._latest_document(school_id, kind, assessment_id, enrolment_id)
        checksum = checksum_of(pdf)
        if latest is not None and latest.checksum == checksum and not force_new:
            return None
        version = (latest.doc_version + 1) if latest is not None else 1
        key = key_template.format(version=version)
        stored_checksum = storage.put(key, pdf)
        document = PublishedDocument(
            school_id=school_id,
            assessment_id=assessment_id,
            enrolment_id=enrolment_id,
            kind=kind,
            doc_version=version,
            supersedes_id=latest.id if latest is not None else None,
            storage_key=key,
            checksum=stored_checksum,
            published_by=published_by,
            published_at=datetime.now(UTC),
            correction_reason=correction_reason,
        )
        self._s.add(document)
        await self._s.flush()
        return document

    async def _latest_document(
        self,
        school_id: UUID,
        kind: str,
        assessment_id: UUID | None,
        enrolment_id: UUID,
    ) -> PublishedDocument | None:
        stmt = select(PublishedDocument).where(
            PublishedDocument.school_id == school_id,
            PublishedDocument.kind == kind,
            PublishedDocument.enrolment_id == enrolment_id,
        )
        stmt = stmt.where(
            PublishedDocument.assessment_id == assessment_id
            if assessment_id is not None
            else PublishedDocument.assessment_id.is_(None)
        )
        stmt = stmt.order_by(PublishedDocument.doc_version.desc()).limit(1)
        return await self._s.scalar(stmt)

    async def _published_results_for_enrolment(
        self, school_id: UUID, enrolment_id: UUID
    ) -> list[dict[str, Any]]:
        """Every PUBLISHED result for one subject enrolment, term-ordered.

        A subject_enrolment is shared by every assessment of its class_subject
        within the enrolment's session, so: published assessments for
        (enrolment.class_id, class_subject.subject_id, session terms) → each
        one's latest succeeded run → the processed_result for THIS seid.
        """
        subject_enrolment = await self._get_subject_enrolment(school_id, enrolment_id)
        if subject_enrolment is None:
            raise ProblemError(NOT_FOUND, "Subject enrolment not found", status=404)
        enrolment = await self._s.scalar(
            select(Enrolment).where(Enrolment.id == subject_enrolment.enrolment_id)
        )
        class_subject = await self._s.scalar(
            select(ClassSubject).where(ClassSubject.id == subject_enrolment.class_subject_id)
        )
        if enrolment is None or class_subject is None:
            raise ProblemError(NOT_FOUND, "Subject enrolment not found", status=404)

        assessment_rows = (
            await self._s.execute(
                select(Assessment, Term.name, Term.ordinal)
                .join(Term, Term.id == Assessment.term_id)
                .where(
                    Assessment.school_id == school_id,
                    Assessment.class_id == enrolment.class_id,
                    Assessment.subject_id == class_subject.subject_id,
                    Assessment.workflow_state == "published",
                    Term.session_id == enrolment.session_id,
                )
                .order_by(Term.ordinal)
            )
        ).all()

        rows: list[dict[str, Any]] = []
        for assessment, term_name, _ordinal in assessment_rows:
            run_id = await self._s.scalar(
                select(ResultProcessingRun.id)
                .where(
                    ResultProcessingRun.school_id == school_id,
                    ResultProcessingRun.assessment_id == assessment.id,
                    ResultProcessingRun.status == "succeeded",
                )
                .order_by(ResultProcessingRun.created_at.desc(), ResultProcessingRun.id)
                .limit(1)
            )
            if run_id is None:
                continue
            result = await self._s.scalar(
                select(ProcessedResult).where(
                    ProcessedResult.school_id == school_id,
                    ProcessedResult.run_id == run_id,
                    ProcessedResult.subject_enrolment_id == enrolment_id,
                )
            )
            if result is None:
                continue
            rows.append(
                {
                    "assessment_label": term_name,
                    "total": result.total,
                    "grade": result.grade,
                    "position": result.position,
                    "flags": list(result.flags),
                }
            )
        return rows

    async def _assessment_labels(self, assessment: Assessment) -> tuple[str, str, str]:
        """(school_name, subject_name, term_name) for the render header."""
        school_name = await self._s.scalar(
            select(School.name).where(School.id == assessment.school_id)
        )
        subject_name = await self._s.scalar(
            select(Subject.name).where(Subject.id == assessment.subject_id)
        )
        term_name = await self._s.scalar(select(Term.name).where(Term.id == assessment.term_id))
        return school_name or "", subject_name or "", term_name or ""

    async def _enrolment_labels(self, school_id: UUID, enrolment_id: UUID) -> dict[str, str]:
        """Names for a transcript header: student, subject, session, school."""
        subject_enrolment = await self._get_subject_enrolment(school_id, enrolment_id)
        if subject_enrolment is None:
            raise ProblemError(NOT_FOUND, "Subject enrolment not found", status=404)
        enrolment = await self._s.scalar(
            select(Enrolment).where(Enrolment.id == subject_enrolment.enrolment_id)
        )
        class_subject = await self._s.scalar(
            select(ClassSubject).where(ClassSubject.id == subject_enrolment.class_subject_id)
        )
        if enrolment is None or class_subject is None:
            raise ProblemError(NOT_FOUND, "Subject enrolment not found", status=404)
        student = await self._s.scalar(select(Student).where(Student.id == enrolment.student_id))
        if student is None:
            raise ProblemError(NOT_FOUND, "Student not found", status=404)
        subject_name = await self._s.scalar(
            select(Subject.name).where(Subject.id == class_subject.subject_id)
        )
        session_name = await self._s.scalar(
            select(AcademicSession.name).where(AcademicSession.id == enrolment.session_id)
        )
        school_name = await self._s.scalar(select(School.name).where(School.id == school_id))
        return {
            "school_name": school_name or "",
            "student_name": f"{student.first_name} {student.last_name}",
            "subject_name": subject_name or "",
            "session_name": session_name or "",
        }
