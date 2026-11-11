"""People module — SQLAlchemy models (Phase 2).

Mirrors migrations/versions/0003_people_academic.py. students archive via
`archived_at` (spec §6: no hard deletes); duplicate detection uses the
trigram index created by migration 0003.
"""

import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.models import Base

if TYPE_CHECKING:
    from app.academic.models import Enrolment


def uuid7() -> uuid.UUID:
    """Time-ordered UUIDv7 (spec §6 convention; index-friendly).

    The `uuid7` distribution (pyproject) installs as the module
    `uuid_extensions`, not `uuid7` — hence the import path.
    """
    from uuid_extensions import uuid7 as _uuid7

    return uuid.UUID(str(_uuid7()))


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (Index("ix_students_school_names", "school_id", "last_name", "first_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    school_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False
    )
    system_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    admission_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    sex: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(
        SAEnum(
            "active", "graduated", "withdrawn", "archived", name="studentstatus", native_enum=True
        ),
        nullable=False,
        default="active",
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    enrolments: Mapped[list["Enrolment"]] = relationship(
        "Enrolment", back_populates="student", lazy="noload"
    )


class Guardian(Base):
    __tablename__ = "guardians"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    school_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(CITEXT, nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class StudentGuardian(Base):
    """Junction: student ↔ guardian. school_id denormalised for RLS (as user_roles)."""

    __tablename__ = "student_guardians"

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), primary_key=True
    )
    guardian_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("guardians.id", ondelete="CASCADE"), primary_key=True
    )
    school_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False
    )
    relationship: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
