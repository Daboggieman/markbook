"""Score-entry validation (Phase 3 — spec §6.4, §11.3 step 5).

Pure module: no DB, no framework — callable from the API service layer and
from the bulk-import worker job alike. The tests in
tests/unit/test_score_validation.py were written first (rule 10) and encode
the contract; the DB CHECK `(status = 'entered') = (value IS NOT NULL)` is
the last line of defence behind it.
"""

from app.assessment.schemas import ComponentDef, ScoreRowInput
from app.platform.errors import VALIDATION_ERROR, ProblemError

SCORE_STATUSES = ("entered", "absent", "exempt", "missing")


def validate_score_row(row: ScoreRowInput, component: ComponentDef) -> None:
    """Validate one score row against the component it targets.

    Raises ProblemError(VALIDATION_ERROR) on any invalid combination;
    returns None when the row is valid. Rules:

    1. status must be one of entered/absent/exempt/missing.
    2. entered ⇔ value is not None (the application-side mirror of the DB
       CHECK — a genuine zero is ('entered', Decimal('0.00'))).
    3. entered values are within 0..max_score inclusive.
    """
    if row.status not in SCORE_STATUSES:
        raise ProblemError(VALIDATION_ERROR, f"Unknown score status: {row.status!r}")

    if row.status == "entered":
        if row.value is None:
            raise ProblemError(
                VALIDATION_ERROR,
                f"Component {component.key}: status 'entered' requires a value",
            )
        if row.value < 0 or row.value > component.max_score:
            raise ProblemError(
                VALIDATION_ERROR,
                f"Component {component.key}: value {row.value} is outside 0..{component.max_score}",
            )
    elif row.value is not None:
        raise ProblemError(
            VALIDATION_ERROR,
            f"Component {component.key}: status {row.status!r} must not carry a value",
        )
