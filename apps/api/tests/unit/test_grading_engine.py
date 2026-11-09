"""Golden tests for the Phase 4 calculation engine (spec §9, exit criterion).

The §9.3 worked-example rows are the first golden tests: Ada 78 A, Bayo 63 B,
Chidi 49.5→50 C (round once at the end), Dara absent→0 → 79 A, Efe exempt →
58/80*100 = 72.5 → 73 A (renormalise). Boundary edge values 39/40/44/45/69/70/
100 exercise every band edge of the golden scheme.
"""

from decimal import Decimal

import pytest

from app.grading.engine import (
    EngineComponent,
    EngineScheme,
    EngineTemplate,
    Boundary,
    ComputedResult,
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


def entered(seid: str, **cells: str) -> list[ScoreInput]:
    """One entered ScoreInput per given component, plus the rest missing —
    the full per-student consumption set (one entry per template component)."""
    out = [
        ScoreInput(seid, key, "entered", Decimal(value)) for key, value in sorted(cells.items())
    ]
    present = {s.component_key for s in out}
    out += [ScoreInput(seid, key, "missing", None) for key in ("CA1", "CA2", "Test", "Exam")
            if key not in present]
    return out


def total_of(values: dict[str, str]) -> ComputedResult:
    return compute(entered("se1", **values), GOLDEN_TEMPLATE, GOLDEN_SCHEME)


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
        ("exam", "expected_grade"),
        [
            ("0", "F"),  # 39 total
            ("1", "E"),  # 40
            ("4", "E"),  # 44 — top of E
            ("5", "D"),  # 45 — bottom of D
            ("29", "B"),  # 69 — top of B
            ("30", "A"),  # 70 — bottom of A
            ("60", "A"),  # 100
        ],
    )
    def test_edges(self, exam: str, expected_grade: str):
        result = total_of({"CA1": "10", "CA2": "10", "Test": "19", "Exam": exam})
        assert result.total == Decimal(str(10 + 10 + 19 + int(exam)))
        assert result.grade == expected_grade

    def test_zero_total_is_F(self):
        result = compute(
            [ScoreInput("se1", k, "missing", None) for k in ("CA1", "CA2", "Test", "Exam")],
            GOLDEN_TEMPLATE,
            GOLDEN_SCHEME,
        )
        assert result.total == Decimal("0")
        assert result.grade == "F"
        assert "incomplete" in result.flags


class TestPolicies:
    def test_missing_block_blocks_the_whole_student(self):
        scheme = EngineScheme(**{**GOLDEN_SCHEME.__dict__, "missing_policy": "block"})
        result = total_of({"CA1": "8", "Exam": "48"})  # CA2, Test missing
        assert result.blocked is True
        assert result.total is None
        assert result.grade is None
        assert "incomplete" in result.flags

    def test_missing_treat_zero(self):
        scheme = EngineScheme(**{**GOLDEN_SCHEME.__dict__, "missing_policy": "treat_zero"})
        result = compute(entered("se1", CA1="10"), GOLDEN_TEMPLATE, scheme)
        assert result.total == Decimal("10")
        assert result.flags == frozenset()

    def test_missing_flag_incomplete(self):
        result = total_of({"CA1": "10"})  # 10 + three missing → flagged
        assert result.total == Decimal("10")
        assert result.flags == frozenset({"incomplete"})

    def test_absent_exclude_and_renormalise(self):
        scheme = EngineScheme(**{**GOLDEN_SCHEME.__dict__, "absent_policy":
                                 "exclude_and_renormalise"})
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
            [ScoreInput("se1", k, "exempt", None) for k in ("CA1", "CA2", "Test", "Exam")],
            GOLDEN_TEMPLATE,
            GOLDEN_SCHEME,
        )
        assert result.blocked is True
        assert result.total is None
        assert result.flags == frozenset({"no_scoreable_components"})

    def test_full_precision_before_rounding(self):
        # 1/3 * 30 = 9.999… — kept at full precision, rounds to 10 once at the end.
        template = EngineTemplate(components=(EngineComponent("Quiz", Decimal("3"),
                                                             Decimal("30")),))
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
    def results_with_totals(self, *totals: str) -> list[ComputedResult]:
        out = []
        for i, total in enumerate(totals):
            seid = f"se{i}"
            # entered value == total on the golden template (weight == max).
            value = Decimal(total)
            scores = [
                ScoreInput(seid, "CA1", "entered", value if value <= 10 else Decimal("10")),
            ]
            rest = value - Decimal("10") if value > 10 else Decimal("0")
            scores.append(ScoreInput(seid, "CA2", "entered", rest if rest <= 10
                                     else Decimal("10")))
            rest -= Decimal("10") if rest > 10 else Decimal("0")
            scores.append(ScoreInput(seid, "Test", "entered", min(rest, Decimal("20"))))
            rest -= min(rest, Decimal("20"))
            scores.append(ScoreInput(seid, "Exam", "entered", max(rest, Decimal("0"))))
            out.append(compute(scores, GOLDEN_TEMPLATE, GOLDEN_SCHEME))
        return out

    def test_dense_ranking(self):
        results = self.results_with_totals("78", "63", "63", "50")
        ranked = rank(results, EngineScheme(**{**GOLDEN_SCHEME.__dict__, "tie_policy":
                                               "dense"}))
        assert [r.position for r in ranked] == [1, 2, 2, 3]
        assert [r.total for r in ranked] == [Decimal("78"), Decimal("63"),
                                             Decimal("63"), Decimal("50")]

    def test_competition_ranking(self):
        results = self.results_with_totals("78", "63", "63", "50")
        ranked = rank(results, EngineScheme(**{**GOLDEN_SCHEME.__dict__, "tie_policy":
                                               "competition"}))
        assert [r.position for r in ranked] == [1, 2, 2, 4]

    def test_ties_share_position_id_ordered(self):
        results = self.results_with_totals("63", "63")
        ranked = rank(results, GOLDEN_SCHEME)
        assert [r.position for r in ranked] == [1, 1]
        assert [r.subject_enrolment_id for r in ranked] == ["se0", "se1"]

    def test_blocked_results_are_not_ranked(self):
        good = total_of({"CA1": "8", "CA2": "7", "Test": "15", "Exam": "48"})
        scheme = EngineScheme(**{**GOLDEN_SCHEME.__dict__, "missing_policy": "block"})
        blocked = compute(entered("se9", CA1="8"), GOLDEN_TEMPLATE, scheme)
        ranked = rank([good, blocked], GOLDEN_SCHEME)
        assert len(ranked) == 1
        assert ranked[0].subject_enrolment_id == "se1"

    def test_rank_is_deterministic(self):
        results = self.results_with_totals("78", "63", "50", "79", "73")
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
        # synthesized missing entries count: a different component missing changes it
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
            "boundaries": [{"grade": "A", "min": 70, "max": 100},
                           {"grade": "B", "min": 0, "max": 69}],
            "tie_policy": "dense",
        }
        kwargs.update(overrides)
        return validate_scheme(**kwargs)  # type: ignore[arg-type]

    def test_valid_golden_boundaries(self):
        assert self.build() == (
            Boundary("B", 0, 69),
            Boundary("A", 70, 100),
        )

    def test_gap_rejected(self):
        with pytest.raises(ValueError, match="contiguous"):
            self.build(boundaries=[{"grade": "A", "min": 70, "max": 100},
                                   {"grade": "B", "min": 0, "max": 68}])

    def test_overlap_rejected(self):
        with pytest.raises(ValueError, match="contiguous"):
            self.build(boundaries=[{"grade": "A", "min": 70, "max": 100},
                                   {"grade": "B", "min": 0, "max": 70}])

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
            self.build(boundaries=[{"grade": "A", "min": 0, "max": 50},
                                   {"grade": "A", "min": 51, "max": 100}])

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
            boundaries=[{"grade": "A", "min": 70, "max": 100},
                        {"grade": "B", "min": 0, "max": 69}],
            tie_policy="dense",
        )
        assert scheme.boundaries == (Boundary("B", 0, 69), Boundary("A", 70, 100))
        assert scheme == GOLDEN_SCHEME


class TestUngradedGap:
    def test_precision_leaves_gap_flagged(self):
        # precision 1 keeps 44.5 unrounded at the band edge → no boundary holds
        # it → grade None + 'ungraded' flag (integer boundaries are the norm).
        scheme = EngineScheme(**{**GOLDEN_SCHEME.__dict__, "precision": 1})
        result = total_of({"CA1": "10", "CA2": "10", "Test": "14", "Exam": "10.5"})
        assert result.total == Decimal("44.5")
        assert result.grade is None
        assert "ungraded" in result.flags
