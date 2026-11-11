"""Documents schemas — Pydantic request/response models (Phase 5)."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
