"""Cursor-based pagination (spec §2.3, §8).

Every list endpoint is paginated with a hard max page size. The cursor is an
opaque base64url token over `(sort_value, id)` so paging is stable under
concurrent writes.
"""

import base64
import binascii
from dataclasses import dataclass
from typing import Any

from app.platform.config import get_settings
from app.platform.errors import VALIDATION_ERROR, ProblemError


@dataclass(frozen=True, slots=True)
class Cursor:
    """Decoded cursor: the sort key value of the last item plus its id (tie-breaker)."""

    sort_value: str
    id: str


@dataclass(frozen=True, slots=True)
class Page:
    items: list[Any]
    next_cursor: str | None

    def model_dump(self) -> dict[str, Any]:
        return {"items": self.items, "next_cursor": self.next_cursor}


def encode_cursor(sort_value: Any, last_id: str) -> str:
    raw = f"{sort_value}|{last_id}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(token: str) -> Cursor:
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
        sort_value, last_id = raw.decode("utf-8").rsplit("|", 1)
        return Cursor(sort_value=sort_value, id=last_id)
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise ProblemError(VALIDATION_ERROR, "Invalid pagination cursor") from exc


def page_params(limit: int | None, cursor: str | None) -> tuple[int, Cursor | None]:
    """Validate limit against the hard max; decode the cursor."""
    settings = get_settings()
    limit_value = (
        min(settings.default_page_size, settings.max_page_size) if limit is None else limit
    )
    if limit_value < 1:
        raise ProblemError(VALIDATION_ERROR, "limit must be at least 1")
    limit_value = min(limit_value, settings.max_page_size)
    decoded = decode_cursor(cursor) if cursor else None
    return limit_value, decoded


def build_next_cursor(
    rows: list[Any], *, fetched_limit: int, sort_attr: str = "sort_value", id_attr: str = "id"
) -> str | None:
    """Build the next cursor from a page fetched with limit+1 rows.

    Callers fetch one extra row to detect a next page. If fewer rows than the
    requested limit came back, there is no next page. Otherwise the cursor
    points at the last row *within* the limit (caller passes rows[:limit] with
    rows[limit] present, or simply the rows it will return).
    """
    if not rows or len(rows) < fetched_limit:
        return None
    last = rows[fetched_limit - 1]
    return encode_cursor(getattr(last, sort_attr), getattr(last, id_attr))
