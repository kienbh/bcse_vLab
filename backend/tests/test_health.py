"""Smoke tests for health endpoints."""
import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_health_returns_ok() -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "vju-lab-portal-api"
    assert "version" in body


@pytest.mark.asyncio
async def test_ready_returns_ready() -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_root_lists_docs() -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "VJU Hardware Lab Portal API"
    assert body["docs"] == "/api/docs"
