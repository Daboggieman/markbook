"""Object storage client for published documents (Phase 5).

The seam is narrow by design: `put` (returns checksum) and `presigned_get`
(time-limited download URL — signed short-lived URLs per
08-security-and-operations.md). boto3 is imported lazily inside the S3
client: it is not an API dependency, the API never touches storage bytes —
only the WORKER puts, and only presigned GETs come back through the API.

Tests inject a fake implementing the same protocol; no test ever needs S3.
"""

import hashlib
from typing import Any, Protocol
from uuid import UUID

from app.platform.config import get_settings
from app.platform.logging import get_logger

log = get_logger("documents")

CHECKSUM_ALGORITHM = "sha256"


def checksum_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class StorageClient(Protocol):
    """What the documents service needs from object storage."""

    def put(self, key: str, data: bytes) -> str:
        """Store bytes under `key`; return the checksum (sha256 hex)."""
        ...

    def presigned_get(self, key: str, expires_in: int) -> str:
        """A time-limited download URL for `key`."""
        ...


class S3Storage:
    """S3-compatible client (MinIO in dev). boto3 is lazy — constructing this
    class never imports it; the first put/presigned_get does."""

    def __init__(self, *, expires_in: int = 300) -> None:
        settings = get_settings()
        self._endpoint = settings.s3_endpoint
        self._bucket = settings.s3_bucket
        self._access_key = settings.s3_access_key
        self._secret_key = settings.s3_secret_key
        self._expires_in = expires_in
        self._client: Any = None

    def _boto(self) -> Any:
        if self._client is None:
            try:
                import boto3  # noqa: PLC0415 — lazy by design; see module docstring
            except ImportError as exc:  # pragma: no cover — dev images carry boto3
                raise RuntimeError(
                    "boto3 is not installed; object storage is unavailable in this image"
                ) from exc
            self._client = boto3.client(
                "s3",
                endpoint_url=self._endpoint,
                aws_access_key_id=self._access_key,
                aws_secret_access_key=self._secret_key,
            )
        return self._client

    def put(self, key: str, data: bytes) -> str:
        self._boto().put_object(Bucket=self._bucket, Key=key, Body=data)
        return checksum_of(data)

    def presigned_get(self, key: str, expires_in: int) -> str:
        return self._boto().generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )


def get_storage() -> StorageClient:
    """The process storage client. Swappable in tests via monkeypatch."""
    return S3Storage()


def storage_key_for(
    *, school_id: UUID, assessment_id: UUID, enrolment_id: UUID, kind: str, doc_version: int
) -> str:
    """Deterministic key: every version is a distinct object, and a
    superseded object is never overwritten (immutability, spec §10)."""
    return f"schools/{school_id}/{kind}/{assessment_id}/{enrolment_id}/v{doc_version}.pdf"
