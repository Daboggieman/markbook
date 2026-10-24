"""Problem-error tests — stable machine codes and RFC 7807 shape."""

from app.platform.errors import (
    PERMISSION_DENIED,
    VERSION_CONFLICT,
    ProblemError,
)


def test_problem_error_defaults() -> None:
    err = ProblemError(PERMISSION_DENIED, "no")
    assert err.code == PERMISSION_DENIED
    assert err.status == 403


def test_problem_error_version_conflict() -> None:
    err = ProblemError(VERSION_CONFLICT, "stale write")
    assert err.status == 409


def test_unknown_code_defaults_to_400() -> None:
    err = ProblemError("SOMETHING_ELSE", "why")
    assert err.status == 400


def test_status_override() -> None:
    err = ProblemError("SOMETHING_ELSE", "why", status=418)
    assert err.status == 418
