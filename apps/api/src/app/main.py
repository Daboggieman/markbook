"""FastAPI app factory and request lifecycle (Phase 0 deliverable).

Exits:
  - docker compose up works
  - health endpoint passes
  - OpenAPI served at /openapi.json (FastAPI default)
"""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.platform import db as platform_db
from app.platform.config import get_settings
from app.platform.errors import (
    VALIDATION_ERROR,
    ProblemError,
    problem_exception_handler,
    problem_response,
)
from app.platform.logging import configure_logging, set_request_context


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(
        level=get_settings().log_level,
        fmt=get_settings().log_format,
    )
    yield
    await platform_db.dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/openapi",
        redoc_url="/redoc",
    )

    # CORS — strict allowlist per spec §13.1 (filled in Phase 1 with the web app URL).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],  # Vite dev server
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Exception handler for our typed errors.
    app.add_exception_handler(ProblemError, problem_exception_handler)

    # Request logging middleware — sets request context for every log line.
    @app.middleware("http")
    async def log_request(request: Request, call_next):
        import uuid

        rid = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        set_request_context(request_id=rid)

        from app.platform.logging import get_logger

        log = get_logger("http")
        log.info("request_started", method=request.method, path=request.url.path)

        try:
            response = await call_next(request)
        except Exception as exc:
            log.error("request_failed", method=request.method, path=request.url.path, error=str(exc))
            raise
        else:
            log.info(
                "request_finished",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
            )
        return response

    # Health endpoint — used by the load balancer and docker healthcheck.
    @app.get("/health", tags=["health"])
    async def health() -> dict[str, Any]:
        from app.platform.logging import get_logger

        db_status = {"database": "unknown"}
        try:
            db_status = await platform_db.check_db_ready()
        except Exception as exc:
            db_status = {"database": f"error: {exc!r}"}

        return {
            "status": "ok",
            "environment": settings.environment,
            **db_status,
        }

    # Import and include routers here. Phase 1 adds identity and access routers.
    # from app.identity.router import router as identity_router
    # app.include_router(identity_router, prefix="/api/v1/identity", tags=["identity"])

    return app


app = create_app()