"""Workflow module — SQLAlchemy models (Phase 5).

Mirrors migrations/versions/0006_workflow_documents.py. The assessment's own
state lives on assessments.workflow_state (assessment/models.py); these tables
hold the supporting records:

  - WorkflowDefinition: a school's configurable stage order (JSONB). Only the
    ORDER and PERMISSION REQUIREMENTS of stages are configurable — the legal
    transition graph and the mandatory invariants (spec §10) are code.
  - ApprovalRecord: one row per successful transition. Immutable.
  - PublishedDocument: immutable published artifact; a correction INSERTs a
    new row (doc_version + 1, supersedes_id → prior). Never UPDATEd.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.assessment.models import WORKFLOW_STATES
from app.people.models import uuid7
from app.platform.models import Base

DOCUMENT_KINDS = ("report_card", "transcript")


class WorkflowDefinition(Base):
    """A named, per-school stage configuration (spec §10).

    `stages` shape:
    [{"state": "submitted", "requires": "scores.submit"}, ...] — the ordered
    path from draft to published. Unknown states are rejected at write time
    by the service; the mandatory invariants are not expressible here.
    """

    __tablename__ = "workflow_definitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    school_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    stages: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class ApprovalRecord(Base):
    """One row per successful workflow transition — the durable approval
    ledger the audit log cross-references (spec §10)."""

    __tablename__ = "approval_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    school_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessments.id"), nullable=False
    )
    from_state: Mapped[str] = mapped_column(
        SAEnum(*WORKFLOW_STATES, name="workflowstate", native_enum=True),
        nullable=False,
    )
    to_state: Mapped[str] = mapped_column(
        SAEnum(*WORKFLOW_STATES, name="workflowstate", native_enum=True),
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PublishedDocument(Base):
    """An immutable published artifact (report card or transcript).

    Corrections never modify an existing row: they INSERT a new one with
    doc_version = prior + 1 and supersedes_id = prior.id (spec §10). The
    storage_key points into object storage; checksum is the SHA-256 hex of
    the stored bytes.
    """

    __tablename__ = "published_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    school_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False
    )
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessments.id"), nullable=True
    )
    enrolment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subject_enrolments.id"), nullable=True
    )
    kind: Mapped[str] = mapped_column(
        SAEnum(*DOCUMENT_KINDS, name="documentkind", native_enum=True),
        nullable=False,
    )
    doc_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("published_documents.id"), nullable=True
    )
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    correction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
