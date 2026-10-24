"""Config system — pydantic-settings, environment only.

Secrets and configuration come from the environment, never the repo
(docs/handover_docs/08-repo-structure-and-hygiene.md). `.env` support exists
for local dev only; production must set real environment variables.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="MARKBOOK_",
        extra="ignore",
    )

    # App
    app_name: str = "markbook-api"
    environment: str = "dev"  # dev | staging | prod
    log_level: str = "INFO"
    log_format: str = "json"  # json | console

    # Database — the app role; NOT a superuser, RLS applies (spec §5).
    database_url: str = "postgresql+psycopg://markbook_app:markbook_app@localhost:5432/markbook"
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_echo: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Object storage (S3-compatible; MinIO in dev)
    s3_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "markbook-dev"
    s3_access_key: str = ""
    s3_secret_key: str = ""

    # Auth (used from Phase 1; declared here so config is complete)
    jwt_secret: str = "dev-only-change-me"  # noqa: S105 - dev default; env wins in prod
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = 900  # 10-15 min per spec §7.1
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 14
    argon2id_time_cost: int = 3
    argon2id_memory_cost: int = 65536
    argon2id_parallelism: int = 4

    # Idempotency
    idempotency_key_ttl_seconds: int = 60 * 60 * 24  # 24 h per spec §8

    # Pagination
    default_page_size: int = 50
    max_page_size: int = 200


@lru_cache
def get_settings() -> Settings:
    """Cached settings. Process-lifetime only — safe under the no-in-process-state
    rule because settings are process configuration, not user data."""
    return Settings()
