"""Golden tests for the Phase 4 calculation engine (spec §9, exit criterion).

The §9.3 worked-example rows are the first golden tests: Ada 78 A, Bayo 63 B,
Chidi 49.5→50 C (round once at the end), Dara absent→0 → 79 A, Efe exempt →
58/80*100 = 72.5 → 73 A (renormalise). Boundary edge values 39/40/44/45/69/70/
100 exercise every band edge of the golden scheme.
"""

from dataclasses import replace
from decimal import Decimal

import pytest

from app.grading.engine import (
    Boundary,
    ComputedResult,
    EngineComponent,
    EngineScheme,
    EngineTemplate,
    ScoreInput,
    build_scheme,
    compute,
    input_hash,
    rank,
    validate_scheme,
)

# ---- the golden fixtures (spec §9.3) ----------------------------------------

GOLDEN_TEMPLATE = EngineTemplate(
    components=(
        EngineComponent("CA1", Decimal("10"), Decimal("10")),
        EngineComponent("CA2", Decimal("10"), Decimal("10")),
        EngineComponent("Test", Decimal("20"), Decimal("20")),
        EngineComponent("Exam", Decimal("60"), Decimal("60")),
    )
)

GOLDEN_BOUNDARIES = (
    Boundary("A", 70, 100, "Excellent"),
    Boundary("B", 60, 69, "Very good"),
    Boundary("C", 50, 59, "Good"),
    Boundary("D", 45, 49, "Pass"),
    Boundary("E", 40, 44, "Weak pass"),
    Boundary("F", 0, 39, "Fail"),
)

GOLDEN_SCHEME = EngineScheme(
    rounding_mode="ROUND_HALF_UP",
    precision=0,
    missing_policy="flag_incomplete",
    absent_policy="treat_zero",
    exempt_policy="exclude_and_renormalise",
    boundaries=GOLDEN_BOUNDARIES,
    tie_policy="dense",
)

COMPONENT_KEYS = ("CA1", "CA2", "Test", "Exam")


def entered(seid: str, **cells: str) -> list[ScoreInput]:
    """One entered ScoreInput per given component, plus the rest missing —
    the full per-student consumption set (one entry per template component)."""
    out = [ScoreInput(seid, key, "entered", Decimal(value)) for key, value in sorted(cells.items())]
    present = {s.component_key for s in out}
    out += [ScoreInput(seid, key, "missing", None) for key in COMPONENT_KEYS if key not in present]
    return out


def total_of(values: dict[str, str]) -> ComputedResult:
    return compute(entered("se1", **values), GOLDEN_TEMPLATE, GOLDEN_SCHEME)


def result_with_total(seid: str, total: str) -> ComputedResult:
    """A computed result with exactly `total` under the golden template:
    CA1 10 + CA2 10 + Test 20 + Exam (total - 40); valid for totals 40..100."""
    exam = Decimal(total) - 40
    assert Decimal("0") <= exam <= 60
    return compute(
        entered(seid, CA1="10", CA2="10", Test="20", Exam=str(exam)),
        GOLDEN_TEMPLATE,
        GOLDEN_SCHEME,
    )


class TestGoldenExample:
    """The five §9.3 rows — these are the exit-criterion golden tests."""

    def test_ada(self):
        result = total_of({"CA1": "8", "CA2": "7", "Test": "15", "Exam": "48"})
        assert result.total == Decimal("78")
        assert result.grade == "A"
        assert result.flags == frozenset()
        assert result.blocked is False

    def test_bayo(self):
        result = total_of({"CA1": "6", "CA2": "5", "Test": "12", "Exam": "40"})
        assert result.total == Decimal("63")
        assert result.grade == "B"

    def test_chidi_rounds_once_at_the_end(self):
        # 5 + 4.5 + 9 + 31 = 49.5 → 50 (HALF_UP), grade C — not 49.
        result = total_of({"CA1": "5", "CA2": "4.5", "Test": "9", "Exam": "31"})
        assert result.total == Decimal("50")
        assert result.grade == "C"

    def test_dara_absent_treated_as_zero(self):
        # absent → treat_zero: 9 + 0 + 18 + 52 = 79 → A; no renormalise flag.
        result = compute(
            [
                ScoreInput("se1", "CA1", "entered", Decimal("9")),
                ScoreInput("se1", "CA2", "absent", None),
                ScoreInput("se1", "Test", "entered", Decimal("18")),
                ScoreInput("se1", "Exam", "entered", Decimal("52")),
            ],
            GOLDEN_TEMPLATE,
            GOLDEN_SCHEME,
        )
        assert result.total == Decimal("79")
        assert result.grade == "A"
        assert result.flags == frozenset()

    def test_efe_exempt_renormalises(self):
        # exempt → excluded: 7 + 6 + 45 = 58 over included weight 80
        # → 58 / 80 * 100 = 72.5 → 73 (HALF_UP) → A, flagged renormalised.
        result = compute(
            [
                ScoreInput("se1", "CA1", "entered", Decimal("7")),
                ScoreInput("se1", "CA2", "entered", Decimal("6")),
                ScoreInput("se1", "Test", "exempt", None),
                ScoreInput("se1", "Exam", "entered", Decimal("45")),
            ],
            GOLDEN_TEMPLATE,
            GOLDEN_SCHEME,
        )
        assert result.total == Decimal("73")
        assert result.grade == "A"
        assert result.flags == frozenset({"renormalised"})

    def test_breakdown_contents(self):
        result = total_of({"CA1": "8", "CA2": "7", "Test": "15", "Exam": "48"})
        by_key = {e.component_key: e for e in result.breakdown}
        assert by_key["CA1"].contribution == Decimal("8")
        assert by_key["Exam"].contribution == Decimal("48")
        assert all(not e.excluded for e in result.breakdown)


class TestBoundaryEdges:
    """Edge values 39, 40, 44, 45, 69, 70, 100 — every band edge."""

    @pytest.mark.parametrize(
        ("test", "exam", "expected_total", "expected_grade"),
        [
            # CA1 10 + CA2 10 + Test 19 = 39, plus the exam.
            ("19", "0", "39", "F"),
            ("19", "1", "40", "E"),
            ("19", "5", "44", "E"),
            ("19", "6", "45", "D"),
            ("19", "30", "69", "B"),
            ("19", "31", "70", "A"),
            ("20", "60", "100", "A"),
        ],
    )
    def test_edges(self, test: str, exam: str, expected_total: str, expected_grade: str):
        result = total_of({"CA1": "10", "CA2": "10", "Test": test, "Exam": exam})
        assert result.total == Decimal(expected_total)
        assert result.grade == expected_grade

    def test_zero_total_is_F(self):
        result = compute(
            [ScoreInput("se1", k, "missing", None) for k in COMPONENT_KEYS],
            GOLDEN_TEMPLATE,
            GOLDEN_SCHEME,
        )
        assert result.total == Decimal("0")
        assert result.grade == "F"
        assert "incomplete" in result.flags


class TestPolicies:
    def test_missing_block_blocks_the_whole_student(self):
        scheme = replace(GOLDEN_SCHEME, missing_policy="block")
        result = compute(
            entered("se1", CA1="8", Exam="48"),  # CA2, Test missing
            GOLDEN_TEMPLATE,
            scheme,
        )
        assert result.blocked is True
        assert result.total is None
        assert result.grade is None
        assert "incomplete" in result.flags

    def test_missing_treat_zero(self):
        scheme = replace(GOLDEN_SCHEME, missing_policy="treat_zero")
        result = compute(entered("se1", CA1="10"), GOLDEN_TEMPLATE, scheme)
        assert result.total == Decimal("10")
        assert result.flags == frozenset()

    def test_missing_flag_incomplete(self):
        result = total_of({"CA1": "10"})  # 10 + three missing → flagged
        assert result.total == Decimal("10")
        assert result.flags == frozenset({"incomplete"})

    def test_absent_exclude_and_renormalise(self):
        scheme = replace(GOLDEN_SCHEME, absent_policy="exclude_and_renormalise")
        result = compute(
            [
                ScoreInput("se1", "CA1", "entered", Decimal("7")),
                ScoreInput("se1", "CA2", "entered", Decimal("6")),
                ScoreInput("se1", "Test", "absent", None),
                ScoreInput("se1", "Exam", "entered", Decimal("45")),
            ],
            GOLDEN_TEMPLATE,
            scheme,
        )
        # same as Efe: 58/80*100 = 72.5 → 73
        assert result.total == Decimal("73")
        assert result.flags == frozenset({"renormalised"})

    def test_exempt_cannot_be_treated_as_zero(self):
        # The spec defines exactly one exempt policy; a scheme that says
        # otherwise is rejected at creation.
        with pytest.raises(ValueError, match="exempt_policy"):
            validate_scheme(
                rounding_mode="ROUND_HALF_UP",
                precision=0,
                missing_policy="flag_incomplete",
                absent_policy="treat_zero",
                exempt_policy="treat_zero",
                boundaries=[{"grade": "A", "min": 0, "max": 100}],
                tie_policy="dense",
            )

    def test_everything_excluded_has_no_total(self):
        result = compute(
            [ScoreInput("se1", k, "exempt", None) for k in COMPONENT_KEYS],
            GOLDEN_TEMPLATE,
            GOLDEN_SCHEME,
        )
        assert result.blocked is True
        assert result.total is None
        assert result.flags == frozenset({"no_scoreable_components"})

    def test_full_precision_before_rounding(self):
        # 1/3 * 30 = 9.999… — kept at full precision, rounds to 10 once at the end.
        template = EngineTemplate(
            components=(EngineComponent("Quiz", Decimal("3"), Decimal("30")),)
        )
        scheme = EngineScheme(
            rounding_mode="ROUND_HALF_UP",
            precision=0,
            missing_policy="treat_zero",
            absent_policy="treat_zero",
            exempt_policy="exclude_and_renormalise",
            boundaries=(Boundary("A", 0, 100),),
            tie_policy="dense",
        )
        result = compute([ScoreInput("se1", "Quiz", "entered", Decimal("1"))], template, scheme)
        assert result.total == Decimal("10")


class TestRanking:
    def test_dense_ranking(self):
        results = [result_with_total(f"se{i}", t) for i, t in enumerate(("78", "63", "63", "50"))]
        ranked = rank(results, replace(GOLDEN_SCHEME, tie_policy="dense"))
        assert [r.position for r in ranked] == [1, 2, 2, 3]
        assert [r.total for r in ranked] == [
            Decimal("78"),
            Decimal("63"),
            Decimal("63"),
            Decimal("50"),
        ]

    def test_competition_ranking(self):
        results = [result_with_total(f"se{i}", t) for i, t in enumerate(("78", "63", "63", "50"))]
        ranked = rank(results, replace(GOLDEN_SCHEME, tie_policy="competition"))
        assert [r.position for r in ranked] == [1, 2, 2, 4]

    def test_ties_share_position_id_ordered(self):
        results = [result_with_total("se0", "63"), result_with_total("se1", "63")]
        ranked = rank(results, GOLDEN_SCHEME)
        assert [r.position for r in ranked] == [1, 1]
        assert [r.subject_enrolment_id for r in ranked] == ["se0", "se1"]

    def test_blocked_results_are_not_ranked(self):
        good = result_with_total("se1", "78")
        scheme = replace(GOLDEN_SCHEME, missing_policy="block")
        blocked = compute(entered("se9", CA1="8"), GOLDEN_TEMPLATE, scheme)
        ranked = rank([good, blocked], GOLDEN_SCHEME)
        assert len(ranked) == 1
        assert ranked[0].subject_enrolment_id == "se1"

    def test_rank_is_deterministic(self):
        results = [
            result_with_total(f"se{i}", t) for i, t in enumerate(("78", "63", "50", "79", "73"))
        ]
        first = rank(results, GOLDEN_SCHEME)
        second = rank(list(reversed(results)), GOLDEN_SCHEME)
        assert first == second


class TestDeterminism:
    def test_identical_inputs_identical_results(self):
        a = total_of({"CA1": "8", "CA2": "7", "Test": "15", "Exam": "48"})
        b = total_of({"CA1": "8", "CA2": "7", "Test": "15", "Exam": "48"})
        assert a == b

    def test_input_hash_stable(self):
        scores = entered("se1", CA1="8", CA2="7", Test="15", Exam="48")
        assert input_hash(scores) == input_hash(list(reversed(scores)))

    def test_input_hash_decimal_form_insensitive(self):
        a = input_hash([ScoreInput("se1", "CA1", "entered", Decimal("8.00"))])
        b = input_hash([ScoreInput("se1", "CA1", "entered", Decimal("8"))])
        assert a == b

    def test_input_hash_covers_everything_consumed(self):
        base = entered("se1", CA1="8", CA2="7", Test="15", Exam="48")
        assert input_hash(base) == input_hash(base)
        changed = [ScoreInput("se1", "CA1", "entered", Decimal("9"))] + base[1:]
        assert input_hash(base) != input_hash(changed)
        # synthesized missing entries count: dropping one changes the hash
        fewer = [s for s in base if s.component_key != "Exam"]
        assert input_hash(base) != input_hash(fewer)


class TestSchemeValidation:
    def build(self, **overrides: object) -> tuple[Boundary, ...]:
        kwargs: dict[str, object] = {
            "rounding_mode": "ROUND_HALF_UP",
            "precision": 0,
            "missing_policy": "flag_incomplete",
            "absent_policy": "treat_zero",
            "exempt_policy": "exclude_and_renormalise",
            "boundaries": [
                {"grade": "A", "min": 70, "max": 100},
                {"grade": "B", "min": 0, "max": 69},
            ],
            "tie_policy": "dense",
        }
        kwargs.update(overrides)
        return validate_scheme(**kwargs)  # type: ignore[arg-type]

    def test_valid_golden_boundaries(self):
        assert self.build() == (Boundary("B", 0, 69), Boundary("A", 70, 100))

    def test_gap_rejected(self):
        with pytest.raises(ValueError, match="contiguous"):
            self.build(
                boundaries=[
                    {"grade": "A", "min": 70, "max": 100},
                    {"grade": "B", "min": 0, "max": 68},
                ]
            )

    def test_overlap_rejected(self):
        with pytest.raises(ValueError, match="contiguous"):
            self.build(
                boundaries=[
                    {"grade": "A", "min": 70, "max": 100},
                    {"grade": "B", "min": 0, "max": 70},
                ]
            )

    def test_must_reach_zero_and_hundred(self):
        with pytest.raises(ValueError, match="start at 0"):
            self.build(boundaries=[{"grade": "A", "min": 1, "max": 100}])
        with pytest.raises(ValueError, match="end at 100"):
            self.build(boundaries=[{"grade": "A", "min": 0, "max": 99}])

    def test_min_above_max_rejected(self):
        with pytest.raises(ValueError, match="min must not exceed max"):
            self.build(boundaries=[{"grade": "A", "min": 50, "max": 40}])

    def test_duplicate_grade_rejected(self):
        with pytest.raises(ValueError, match="Duplicate grade"):
            self.build(
                boundaries=[
                    {"grade": "A", "min": 0, "max": 50},
                    {"grade": "A", "min": 51, "max": 100},
                ]
            )

    def test_unknown_policy_rejected(self):
        with pytest.raises(ValueError, match="missing_policy"):
            self.build(missing_policy="invent")
        with pytest.raises(ValueError, match="absent_policy"):
            self.build(absent_policy="invent")
        with pytest.raises(ValueError, match="tie_policy"):
            self.build(tie_policy="invent")
        with pytest.raises(ValueError, match="rounding mode"):
            self.build(rounding_mode="ROUND_SIDEWAYS")

    def test_precision_bounds(self):
        with pytest.raises(ValueError, match="precision"):
            self.build(precision=5)
        with pytest.raises(ValueError, match="precision"):
            self.build(precision=-1)

    def test_build_scheme_round_trip(self):
        scheme = build_scheme(
            rounding_mode="ROUND_HALF_UP",
            precision=0,
            missing_policy="flag_incomplete",
            absent_policy="treat_zero",
            exempt_policy="exclude_and_renormalise",
            boundaries=[{"grade": "A", "min": 70, "max": 100}, {"grade": "B", "min": 0, "max": 69}],
            tie_policy="dense",
        )
        assert scheme.boundaries == (Boundary("B", 0, 69), Boundary("A", 70, 100))
        # Same engine-relevant settings as the golden scheme (boundaries differ).
        assert scheme.rounding_mode == GOLDEN_SCHEME.rounding_mode
        assert scheme.precision == GOLDEN_SCHEME.precision
        assert scheme.missing_policy == GOLDEN_SCHEME.missing_policy
        assert scheme.absent_policy == GOLDEN_SCHEME.absent_policy
        assert scheme.exempt_policy == GOLDEN_SCHEME.exempt_policy
        assert scheme.tie_policy == GOLDEN_SCHEME.tie_policy


class TestUngradedGap:
    def test_precision_leaves_gap_flagged(self):
        # precision 1 keeps 44.5 unrounded at the band edge → no boundary
        # holds it → grade None + 'ungraded' flag (integer boundaries are norm).
        scheme = replace(GOLDEN_SCHEME, precision=1)
        result = compute(
            entered("se1", CA1="10", CA2="10", Test="14", Exam="10.5"),
            GOLDEN_TEMPLATE,
            scheme,
        )
        assert result.total == Decimal("44.5")
        assert result.grade is None
        assert "ungraded" in result.flags
