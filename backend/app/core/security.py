"""JWT issue/verify + cookie helpers."""
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Request, Response
from jose import JWTError, jwt

from app.core.config import get_settings

ACCESS_COOKIE = "lab_access"
REFRESH_COOKIE = "lab_refresh"
OIDC_STATE_COOKIE = "lab_oidc_state"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def issue_access_token(*, sub: str, role: str, extra: dict[str, Any] | None = None) -> str:
    s = get_settings()
    payload = {
        "sub": sub,
        "role": role,
        "iat": int(_now().timestamp()),
        "exp": int((_now() + timedelta(minutes=s.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
        "type": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(
        payload, s.JWT_SECRET_KEY.get_secret_value(), algorithm=s.JWT_ALGORITHM
    )


def issue_refresh_token(*, sub: str) -> str:
    s = get_settings()
    payload = {
        "sub": sub,
        "iat": int(_now().timestamp()),
        "exp": int((_now() + timedelta(days=s.JWT_REFRESH_TOKEN_EXPIRE_DAYS)).timestamp()),
        "type": "refresh",
    }
    return jwt.encode(
        payload, s.JWT_SECRET_KEY.get_secret_value(), algorithm=s.JWT_ALGORITHM
    )


def verify_token(token: str) -> dict[str, Any]:
    s = get_settings()
    try:
        return jwt.decode(token, s.JWT_SECRET_KEY.get_secret_value(), algorithms=[s.JWT_ALGORITHM])
    except JWTError as e:
        raise ValueError(f"invalid token: {e}") from e


def set_auth_cookies(response: Response, *, access: str, refresh: str) -> None:
    s = get_settings()
    secure = s.is_prod
    response.set_cookie(
        ACCESS_COOKIE,
        access,
        max_age=s.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        max_age=s.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api/auth",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    response.delete_cookie(OIDC_STATE_COOKIE, path="/api/auth")


def read_access_cookie(request: Request) -> str | None:
    return request.cookies.get(ACCESS_COOKIE)
