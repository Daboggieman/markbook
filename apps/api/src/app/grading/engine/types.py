"""Pure data types for the result calculation engine (spec §9.1).

This package is the Phase 4 engine contract boundary: stdlib only, no I/O,
no framework, no other app module (import-linter `engine-is-pure`). Decimal
arithmetic throughout — never float (spec rule 6).

The service layer converts DB rows into these types and consumes the
results; the engine knows nothing about SQLAlchemy, FastAPI or tenancy.
"""

from dataclasses import dataclass, field
from decimal import Decimal

# ---- policies (spec §9.2 step 2) -------------------------------------------

MISSING_POLICIES = ("block", "treat_zero", "flag_incomplete")
ABSENT_POLICIES = ("treat_zero", "exclude_and_renormalise")
EXEMPT_POLICIES = ("exclude_and_renormalise",)  # the only policy the spec defines
TIE_POLICIES = ("dense", "competition")
ROUNDING_MODES = (
    "ROUND_HALF_UP",
    "ROUND_HALF_EVEN",
    "ROUND_DOWN",
    "ROUND_UP",
    "ROUND_CEILING",
    "ROUND_FLOOR",
)

# Flags a computed result can carry (spec §9.2 step 8).
FLAG_INCOMPLETE = "incomplete"  # missing_policy=flag_incomplete fired
FLAG_RENORMALISED = "renormalised"  # at least one component was excluded
FLAG_UNGRADED = "ungraded"  # rounded total fell between boundaries
FLAG_NO_SCOREABLE = "no_scoreable_components"  # everything excluded — no total


@dataclass(frozen=True)
class EngineComponent:
    """One score component of the pinned template version (spec §6.4)."""

    key: str
    max_score: Decimal
    weight: Decimal
    required: bool = True


@dataclass(frozen=True)
class EngineTemplate:
    """The template version's components, keyed for lookup."""

    components: tuple[EngineComponent, ...]

    def by_key(self) -> dict[str, EngineComponent]:
        return {c.key: c for c in self.components}


@dataclass(frozen=True)
class ScoreInput:
    """One score cell as the engine sees it.

    `subject_enrolment_id` is opaque to compute() — it exists so a run can
    hash and rank across students without the engine importing app models.
    A component with no row at all is simply absent from the list; compute
    treats absent as 'missing' (the zero-vs-missing distinction lives in the
    scores table, not here).
    """

    subject_enrolment_id: str
    component_key: str
    status: str  # entered | absent | exempt | missing
    value: Decimal | None = None


@dataclass(frozen=True)
class Boundary:
    """One grade band. Integer min/max, validated contiguous over 0..100."""

    grade: str
    min: int
    max: int
    remark: str | None = None


@dataclass(frozen=True)
class EngineScheme:
    """The grading scheme definition (spec §6.5) in engine form."""

    rounding_mode: str = "ROUND_HALF_UP"
    precision: int = 0
    missing_policy: str = "flag_incomplete"
    absent_policy: str = "exclude_and_renormalise"
    exempt_policy: str = "exclude_and_renormalise"
    boundaries: tuple[Boundary, ...] = ()
    tie_policy: str = "dense"


@dataclass(frozen=True)
class BreakdownEntry:
    """One component's contribution to the total (spec §9.2 step 8)."""

    component_key: str
    status: str
    value: Decimal | None  # the raw score value, if any
    contribution: Decimal | None  # None for excluded components
    excluded: bool  # dropped by an exclude_and_renormalise policy


@dataclass(frozen=True)
class ComputedResult:
    """One student's computed outcome, before ranking."""

    subject_enrolment_id: str
    total: Decimal | None  # None when blocked or nothing scoreable
    grade: str | None
    breakdown: tuple[BreakdownEntry, ...] = ()
    flags: frozenset[str] = field(default_factory=frozenset)

    @property
    def blocked(self) -> bool:
        """missing_policy=block fired — the student cannot be processed."""
        return self.total is None and "incomplete" not in self.flags


@dataclass(frozen=True)
class RankedResult:
    """One student's computed outcome with their position (spec §9.2 step 7)."""

    subject_enrolment_id: str
    total: Decimal
    grade: str | None
    position: int
    breakdown: tuple[BreakdownEntry, ...] = ()
    flags: frozenset[str] = field(default_factory=frozenset)
