"""Authorization matrix (Phase 1 exit criterion, spec §7.2).

Tests the pure decision function `authorize()` against the grant/scope
semantics: school > assigned > own, deny on missing permission, deny on
resource mismatch. Parametrised to mirror the spec's matrix shape.
"""

from uuid import uuid4

import pytest

from app.access.service import (
    SENSITIVE_PERMISSIONS,
    Actor,
    ResourceRef,
    authorize,
    broadest_scope,
    scope_filter,
)
from app.platform.errors import PERMISSION_DENIED, ProblemError

SCHOOL = uuid4()


def _actor() -> Actor:
    return Actor(
        user_id=uuid4(),
        school_id=SCHOOL,
        token_version=1,
        session_id=uuid4(),
    )


# ---------------------------------------------------------------------------
# Missing permission
# ---------------------------------------------------------------------------


def test_missing_permission_denies() -> None:
    with pytest.raises(ProblemError) as exc_info:
        authorize([], "students.view", actor=_actor())
    assert exc_info.value.status == 403
    assert exc_info.value.code == PERMISSION_DENIED


def test_unrelated_permission_denies() -> None:
    grants = [("students.view", "school")]
    with pytest.raises(ProblemError):
        authorize(grants, "students.edit", resource=None, actor=_actor())


# ---------------------------------------------------------------------------
# school scope — the broadest, allows regardless of resource
# ---------------------------------------------------------------------------


def test_school_scope_allows_without_resource() -> None:
    decision = authorize([("students.view", "school")], "students.view", resource=None)
    assert decision.allowed
    assert decision.scope == "school"


def test_school_scope_allows_with_resource() -> None:
    resource = ResourceRef(resource_type="student", resource_id=uuid4(), created_by=uuid4())
    decision = authorize([("students.view", "school")], "students.view", resource)
    assert decision.allowed


# ---------------------------------------------------------------------------
# assigned scope
# ---------------------------------------------------------------------------


def test_assigned_scope_with_resource_keys_allows() -> None:
    resource = ResourceRef(resource_type="score", assignment_keys=("class:1", "subject:2"))
    decision = authorize([("scores.enter", "assigned")], "scores.enter", resource)
    assert decision.allowed


def test_assigned_scope_without_resource_denies() -> None:
    with pytest.raises(ProblemError) as exc_info:
        authorize([("scores.enter", "assigned")], "scores.enter", resource=None)
    assert exc_info.value.status == 403


def test_assigned_scope_with_empty_keys_denies() -> None:
    resource = ResourceRef(resource_type="score", assignment_keys=())
    with pytest.raises(ProblemError):
        authorize([("scores.enter", "assigned")], "scores.enter", resource)


# ---------------------------------------------------------------------------
# own scope
# ---------------------------------------------------------------------------


def test_own_scope_matching_owner_allows() -> None:
    actor = _actor()
    resource = ResourceRef(resource_type="report", created_by=actor.user_id)
    decision = authorize([("reports.view", "own")], "reports.view", resource, actor=actor)
    assert decision.allowed


def test_own_scope_other_owner_denies() -> None:
    actor = _actor()
    resource = ResourceRef(resource_type="report", created_by=uuid4())
    with pytest.raises(ProblemError):
        authorize([("reports.view", "own")], "reports.view", resource, actor=actor)


def test_own_scope_without_resource_denies() -> None:
    with pytest.raises(ProblemError):
        authorize([("reports.view", "own")], "reports.view", resource=None, actor=_actor())


def test_own_scope_without_actor_denies() -> None:
    resource = ResourceRef(resource_type="report", created_by=uuid4())
    with pytest.raises(ProblemError):
        authorize([("reports.view", "own")], "reports.view", resource, actor=None)


# ---------------------------------------------------------------------------
# Broadest scope wins; multiple grants collapse
# ---------------------------------------------------------------------------


def test_broadest_scope_school_beats_own() -> None:
    grants = [("students.view", "own"), ("students.view", "school")]
    decision = authorize(grants, "students.view", resource=None, actor=_actor())
    assert decision.allowed
    assert decision.scope == "school"


def test_broadest_scope_assigned_beats_own() -> None:
    grants = [("scores.enter", "own"), ("scores.enter", "assigned")]
    # assigned is broader than own: with no resource context, assigned denies.
    with pytest.raises(ProblemError) as exc_info:
        authorize(grants, "scores.enter", resource=None)
    assert exc_info.value.status == 403


def test_broadest_scope_helper_orders_narrow_to_wide() -> None:
    assert broadest_scope([]) is None
    assert broadest_scope(["own"]) == "own"
    assert broadest_scope(["own", "school", "assigned"]) == "school"


def test_scope_filter_returns_broadest() -> None:
    grants = [("scores.view", "own"), ("scores.view", "assigned")]
    assert scope_filter(grants, "scores.view") == "assigned"


def test_scope_filter_without_grant_raises() -> None:
    with pytest.raises(ProblemError) as exc_info:
        scope_filter([], "scores.view")
    assert exc_info.value.status == 403


def test_scope_filter_ignores_other_permissions() -> None:
    grants = [("scores.view", "school"), ("students.view", "school")]
    assert scope_filter(grants, "scores.view") == "school"


# ---------------------------------------------------------------------------
# Decision shape and sensitive permissions
# ---------------------------------------------------------------------------


def test_decision_shape_on_allow() -> None:
    decision = authorize([("students.view", "school")], "students.view")
    assert decision.allowed
    assert decision.scope == "school"


def test_sensitive_permissions_cover_publish_and_deletion() -> None:
    assert "results.publish" in SENSITIVE_PERMISSIONS
    assert "users.delete" in SENSITIVE_PERMISSIONS
    assert "roles.manage" in SENSITIVE_PERMISSIONS


def test_scope_of_unknown_grant_code_denies() -> None:
    # An unknown scope value should not be treated as school-wide or silently
    # fall through to own; it must deny to prevent a corrupted DB row from
    # granting unintended access (DB enum prevents this in prod, but defence
    # in depth).
    grants = [("students.view", "mystery")]
    with pytest.raises(ProblemError) as exc_info:
        authorize(grants, "students.view")
    assert exc_info.value.status == 403
