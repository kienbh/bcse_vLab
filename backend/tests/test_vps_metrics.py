"""VPS-GPU metrics service + endpoints (M6.5).

Covers:
  - stdout parsers for `nvidia-smi`, `df`, and `nvidia-smi --query-compute-apps`
  - mock-mode fast path (no SSH required)
  - in-process cache hit/miss collapses concurrent callers to one probe
  - bulk endpoint filters by tier
  - external-user access scoping
"""
from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app as fastapi_app
from app.models import Device, DeviceStatus, DeviceType, SpecialAccess, User, UserRole
from app.models.quota import UserQuota
from app.services import vps_metrics as svc


@pytest_asyncio.fixture
async def gpu_vps(db: AsyncSession) -> Device:
    d = Device(
        name=f"sv-gpu-{uuid4().hex[:3]}",
        device_type=DeviceType.VPS,
        model="Proxmox VPS — 8vCPU/64GB · RTX 6000 Ada 48GB",
        internal_ip=f"192.168.2.{100 + (uuid4().int % 50)}",
        ssh_port=22,
        ssh_user="ubuntu",
        status=DeviceStatus.AVAILABLE,
        capabilities={"tier": "gpu", "gpu": "RTX 6000 Ada", "vram_gb": 48},
    )
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return d


@pytest_asyncio.fixture
async def cpu_vps(db: AsyncSession) -> Device:
    d = Device(
        name=f"sv-cpu-{uuid4().hex[:3]}",
        device_type=DeviceType.VPS,
        model="Proxmox VPS — 2vCPU/4GB",
        internal_ip=f"192.168.2.{200 + (uuid4().int % 50)}",
        ssh_port=22,
        ssh_user="ubuntu",
        status=DeviceStatus.AVAILABLE,
        capabilities={"tier": "thap"},
    )
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return d


# ---------- parsers ----------------------------------------------------------


def test_parse_gpu_one_line() -> None:
    raw = "NVIDIA RTX 6000 Ada, 32, 18432, 49140, 56"
    g = svc._parse_gpu(raw)
    assert g is not None
    assert g.name == "NVIDIA RTX 6000 Ada"
    assert g.util_pct == 32
    assert g.vram_used_mb == 18432
    assert g.vram_total_mb == 49140
    assert g.temp_c == 56


def test_parse_gpu_empty() -> None:
    assert svc._parse_gpu("") is None
    assert svc._parse_gpu("   \n") is None


def test_parse_gpu_garbage_returns_none() -> None:
    assert svc._parse_gpu("not, enough") is None
    assert svc._parse_gpu("a, b, c, d, e") is None  # ints don't parse


def test_parse_disk_typical() -> None:
    raw = "120034598912 536870912000 /home"
    d = svc._parse_disk(raw)
    assert d is not None
    assert d.free_bytes == 120034598912
    assert d.total_bytes == 536870912000
    assert d.used_bytes == 536870912000 - 120034598912
    assert d.mount == "/home"


def test_parse_disk_empty() -> None:
    assert svc._parse_disk("") is None
    assert svc._parse_disk("only one field") is None


def test_parse_processes_mixed_rows() -> None:
    raw = (
        "1234, 4096, python3\n"
        "5678, 12288, jupyter-lab\n"
        "garbage line\n"
        ", , noisy\n"
    )
    out = svc._parse_processes(raw)
    assert len(out) == 2
    assert out[0].pid == 1234
    assert out[0].vram_mb == 4096
    assert out[1].name == "jupyter-lab"


def test_parse_processes_empty() -> None:
    assert svc._parse_processes("") == []


# ---------- mock-mode service path ------------------------------------------


@pytest.mark.asyncio
async def test_mock_snapshot_is_self_consistent() -> None:
    os.environ["MOCK_SSH_DEVICES"] = "true"
    # Clear cache between tests
    svc._memory_cache.clear()
    snap = await svc.get_metrics(
        device_id=uuid4(), internal_ip="10.0.0.1", ssh_port=22, ssh_user="x"
    )
    assert snap.gpu is not None
    assert 0 <= snap.gpu.util_pct <= 100
    assert snap.gpu.vram_used_mb <= snap.gpu.vram_total_mb
    assert snap.disk is not None
    assert snap.disk.free_bytes <= snap.disk.total_bytes
    assert snap.cached is False


@pytest.mark.asyncio
async def test_cache_collapses_concurrent_misses() -> None:
    """10 concurrent callers for the same device → 1 underlying snapshot.

    Verified by checking they all return the same `fetched_at` timestamp,
    which is captured per-snapshot and would differ if each call probed
    independently.
    """
    os.environ["MOCK_SSH_DEVICES"] = "true"
    svc._memory_cache.clear()
    svc._locks.clear()
    did = uuid4()
    snaps = await asyncio.gather(*[
        svc.get_metrics(device_id=did, internal_ip="10.0.0.2", ssh_port=22, ssh_user="x")
        for _ in range(10)
    ])
    timestamps = {s.fetched_at for s in snaps}
    assert len(timestamps) == 1
    # First through the lock is uncached; the other 9 ride the cache. We
    # can't assert exact ordering since asyncio.gather doesn't guarantee
    # it, but the cached-flag mix should be (1 false, 9 true).
    cached_flags = [s.cached for s in snaps]
    assert cached_flags.count(False) == 1
    assert cached_flags.count(True) == 9


# ---------- endpoints -------------------------------------------------------


async def _auth_client(user: User) -> AsyncClient:
    """ASGI client with the JWT access cookie pre-set for `user`."""
    from app.core.security import ACCESS_COOKIE, issue_access_token
    token = issue_access_token(sub=str(user.id), role=user.role.value)
    transport = ASGITransport(app=fastapi_app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.cookies.set(ACCESS_COOKIE, token)
    return client


@pytest_asyncio.fixture
async def extern(db: AsyncSession) -> User:
    u = User(
        email=f"ext-{uuid4().hex[:6]}@esas.example",
        full_name="External",
        role=UserRole.STUDENT,
        is_active=True,
        external=True,
    )
    db.add(u)
    await db.flush()
    db.add(UserQuota(user_id=u.id))
    await db.commit()
    await db.refresh(u)
    return u


@pytest.mark.asyncio
async def test_bulk_returns_only_gpu_tier(db, student, gpu_vps, cpu_vps) -> None:
    os.environ["MOCK_SSH_DEVICES"] = "true"
    svc._memory_cache.clear()
    async with await _auth_client(student) as c:
        r = await c.get("/api/vps-metrics?tier=gpu")
    assert r.status_code == 200
    body = r.json()
    assert body["tier"] == "gpu"
    ids = [m["device_id"] for m in body["metrics"]]
    assert str(gpu_vps.id) in ids
    assert str(cpu_vps.id) not in ids


@pytest.mark.asyncio
async def test_single_device_metrics_404_unknown(db, student) -> None:
    os.environ["MOCK_SSH_DEVICES"] = "true"
    async with await _auth_client(student) as c:
        r = await c.get(f"/api/vps-metrics/{uuid4()}")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "DEVICE_NOT_FOUND"


@pytest.mark.asyncio
async def test_single_device_metrics_400_non_vps(db, student, device) -> None:
    """Hitting metrics on an FPGA → 400, not a confusing SSH attempt."""
    os.environ["MOCK_SSH_DEVICES"] = "true"
    async with await _auth_client(student) as c:
        r = await c.get(f"/api/vps-metrics/{device.id}")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "NOT_A_VPS"


@pytest.mark.asyncio
async def test_external_user_blocked_without_grant(db, extern, gpu_vps) -> None:
    os.environ["MOCK_SSH_DEVICES"] = "true"
    async with await _auth_client(extern) as c:
        r = await c.get(f"/api/vps-metrics/{gpu_vps.id}")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "ACCESS_DENIED"


@pytest.mark.asyncio
async def test_external_user_sees_only_granted_in_bulk(db, extern, gpu_vps) -> None:
    """External + no grant → empty list, NOT every GPU box."""
    os.environ["MOCK_SSH_DEVICES"] = "true"
    svc._memory_cache.clear()
    async with await _auth_client(extern) as c:
        r = await c.get("/api/vps-metrics?tier=gpu")
    assert r.status_code == 200
    assert r.json()["metrics"] == []


@pytest.mark.asyncio
async def test_external_user_with_grant_can_read(db, extern, gpu_vps, admin) -> None:
    now = datetime.now(UTC)
    db.add(SpecialAccess(
        user_id=extern.id,
        device_id=gpu_vps.id,
        granted_by=admin.id,
        valid_from=now - timedelta(days=1),
        valid_to=now + timedelta(days=30),
        allowed_time_windows=[],
        reason="ESAS task",
    ))
    await db.commit()

    os.environ["MOCK_SSH_DEVICES"] = "true"
    svc._memory_cache.clear()
    async with await _auth_client(extern) as c:
        r = await c.get(f"/api/vps-metrics/{gpu_vps.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["device_id"] == str(gpu_vps.id)
    assert body["gpu"] is not None
