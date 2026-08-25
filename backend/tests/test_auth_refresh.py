"""POST /api/auth/refresh — đổi refresh cookie lấy access token mới.

Chạy với DB test như các test khác (DATABASE_URL + fixtures conftest).
Endpoint sinh ra từ bug sweep A3 25/8: frontend gọi /auth/refresh nhưng route
không tồn tại (404) → tab mở quá TTL access token bị văng phiên.
"""
from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    issue_access_token,
    issue_refresh_token,
)
from app.main import app
from app.models import User


def _client(db: AsyncSession) -> httpx.AsyncClient:
    async def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


@pytest.mark.asyncio
async def test_refresh_without_cookie_401(db: AsyncSession) -> None:
    async with _client(db) as ac:
        resp = await ac.post("/api/auth/refresh")
    app.dependency_overrides.clear()
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "NO_REFRESH_TOKEN"


@pytest.mark.asyncio
async def test_refresh_with_garbage_token_401(db: AsyncSession) -> None:
    async with _client(db) as ac:
        ac.cookies.set(REFRESH_COOKIE, "not-a-jwt")
        resp = await ac.post("/api/auth/refresh")
    app.dependency_overrides.clear()
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "INVALID_REFRESH_TOKEN"


@pytest.mark.asyncio
async def test_refresh_rejects_access_token_as_refresh(
    db: AsyncSession, student: User
) -> None:
    """Access token (type=access) không được dùng thay refresh token."""
    access = issue_access_token(sub=str(student.id), role=student.role.value)
    async with _client(db) as ac:
        ac.cookies.set(REFRESH_COOKIE, access)
        resp = await ac.post("/api/auth/refresh")
    app.dependency_overrides.clear()
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "INVALID_REFRESH_TOKEN"


@pytest.mark.asyncio
async def test_refresh_ok_sets_new_cookies(db: AsyncSession, student: User) -> None:
    refresh = issue_refresh_token(sub=str(student.id))
    async with _client(db) as ac:
        ac.cookies.set(REFRESH_COOKIE, refresh)
        resp = await ac.post("/api/auth/refresh")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["status"] == "refreshed"
    set_cookie = ";".join(resp.headers.get_list("set-cookie"))
    assert ACCESS_COOKIE in set_cookie
    assert REFRESH_COOKIE in set_cookie


@pytest.mark.asyncio
async def test_refresh_inactive_user_401(db: AsyncSession, student: User) -> None:
    student.is_active = False
    await db.commit()
    refresh = issue_refresh_token(sub=str(student.id))
    async with _client(db) as ac:
        ac.cookies.set(REFRESH_COOKIE, refresh)
        resp = await ac.post("/api/auth/refresh")
    app.dependency_overrides.clear()
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "USER_INACTIVE"
