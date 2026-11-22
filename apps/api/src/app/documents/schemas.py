"""Documents schemas — Pydantic request/response models (Phase 5)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReportCardRequest(BaseModel):
    assessment_id: UUID


class TranscriptRequest(BaseModel):
    enrolment_id: UUID


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_id: UUID
    assessment_id: UUID | None
    enrolment_id: UUID | None
    kind: str
    doc_version: int
    supersedes_id: UUID | None
    checksum: str
    published_by: UUID | None
    published_at: datetime
    correction_reason: str | None


class DownloadResponse(BaseModel):
    """A signed, short-lived download URL (08-security-and-operations)."""

    document_id: UUID
    url: str
    expires_in: int


class DocumentListItem(BaseModel):
    """One published document on the reports screen (Phase 6).

    A join projection — the row itself has no student name; the list query
    resolves it through the enrolment. Not the download endpoint's schema
    (that stays DocumentResponse-shaped).
    """

    id: UUID
    kind: str
    doc_version: int
    enrolment_id: UUID | None
    student_name: str | None
    supersedes_id: UUID | None
    correction_reason: str | None
    published_at: datetime
