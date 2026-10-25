"""Error format — RFC 7807 problem details with stable machine codes (spec §8).

Every error the API returns is a problem-details document with a stable
machine code. The error-format helper lives in `platform` and is never
inlined (docs/handover_docs/02-api-conventions.md).
"""

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

# Stable machine codes (spec §8). Do not invent ad-hoc codes; add here if needed.
PERMISSION_DENIED = "PERMISSION_DENIED"
VERSION_CONFLICT = "VERSION_CONFLICT"
VALIDATION_ERROR = "VALIDATION_ERROR"
INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
RATE_LIMITED = "RATE_LIMITED"
NOT_FOUND = "NOT_FOUND"
CONFLICT = "CONFLICT"

STATUS_BY_CODE: dict[str, int] = {
    PERMISSION_DENIED: 403,
    VERSION_CONFLICT: 409,
    VALIDATION_ERROR: 422,
    INVALID_STATE_TRANSITION: 409,
    POSSIBLE_DUPLICATE: 409,
    RATE_LIMITED: 429,
    NOT_FOUND: 404,
    CONFLICT: 409,
}

TYPE_BY_CODE: dict[str, str] = {
    code: f"https://markbook.example/problems/{code.lower()}" for code in STATUS_BY_CODE
}


class ProblemError(Exception):
    """Raise from services/routers; the handler turns it into a problem document."""

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        status: int | None = None,
        extra: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.code = code
        self.status = status if status is not None else STATUS_BY_CODE.get(code, 400)
        self.extra = extra or {}
        self.headers = headers
        super().__init__(detail)

    @property
    def detail(self) -> str:
        return self.args[0] if self.args else ""


def problem_response(
    request: Request,
    *,
    status: int,
    code: str,
    detail: str,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    from app.platform.logging import request_id_ctx

    body: dict[str, Any] = {
        "type": TYPE_BY_CODE.get(code, "about:blank"),
        "title": code.replace("_", " ").title(),
        "status": status,
        "code": code,
        "detail": detail,
        "instance": str(request.url.path),
        "request_id": request_id_ctx.get(),
    }
    if extra:
        body.update(extra)
    return JSONResponse(status_code=status, content=body, headers=headers or {})


async def problem_exception_handler(request: Request, exc: ProblemError) -> JSONResponse:
    return problem_response(
        request,
        status=exc.status,
        code=exc.code,
        detail=exc.detail,
        extra=exc.extra,
        headers=exc.headers,
    )
