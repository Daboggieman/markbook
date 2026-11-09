"""Grading schemas — Pydantic request/response models (Phase 4).

Scheme definitions are validated by the pure engine (`build_scheme`); these
models only carry shape. Allowed policy/rounding values live in the engine
constants — the service maps a SchemeValidationError to a 422 with the
engine's message, so there is ONE authority on what a valid scheme is.
Totals are `Decimal` end to end (rule 6 — never float).
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BoundaryDef(BaseModel):
    """One grade band. Integer min/max; contiguity across 0..100 is the
    engine's rule (validate_scheme), not pydantic's."""

    grade: Annotated[str, Field(min_length=1, max_length=50)]
    min: int
    max: int
    remark: str | None = None


class SchemeDefinition(BaseModel):
    """The JSONB `definition` of a grading scheme version (spec §6.5)."""

    rounding_mode: str = "ROUND_HALF_UP"
    precision: int = 0
    missing_policy: str = "flag_incomplete"
    absent_policy: str = "treat_zero"
    exempt_policy: str = "exclude_and_renormalise"
    boundaries: Annotated[list[BoundaryDef], Field(min_length=1)]
    tie_policy: str = "dense"

    def engine_kwargs(self) -> dict[str, Any]:
        """Flatten into build_scheme() kwargs — the single call that validates
        and produces the engine's scheme object."""
        return {
            "rounding_mode": self.rounding_mode,
            "precision": self.precision,
            "missing_policy": self.missing_policy,
            "absent_policy": self.absent_policy,
            "exempt_policy": self.exempt_policy,
            "boundaries": [b.model_dump() for b in self.boundaries],
            "tie_policy": self.tie_policy,
        }


class SchemeCreate(BaseModel):
    """Create a scheme, or save the NEXT VERSION of an existing name
    (editing a scheme creates a new version — spec §9.4)."""

    name: Annotated[str, Field(min_length=1, max_length=255)]
    definition: SchemeDefinition


class SchemeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_id: UUID
    name: str
    version_no: int
    status: str
    definition: dict[str, Any]
    created_at: datetime


class ProcessRequest(BaseModel):
    """Recalculation is explicit: the body names the scheme VERSION to use
    (spec §9.4). The template version is the one the assessment pins."""

    scheme_id: UUID


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    assessment_id: UUID
    scheme_id: UUID
    scheme_version: int
    template_version_id: UUID
    status: str
    input_hash: str | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    requested_by: UUID | None
    created_at: datetime


class ProcessedResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    subject_enrolment_id: UUID
    student_name: str | None = None  # joined for the UI; None on bare-row paths
    total: Decimal | None
    grade: str | None
    position: int | None
    breakdown: list[dict[str, Any]]
    flags: list[str]


class ResultsResponse(BaseModel):
    """The current results for an assessment: the latest succeeded run and
    its rows, position-ordered."""

    run: RunResponse
    results: list[ProcessedResultResponse]
