"""Score-entry validation tests (Phase 3 — spec §6.4, §11.3 step 5).

Written BEFORE the implementation (rule 10). The contract under test is
`assessment.validation.validate_score_row`: given one score row and the
pinned template component it targets, raise ProblemError(VALIDATION_ERROR)
on any invalid combination, return None when valid.

The zero-vs-missing invariant is the heart of Phase 3: a genuine zero is
('entered', Decimal('0.00')); every other status must carry no value —
exactly what the DB CHECK `(status = 'entered') = (value IS NOT NULL)`
enforces. These tests are the application-side mirror of that constraint.
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from app.assessment.schemas import ComponentDef, ScoreRowInput
from app.assessment.validation import validate_score_row
from app.platform.errors import VALIDATION_ERROR, ProblemError

CA1 = ComponentDef(key="CA1", label="First CA", max_score=Decimal("10.00"), weight=Decimal("10"))
EXAM = ComponentDef(key="Exam", label="Exam", max_score=Decimal("60.00"), weight=Decimal("60"))


def _row(status: str, value: Decimal | None, key: str = "CA1") -> ScoreRowInput:
    return ScoreRowInput(
        subject_enrolment_id=uuid4(),
        component_key=key,
        status=status,  # type: ignore[arg-type]
        value=value,
    )


class TestEnteredRows:
    def test_zero_is_a_real_score(self) -> None:
        """0.00 entered is valid — this is the zero-vs-missing invariant."""
        assert validate_score_row(_row("entered", Decimal("0.00")), CA1) is None

    def test_value_within_range(self) -> None:
        assert validate_score_row(_row("entered", Decimal("8.00")), CA1) is None

    def test_value_at_max_score_boundary(self) -> None:
        assert validate_score_row(_row("entered", Decimal("10.00")), CA1) is None

    def test_missing_value_rejected(self) -> None:
        """entered without a value mirrors the DB CHECK's left side."""
        with pytest.raises(ProblemError) as exc:
            validate_score_row(_row("entered", None), CA1)
        assert exc.value.code == VALIDATION_ERROR

    def test_value_above_max_rejected(self) -> None:
        with pytest.raises(ProblemError) as exc:
            validate_score_row(_row("entered", Decimal("10.01")), CA1)
        assert exc.value.code == VALIDATION_ERROR

    def test_negative_value_rejected(self) -> None:
        with pytest.raises(ProblemError) as exc:
            validate_score_row(_row("entered", Decimal("-0.01")), CA1)
        assert exc.value.code == VALIDATION_ERROR

    def test_max_score_of_other_component_applies(self) -> None:
        """48 is valid for the Exam (max 60) but not for CA1 (max 10)."""
        assert validate_score_row(_row("entered", Decimal("48")), EXAM) is None
        with pytest.raises(ProblemError):
            validate_score_row(_row("entered", Decimal("48"), key="Exam"), CA1)


class TestNonEnteredRows:
    @pytest.mark.parametrize("status", ["absent", "exempt", "missing"])
    def test_no_value_required(self, status: str) -> None:
        assert validate_score_row(_row(status, None), CA1) is None

    @pytest.mark.parametrize("status", ["absent", "exempt", "missing"])
    def test_value_rejected(self, status: str) -> None:
        """A value on a non-entered row mirrors the DB CHECK's right side."""
        with pytest.raises(ProblemError) as exc:
            validate_score_row(_row(status, Decimal("5.00")), CA1)
        assert exc.value.code == VALIDATION_ERROR


class TestUnknownStatus:
    def test_unknown_status_rejected(self) -> None:
        """Guard for non-Pydantic callers (the bulk-import path parses CSV)."""
        with pytest.raises(ProblemError) as exc:
            validate_score_row(_row("exused", None), CA1)
        assert exc.value.code == VALIDATION_ERROR
