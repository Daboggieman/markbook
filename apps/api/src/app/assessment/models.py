"""Assessment module — SQLAlchemy models (Phase 3).

Mirrors migrations/versions/0004_assessment_scores.py. The zero-vs-missing
invariant lives in the DB CHECK on `scores` — `entered` ⇔ value IS NOT NULL
(spec §6.4); the application layer must not try to be cleverer than that
constraint. Template definitions are JSONB and immutable once a version
leaves `draft` — editing a template creates a NEW version, and existing
assessments keep pointing at the version they were created with.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.people.models import uuid7
from app.platform.models import Base

TEMPLATE_VERSION_STATUSES = ("draft", "active", "retired")
WORKFLOW_STATES = (
    "draft",
    "submitted",
    "under_review",
    "returned",
    "approved",
    "locked",
    "published",
)
# The workflow states in which score cells may still be written (spec §6.4).
EDITABLE_STATES = ("draft", "returned")
SCORE_STATUSES = ("entered", "absent", "exempt", "missing")
SCORE_CHANGE_SOURCES = ("web", "desktop_sync", "import")


class AssessmentTemplate(Base):
    __tablename__ = "assessment_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    school_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class AssessmentTemplateVersion(Base):
    """One immutable revision of a template's component definition.

    `definition` shape (spec §6.4):
    {"components": [{"key", "label", "max_score", "weight", "required"}]}
    """

    __tablename__ = "assessment_template_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    school_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessment_templates.id"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        SAEnum(*TEMPLATE_VERSION_STATUSES, name="templateversionstatus", native_enum=True),
        nullable=False,
        default="draft",
    )
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class Assessment(Base):
    """One result set: a subject's scores for a term/class(/section)."""

    __tablename__ = "assessments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    school_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False
    )
    term_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("terms.id"), nullable=False
    )
    class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sections.id"), nullable=True
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False
    )
    template_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessment_template_versions.id"), nullable=False
    )
    workflow_state: Mapped[str] = mapped_column(
        SAEnum(*WORKFLOW_STATES, name="workflowstate", native_enum=True),
        nullable=False,
        default="draft",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Score(Base):
    """One cell of the score sheet: a component for one subject enrolment.

    `value` is a real score only when status = 'entered' — a genuine zero is
    ('entered', Decimal('0.00')), never NULL. The DB CHECK enforces the
    equivalence; tests must not suggest the constraint is in the way.
    """

    __tablename__ = "scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    school_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessments.id"), nullable=False
    )
    subject_enrolment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subject_enrolments.id"), nullable=False
    )
    component_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        SAEnum(*SCORE_STATUSES, name="scorestatus", native_enum=True),
        nullable=False,
        default="missing",
    )
    value: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    entered_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    entered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ScoreChange(Base):
    """Append-only edit ledger for scores (spec §6.4). No UPDATE, ever."""

    __tablename__ = "score_changes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    school_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False
    )
    score_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scores.id"), nullable=False
    )
    old_status: Mapped[str | None] = mapped_column(
        SAEnum(*SCORE_STATUSES, name="scorestatus", native_enum=True), nullable=True
    )
    old_value: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    new_status: Mapped[str | None] = mapped_column(
        SAEnum(*SCORE_STATUSES, name="scorestatus", native_enum=True), nullable=True
    )
    new_value: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    source: Mapped[str] = mapped_column(
        SAEnum(*SCORE_CHANGE_SOURCES, name="scorechangesource", native_enum=True),
        nullable=False,
    )
