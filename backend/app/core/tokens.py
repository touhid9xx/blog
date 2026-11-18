import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from jwt import InvalidTokenError

from app.core.config import get_settings

TokenType = Literal["access", "refresh"]


class TokenError(Exception):
    """Raised when a JWT is invalid, expired, or of the wrong type."""


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _encode(
    sub: str,
    ttype: TokenType,
    expires_delta: timedelta,
    extra: dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    payload: dict[str, Any] = {
        "sub": sub,
        "type": ttype,
        "iat": int(_now().timestamp()),
        "exp": int((_now() + expires_delta).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: str, role: str) -> str:
    settings = get_settings()
    return _encode(
        sub=user_id,
        ttype="access",
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra={"role": role},
    )


def create_refresh_token(user_id: str) -> str:
    settings = get_settings()
    return _encode(
        sub=user_id,
        ttype="refresh",
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def _decode(token: str, expected: TokenType) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except InvalidTokenError as e:
        raise TokenError(f"invalid token: {e}") from e

    if payload.get("type") != expected:
        raise TokenError(f"expected {expected} token, got {payload.get('type')!r}")
    if not payload.get("sub"):
        raise TokenError("token missing subject")
    return payload


def decode_access(token: str) -> dict[str, Any]:
    return _decode(token, "access")


def decode_refresh(token: str) -> dict[str, Any]:
    return _decode(token, "refresh")
