"""JWT token helper tests (Phase 1 — spec §7.1 access-token contract).

Covers create/decode round-trip, claims content, and the failure modes the
`require` dependency depends on: expired, tampered, wrong issuer, missing
claims.
"""

import time
from uuid import uuid4

import jwt as pyjwt
import pytest

from app.identity.tokens import create_access_token, decode_access_token
from app.platform.config import get_settings


def _make(user_id=None, school_id=None, token_version=1, session_id=None, **overrides):
    """Create a token with fresh identities unless given."""
    return create_access_token(
        user_id=user_id or uuid4(),
        school_id=school_id or uuid4(),
        token_version=token_version,
        session_id=session_id or uuid4(),
        **overrides,
    )


def test_round_trip_preserves_claims() -> None:
    user_id, school_id, session_id = uuid4(), uuid4(), uuid4()
    token, ttl = create_access_token(
        user_id=user_id, school_id=school_id, token_version=3, session_id=session_id
    )
    claims = decode_access_token(token)
    assert claims["sub"] == str(user_id)
    assert claims["school_id"] == str(school_id)
    assert claims["token_version"] == 3
    assert claims["session_id"] == str(session_id)
    assert claims["iss"] == "markbook"
    assert ttl == get_settings().access_token_ttl_seconds


def test_super_admin_flag_adds_claim() -> None:
    token, _ = create_access_token(
        user_id=uuid4(),
        school_id=uuid4(),
        token_version=1,
        session_id=uuid4(),
        is_super_admin=True,
    )
    assert decode_access_token(token)["super"] is True


def test_non_super_admin_has_no_super_claim() -> None:
    token, _ = _make()
    assert "super" not in decode_access_token(token)


def test_tampered_token_rejected() -> None:
    token, _ = _make()
    header, payload, _sig = token.split(".")
    with pytest.raises(pyjwt.InvalidTokenError):
        decode_access_token(f"{header}.{payload}xx")


def test_wrong_secret_rejected() -> None:
    """A token signed with a different secret must not verify."""
    settings = get_settings()
    forged = pyjwt.encode(
        {"sub": str(uuid4()), "exp": int(time.time()) + 900},
        settings.jwt_secret + "x",
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(pyjwt.InvalidTokenError):
        decode_access_token(forged)


def test_expired_token_rejected(monkeypatch) -> None:
    """A token whose exp lies in the past is rejected even with a valid signature."""

    class _ExpiredSettings:
        jwt_secret = get_settings().jwt_secret
        jwt_algorithm = get_settings().jwt_algorithm
        access_token_ttl_seconds = -1  # expires the moment it is created

    monkeypatch.setattr("app.identity.tokens.get_settings", lambda: _ExpiredSettings())
    token, _ = _make()
    with pytest.raises(pyjwt.ExpiredSignatureError):
        decode_access_token(token)


def test_missing_required_claim_rejected() -> None:
    """decode requires exp, sub, school_id, token_version, session_id."""
    token = _forge({"sub": str(uuid4()), "exp": int(time.time()) + 900})
    with pytest.raises(pyjwt.InvalidTokenError):
        decode_access_token(token)


def test_wrong_issuer_rejected() -> None:
    settings = get_settings()
    token = pyjwt.encode(
        {
            "sub": str(uuid4()),
            "school_id": str(uuid4()),
            "token_version": 1,
            "session_id": str(uuid4()),
            "exp": int(time.time()) + 900,
            "iss": "other-issuer",
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(pyjwt.InvalidTokenError):
        decode_access_token(token)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _forge(claims: dict) -> str:
    settings = get_settings()
    return pyjwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
