"""The Phase 4 calculation engine (spec §9).

Pure functions, no I/O, no framework imports, `Decimal` arithmetic only —
enforced by the import-linter `engine-is-pure` contract. The service layer
(`app.grading.service`) converts DB rows into these types and consumes the
outputs; nothing in here knows about SQLAlchemy, FastAPI or tenancy.

Public API (spec §9.1):

    compute(student_scores, template, scheme) -> ComputedResult   # one student
    rank(results, scheme)                     -> list[RankedResult]
    input_hash(scores)                        -> str              # spec §9.4
    validate_scheme(...) / build_scheme(...)  # called at scheme creation
"""

from app.grading.engine.compute import STATUS_ENTERED, STATUS_MISSING, compute
from app.grading.engine.hashing import canonical_value, input_hash
from app.grading.engine.rank import rank
from app.grading.engine.scheme import (
    MAX_PRECISION,
    SchemeValidationError,
    build_scheme,
    find_grade,
    validate_scheme,
)
from app.grading.engine.types import (
    ABSENT_POLICIES,
    EXEMPT_POLICIES,
    FLAG_INCOMPLETE,
    FLAG_NO_SCOREABLE,
    FLAG_RENORMALISED,
    FLAG_UNGRADED,
    MISSING_POLICIES,
    ROUNDING_MODES,
    TIE_POLICIES,
    Boundary,
    BreakdownEntry,
    ComputedResult,
    EngineComponent,
    EngineScheme,
    EngineTemplate,
    RankedResult,
    ScoreInput,
)

__all__ = [
    "ABSENT_POLICIES",
    "EXEMPT_POLICIES",
    "FLAG_INCOMPLETE",
    "FLAG_NO_SCOREABLE",
    "FLAG_RENORMALISED",
    "FLAG_UNGRADED",
    "MAX_PRECISION",
    "MISSING_POLICIES",
    "ROUNDING_MODES",
    "STATUS_ENTERED",
    "STATUS_MISSING",
    "SchemeValidationError",
    "TIE_POLICIES",
    "Boundary",
    "BreakdownEntry",
    "ComputedResult",
    "EngineComponent",
    "EngineScheme",
    "EngineTemplate",
    "RankedResult",
    "ScoreInput",
    "build_scheme",
    "canonical_value",
    "compute",
    "find_grade",
    "input_hash",
    "rank",
    "validate_scheme",
]
