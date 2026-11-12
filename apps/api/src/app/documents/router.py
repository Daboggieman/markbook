"""Documents router — report cards, transcripts, downloads (Phase 5).

Permission mapping (spec §8 documents group):
  - POST /documents/report-cards  → reports.view   (a printable report card
    is a view of published results; only published assessments generate)
  - POST /documents/transcripts   → transcripts.generate
  - GET  /documents/{id}/download → by kind: report_card → reports.view,
    transcript → transcripts.generate (re-checked through require() itself)

Downloads return a signed, short-lived URL (08-security-and-operations) and
write an audit event — every download is audited, not just the publication.
"""

# ruff: noqa: B008  — Depends(require(...)) in defaults is the FastAPI idiom.

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.dependency import get_actor_db, require
from app.access.service import Actor
from app.audit.service import AuditService
from app.documents import schemas
from app.documents.service import DocumentService
from app.platform.errors import NOT_FOUND, ProblemError
from app.workflow.models import DOCUMENT_KINDS, PublishedDocument

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/report-cards", status_code=202)
async def request_report_cards(
    body: schemas.ReportCardRequest,
    actor: Actor = Depends(require("reports.view")),
    session: AsyncSession = Depends(get_actor_db),
) -> dict[str, str]:
    """Queue report-card generation for a published assessment (202 — async,
    spec §8). The job's progress is at GET /jobs/{job_id}; the rendered
    documents appear there as they are written."""
    service = DocumentService(session)
    job = await service.create_report_card_job(actor.school_id, body.assessment_id, actor)
    await session.commit()

    from app.platform.job_queue import enqueue_job

    await enqueue_job(job.id, "report_cards")
    return {"job_id": str(job.id), "status_url": f"/api/v1/jobs/{job.id}"}


@router.post("/transcripts", status_code=202)
async def request_transcript(
    body: schemas.TranscriptRequest,
    actor: Actor = Depends(require("transcripts.generate")),
    session: AsyncSession = Depends(get_actor_db),
) -> dict[str, str]:
    """Queue a transcript for one subject enrolment (202 — async)."""
    service = DocumentService(session)
    job = await service.create_transcript_job(actor.school_id, body.enrolment_id, actor)
    await session.commit()

    from app.platform.job_queue import enqueue_job

    await enqueue_job(job.id, "transcripts")
    return {"job_id": str(job.id), "status_url": f"/api/v1/jobs/{job.id}"}


@router.get("/{document_id}/download", response_model=schemas.DownloadResponse)
async def download_document(
    document_id: UUID,
    request: Request,
    actor: Actor = Depends(require("reports.view")),
    session: AsyncSession = Depends(get_actor_db),
) -> schemas.DownloadResponse:
    """A signed, short-lived download URL for a published document.

    The permission follows the document's kind: transcripts demand
    transcripts.generate even when the caller holds reports.view (the
    require() dependency itself re-checks, its own session and grants).
    Every download is audited (08-security-and-operations)."""
    document = await session.scalar(
        select(PublishedDocument).where(
            PublishedDocument.school_id == actor.school_id, PublishedDocument.id == document_id
        )
    )
    if document is None:
        raise ProblemError(NOT_FOUND, "Document not found", status=404)
    if document.kind not in DOCUMENT_KINDS:  # pragma: no cover — enum-gated
        raise ProblemError(NOT_FOUND, "Document not found", status=404)
    if document.kind == "transcript":
        await require("transcripts.generate")(request)

    from app.documents.storage import get_storage

    expires_in = 300  # signed URLs are short-lived (spec: security and ops)
    url = get_storage().presigned_get(document.storage_key, expires_in)
    await AuditService(session, actor).write(
        "documents.downloaded",
        entity_type="published_document",
        entity_id=document.id,
        after={
            "kind": document.kind,
            "doc_version": document.doc_version,
            "checksum": document.checksum,
        },
    )
    await session.commit()
    return schemas.DownloadResponse(document_id=document.id, url=url, expires_in=expires_in)
