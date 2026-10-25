"""Pagination helper tests — hard max, cursor round-trip, bad cursor rejection."""

import uuid

import pytest

from app.platform.errors import ProblemError
from app.platform.pagination import (
    build_next_cursor,
    decode_cursor,
    encode_cursor,
    page_params,
)


class Row:
    """Mimics an ORM row for cursor-building."""

    def __init__(self, sort_value: str, id: str) -> None:
        self.sort_value = sort_value
        self.id = id


def test_cursor_round_trip() -> None:
    cursor = encode_cursor("2026-10-24T00:00:00+00:00", str(uuid.uuid4()))
    decoded = decode_cursor(cursor)
    assert decoded.sort_value == "2026-10-24T00:00:00+00:00"
    assert isinstance(decoded.id, str) and len(decoded.id) == 36


def test_decode_cursor_rejects_garbage() -> None:
    with pytest.raises(ProblemError) as exc:
        decode_cursor("not-a-cursor")
    assert exc.value.code == "VALIDATION_ERROR"


def test_page_params_hard_max() -> None:
    limit, cursor = page_params(limit=10_000, cursor=None)
    assert limit == 200  # hard max from settings


def test_page_params_defaults() -> None:
    limit, cursor = page_params(limit=None, cursor=None)
    assert limit == 50  # default page size
    assert cursor is None


def test_page_params_rejects_zero() -> None:
    with pytest.raises(ProblemError):
        page_params(limit=0, cursor=None)


def test_build_next_cursor_full_page() -> None:
    rows = [Row_factory(i) for i in range(51)]  # fetched limit+1
    cursor = build_next_cursor(rows[:50], fetched_limit=50)
    assert cursor is not None


def test_build_next_cursor_last_page() -> None:
    rows = [Row_factory(i) for i in range(30)]  # fewer than fetched_limit
    assert build_next_cursor(rows, fetched_limit=50) is None


def Row_factory(i: int) -> Row:
    return Row(sort_value=f"2026-10-24T00:00:{i:02d}", id=str(uuid.uuid4()))
