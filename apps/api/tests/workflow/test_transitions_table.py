"""The §10 transition table as unit tests — no database needed.

The table is the phase's contract: every legal edge, its permission, its
reason requirement and its side effects. If a future edit changes any of
these without changing the spec, these tests are the tripwire.

The guards themselves need a database (they read the sheet, runs and
approval records) — they are proven over HTTP in test_workflow_api.py.
"""

import dataclasses

import pytest
from pydantic import ValidationError

from app.workflow.schemas import StageDef, TransitionRequest, WorkflowDefinitionCreate
from app.workflow.service import SCOPED_TRANSITION_PERMISSIONS, TRANSITIONS

# Spec §10 table, verbatim: (from_state, action) → (to_state, permission).
SPEC_TABLE = {
    ("draft", "submit"): ("submitted", "scores.submit"),
    ("returned", "submit"): ("submitted", "scores.submit"),
    ("submitted", "start-review"): ("under_review", "scores.review"),
    ("under_review", "return"): ("returned", "scores.review"),
    ("under_review", "approve"): ("approved", "results.approve"),
    ("approved", "lock"): ("locked", "results.lock"),
    ("locked", "publish"): ("published", "results.publish"),
    ("published", "correct"): ("published", "results.correct"),
}


class TestTransitionTable:
    def test_exactly_the_spec_rows(self) -> None:
        assert set(TRANSITIONS) == set(SPEC_TABLE)

    def test_every_row_matches_spec(self) -> None:
        for key, (to_state, permission) in SPEC_TABLE.items():
            transition = TRANSITIONS[key]
            assert transition.to_state == to_state, key
            assert transition.permission == permission, key

    def test_reason_required_only_where_spec_demands(self) -> None:
        """return and correct need a reason; nothing else does."""
        assert {k for k, t in TRANSITIONS.items() if t.reason_required} == {
            ("under_review", "return"),
            ("published", "correct"),
        }

    def test_document_job_only_on_publish_and_correct(self) -> None:
        """The rendered-document side effects ride exactly on the two
        transitions that (re)publish results."""
        assert {k for k, t in TRANSITIONS.items() if t.document_job} == {
            ("locked", "publish"),
            ("published", "correct"),
        }

    def test_submit_guard_on_both_submit_edges(self) -> None:
        assert TRANSITIONS[("draft", "submit")].guards == ("submit_resolved",)
        assert TRANSITIONS[("returned", "submit")].guards == ("submit_resolved",)

    def test_review_and_approve_guards(self) -> None:
        assert TRANSITIONS[("submitted", "start-review")].guards == ("not_submitter",)
        assert set(TRANSITIONS[("under_review", "approve")].guards) == {
            "results_current",
            "separation_of_duties",
        }

    def test_results_permissions_are_school_scope_only(self) -> None:
        """Only the scores.* transition permissions honour the assigned scope
        (spec §10 marks exactly those two "(scoped)"); every results.*
        permission is school-scope only."""
        assert SCOPED_TRANSITION_PERMISSIONS == {"scores.submit", "scores.review"}
        for key, transition in TRANSITIONS.items():
            if transition.permission.startswith("results."):
                assert transition.permission not in SCOPED_TRANSITION_PERMISSIONS, key
            else:
                assert transition.permission in SCOPED_TRANSITION_PERMISSIONS, key

    def test_transitions_are_frozen(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            TRANSITIONS[("draft", "submit")].to_state = "approved"  # type: ignore[misc]


class TestTransitionSchemas:
    def test_reason_stripped_and_empty_becomes_none(self) -> None:
        request = TransitionRequest(reason="  Student was absent for the exam.  ")
        assert request.reason == "Student was absent for the exam."
        assert TransitionRequest(reason=None).reason is None
        assert TransitionRequest(reason="   ").reason is None

    def test_reason_cap(self) -> None:
        with pytest.raises(ValidationError):
            TransitionRequest(reason="x" * 2001)

    def test_stage_definition_shape(self) -> None:
        definition = WorkflowDefinitionCreate(
            name="Three-stage",
            stages=[
                StageDef(state="submitted", requires="scores.submit"),
                StageDef(state="under_review", requires="scores.review"),
            ],
        )
        assert definition.stages[0].state == "submitted"
        assert definition.stages[1].requires == "scores.review"
