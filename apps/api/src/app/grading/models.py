"""Grading module — SQLAlchemy models (Phase 4).

Mirrors migrations/versions/0005_grading_results.py. Data model spec §6.5.

`grading_schemes` is row-per-version (like template versions minus the parent
table — the data model defines no scheme parent): the scheme family is
(school_id, name), each row is one version with its own definition and
lifecycle, and `result_processing_runs.scheme_id` stores the exact version row
consumed with `scheme_version` denormalised beside it so every run is
self-describing without a join. Editing a scheme creates a NEW version;
existing runs are untouched (spec §9.4).

`processed_results.total`/`grade`/`position` are NULLable on purpose: a
student whose every component was excluded (flag no_scoreable_components) has
no computable total — the row is stored so the run reports them, and the
report-card layer decides what to show.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.people.models import uuid7
from app.platform.models import Base

SCHEME_STATUSES = ("draft", "active", "retired")
RUN_STATUSES = ("queued", "running", "succeeded", "failed")


class GradingScheme(Base):
    """One version of a grading scheme. Family = (school_id, name)."""

    __tablename__ = "grading_schemes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    school_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        SAEnum(*SCHEME_STATUSES, name="schemestatus", native_enum=True),
        nullable=False,
        default="draft",
    )
    # definition: {"rounding_mode","precision","missing_policy","absent_policy",
    #              "exempt_policy","boundaries":[{"grade","min","max","remark"}],
    #              "tie_policy"} (spec §6.5)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # UNIQUE (school_id, name, version_no) lives in the migration (mirrors the
    # assessments model: uniqueness declared once, in the DDL that owns it).


class ResultProcessingRun(Base):
    """One execution of result processing over one assessment.

    Stores the exact inputs it consumed — scheme version row, scheme version
    number, template version, and the input_hash of every score consumed —
    so a run can be reproduced byte-identically (spec §9.4). A run found
    `failed` carries the operator-facing reason in `error` (deviation: the
    §6.5 table sketch has no error column; without it a failed run is
    unauditable — recorded in 09-phase-acceptance.md).
    """

    __tablename__ = "result_processing_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    school_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessments.id"), nullable=False
    )
    scheme_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grading_schemes.id"), nullable=False
    )
    scheme_version: Mapped[int] = mapped_column(Integer, nullable=False)
    template_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessment_template_versions.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        SAEnum(*RUN_STATUSES, name="runstatus", native_enum=True),
        nullable=False,
        default="queued",
    )
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ProcessedResult(Base):
    """One student's outcome in one run. Rows are immutable once written —
    recalculation creates a NEW run; the latest succeeded run is 'current'
    and older runs are retained (spec §9.4)."""

    __tablename__ = "processed_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    school_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("result_processing_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    subject_enrolment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subject_enrolments.id"), nullable=False
    )
    total: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    grade: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # breakdown: [{"component_key","status","value","contribution","excluded"}]
    breakdown: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    # flags: JSONB array of strings, e.g. ["renormalised"]
    flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
