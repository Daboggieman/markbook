"""SQLAlchemy models for platform-owned baseline tables (Phase 0).

schools, audit_events, outbox_events, jobs. These tables have no school_id
themselves (schools is the root; the others are cross-tenant logs where
school_id is a data column, not a partitioning key). The application DB role
is NOT a superuser and does NOT bypass RLS.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """All models inherit from this. Maps to Alembic's `imported_metadata`."""

    type_annotation_map = {
        UUID: UUID(as_uuid=True),
    }


class School(Base):
    """Exactly one row seeded at launch. Never updated after seed."""

    __tablename__ = "schools"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    config: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class AuditEvent(Base):
    """Append-only event log. App role has INSERT only — no UPDATE/DELETE."""

    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    school_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    actor_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv4/IPv6
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    prev_hash: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class OutboxEvent(Base):
    """Transactional outbox (spec §12, decision D5)."""

    __tablename__ = "outbox_events"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    school_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    topic: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Job(Base):
    """Job table — job status survives Redis loss (spec §12)."""

    __tablename__ = "jobs"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    school_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    type: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "results.process"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    # queued | running | succeeded | failed
    params: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
