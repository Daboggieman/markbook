"""Scheme validation and grade lookup (spec §9.2 step 6).

Boundaries are validated at scheme CREATION (the service calls
`validate_scheme` before persisting), so compute() can trust them: contiguous,
non-overlapping integer bands spanning exactly 0..100. `find_grade` scans for
the first boundary containing the (already rounded) total.
"""

from decimal import Decimal, InvalidOperation

from app.grading.engine.types import (
    ABSENT_POLICIES,
    EXEMPT_POLICIES,
    MISSING_POLICIES,
    ROUNDING_MODES,
    TIE_POLICIES,
    Boundary,
    EngineScheme,
)

MAX_PRECISION = 4  # scores are NUMERIC(6,2); more than 4 dp is never meaningful


class SchemeValidationError(ValueError):
    """The scheme definition is not a valid grading scheme.

    A pure-engine ValueError: the service layer maps it to a 422
    VALIDATION_ERROR with this message.
    """


def _as_int(value: object, label: str) -> int:
    """Accept int, or a Decimal/str that is exactly integral; reject the rest."""
    if isinstance(value, bool):
        raise SchemeValidationError(f"{label} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        raise SchemeValidationError(f"{label} must be an integer")
    if isinstance(value, str):
        try:
            return _as_int(Decimal(value), label)
        except InvalidOperation as exc:
            raise SchemeValidationError(f"{label} must be an integer") from exc
    raise SchemeValidationError(f"{label} must be an integer")


def validate_scheme(
    *,
    rounding_mode: str,
    precision: int,
    missing_policy: str,
    absent_policy: str,
    exempt_policy: str,
    boundaries: list[dict[str, object]],
    tie_policy: str,
) -> tuple[Boundary, ...]:
    """Validate a scheme definition and return its boundaries as engine tuples.

    Raises SchemeValidationError with a human-readable message on any problem.
    Returns boundaries sorted by min ascending.
    """
    if rounding_mode not in ROUNDING_MODES:
        raise SchemeValidationError(f"Unknown rounding mode {rounding_mode!r}")
    if not isinstance(precision, int) or isinstance(precision, bool):
        raise SchemeValidationError("precision must be an integer")
    if not (0 <= precision <= MAX_PRECISION):
        raise SchemeValidationError(f"precision must be between 0 and {MAX_PRECISION}")
    if missing_policy not in MISSING_POLICIES:
        raise SchemeValidationError(f"Unknown missing_policy {missing_policy!r}")
    if absent_policy not in ABSENT_POLICIES:
        raise SchemeValidationError(f"Unknown absent_policy {absent_policy!r}")
    if exempt_policy not in EXEMPT_POLICIES:
        raise SchemeValidationError(f"Unknown exempt_policy {exempt_policy!r}")
    if tie_policy not in TIE_POLICIES:
        raise SchemeValidationError(f"Unknown tie_policy {tie_policy!r}")

    if not boundaries:
        raise SchemeValidationError("A scheme needs at least one boundary")

    parsed: list[tuple[int, Boundary]] = []
    seen_grades: set[str] = set()
    for raw in boundaries:
        if not isinstance(raw, dict):
            raise SchemeValidationError("Each boundary must be an object")
        grade = raw.get("grade")
        if not isinstance(grade, str) or not grade.strip():
            raise SchemeValidationError("Each boundary needs a non-empty grade")
        if grade in seen_grades:
            raise SchemeValidationError(f"Duplicate grade {grade!r}")
        seen_grades.add(grade)
        b_min = _as_int(raw.get("min"), f"Boundary {grade!r} min")
        b_max = _as_int(raw.get("max"), f"Boundary {grade!r} max")
        if b_min > b_max:
            raise SchemeValidationError(f"Boundary {grade!r}: min must not exceed max")
        remark = raw.get("remark")
        if remark is not None and not isinstance(remark, str):
            raise SchemeValidationError(f"Boundary {grade!r}: remark must be a string")
        parsed.append((b_min, Boundary(grade=grade, min=b_min, max=b_max, remark=remark)))

    # Contiguous and non-overlapping across 0..100 (spec §9.2 step 6).
    parsed.sort(key=lambda pair: pair[0])
    if parsed[0][1].min != 0:
        raise SchemeValidationError("Boundaries must start at 0")
    if parsed[-1][1].max != 100:
        raise SchemeValidationError("Boundaries must end at 100")
    for (_, lower), (_, upper) in zip(parsed, parsed[1:], strict=False):
        if upper.min != lower.max + 1:
            raise SchemeValidationError(
                f"Boundaries must be contiguous and non-overlapping: "
                f"{lower.grade!r} ends at {lower.max}, {upper.grade!r} starts at {upper.min}"
            )
    return tuple(b for _, b in parsed)


def build_scheme(
    *,
    rounding_mode: str,
    precision: int,
    missing_policy: str,
    absent_policy: str,
    exempt_policy: str,
    boundaries: list[dict[str, object]],
    tie_policy: str,
) -> EngineScheme:
    """Validate and build an EngineScheme in one call."""
    return EngineScheme(
        rounding_mode=rounding_mode,
        precision=precision,
        missing_policy=missing_policy,
        absent_policy=absent_policy,
        exempt_policy=exempt_policy,
        boundaries=validate_scheme(
            rounding_mode=rounding_mode,
            precision=precision,
            missing_policy=missing_policy,
            absent_policy=absent_policy,
            exempt_policy=exempt_policy,
            boundaries=boundaries,
            tie_policy=tie_policy,
        ),
        tie_policy=tie_policy,
    )


def find_grade(total: Decimal, boundaries: tuple[Boundary, ...]) -> str | None:
    """First boundary where min <= total <= max. None = no boundary contains
    the total (possible only with precision > 0, where a rounded total can
    fall in a gap between integer bands — flagged 'ungraded' upstream)."""
    for b in boundaries:
        if b.min <= total <= b.max:
            return b.grade
    return None
