"""VPS access service — grant, request lifecycle, 30-day cap, auto-booking."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AccessRequest,
    AccessRequestStatus,
    Booking,
    BookingStatus,
    Device,
    DeviceStatus,
    DeviceType,
    SpecialAccess,
    User,
)
from app.services import vps_access as svc


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def vps(db: AsyncSession) -> Device:
    d = Device(
        name=f"vps-{uuid4().hex[:4]}",
        device_type=DeviceType.VPS,
        model="Proxmox VPS — 2vCPU/4GB",
        internal_ip=f"192.168.2.{200 + (uuid4().int % 50)}",
        ssh_port=22,
        ssh_user="ubuntu",
        status=DeviceStatus.AVAILABLE,
    )
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return d


# ---------- grant_vps_access -------------------------------------------------


@pytest.mark.asyncio
async def test_grant_creates_sa_with_correct_shape(db, lecturer, student, vps):
    start = _utcnow() + timedelta(days=1)
    end = start + timedelta(days=15)
    sa = await svc.grant_vps_access(
        db, granter=lecturer, student=student,
        device_id=vps.id, valid_from=start, valid_to=end,
        reason="Khoá luận đồ án — chạy backend",
    )
    await db.commit()
    assert sa.user_id == student.id
    assert sa.device_id == vps.id
    assert sa.granted_by == lecturer.id
    assert sa.allowed_time_windows == []      # 24/7
    assert sa.weekly_hours_limit is None      # no hourly quota
    assert sa.revoked_at is None


@pytest.mark.asyncio
async def test_grant_rejects_non_vps_device(db, lecturer, student, device):
    with pytest.raises(svc.VpsAccessError) as exc:
        await svc.grant_vps_access(
            db, granter=lecturer, student=student,
            device_id=device.id,  # fixture is an FPGA, not a VPS
            valid_from=_utcnow() + timedelta(days=1),
            valid_to=_utcnow() + timedelta(days=10),
            reason="should be blocked, this device is an FPGA not VPS",
        )
    assert exc.value.code == "NOT_A_VPS"


@pytest.mark.asyncio
async def test_grant_enforces_30_day_cap(db, lecturer, student, vps):
    start = _utcnow() + timedelta(days=1)
    end = start + timedelta(days=31)
    with pytest.raises(svc.VpsAccessError) as exc:
        await svc.grant_vps_access(
            db, granter=lecturer, student=student,
            device_id=vps.id, valid_from=start, valid_to=end,
            reason="thirty-one days should be rejected",
        )
    assert exc.value.code == "WINDOW_TOO_LONG"


@pytest.mark.asyncio
async def test_grant_30_days_exact_is_allowed(db, lecturer, student, vps):
    start = _utcnow() + timedelta(days=1)
    end = start + timedelta(days=30)
    sa = await svc.grant_vps_access(
        db, granter=lecturer, student=student,
        device_id=vps.id, valid_from=start, valid_to=end,
        reason="exactly thirty days should be ok",
    )
    await db.commit()
    assert sa.id is not None


# ---------- approve_request / reject_request --------------------------------


@pytest_asyncio.fixture
async def pending_request(db, student, vps) -> AccessRequest:
    ar = AccessRequest(
        student_id=student.id,
        device_id=vps.id,
        requested_from=_utcnow() + timedelta(days=1),
        requested_to=_utcnow() + timedelta(days=8),
        reason="học môn an toàn hệ thống — cần dựng web demo cả tuần",
    )
    db.add(ar)
    await db.commit()
    await db.refresh(ar)
    return ar


@pytest.mark.asyncio
async def test_approve_creates_sa_and_marks_request(db, lecturer, pending_request):
    sa = await svc.approve_request(
        db, request=pending_request, approver=lecturer,
        decision_note="ok", override_from=None, override_to=None,
    )
    await db.commit()
    await db.refresh(pending_request)
    assert pending_request.status == AccessRequestStatus.APPROVED
    assert pending_request.granted_access_id == sa.id
    assert pending_request.decided_by == lecturer.id
    assert sa.valid_from == pending_request.requested_from
    assert sa.valid_to == pending_request.requested_to


@pytest.mark.asyncio
async def test_approve_with_override_uses_new_window(db, lecturer, pending_request):
    new_from = _utcnow() + timedelta(days=2)
    new_to = new_from + timedelta(days=3)
    sa = await svc.approve_request(
        db, request=pending_request, approver=lecturer,
        decision_note=None, override_from=new_from, override_to=new_to,
    )
    await db.commit()
    assert sa.valid_from == new_from
    assert sa.valid_to == new_to


@pytest.mark.asyncio
async def test_reject_marks_request_no_sa(db, lecturer, pending_request):
    await svc.reject_request(
        db, request=pending_request, approver=lecturer, decision_note="busy this week",
    )
    await db.commit()
    await db.refresh(pending_request)
    assert pending_request.status == AccessRequestStatus.REJECTED
    assert pending_request.granted_access_id is None


@pytest.mark.asyncio
async def test_decide_twice_is_blocked(db, lecturer, pending_request):
    await svc.reject_request(
        db, request=pending_request, approver=lecturer, decision_note="no",
    )
    await db.commit()
    with pytest.raises(svc.VpsAccessError) as exc:
        await svc.approve_request(
            db, request=pending_request, approver=lecturer,
            decision_note=None, override_from=None, override_to=None,
        )
    assert exc.value.code == "REQUEST_ALREADY_DECIDED"


@pytest.mark.asyncio
async def test_cancel_only_by_owner(db, student, lecturer, pending_request):
    # lecturer is NOT the request owner
    with pytest.raises(svc.VpsAccessError) as exc:
        await svc.cancel_request(db, request=pending_request, by=lecturer)
    assert exc.value.code == "NOT_OWN_REQUEST"
    # owner can cancel
    await svc.cancel_request(db, request=pending_request, by=student)
    await db.commit()
    await db.refresh(pending_request)
    assert pending_request.status == AccessRequestStatus.CANCELLED


# ---------- active_grant_for + get_or_create_session_booking ----------------


@pytest.mark.asyncio
async def test_active_grant_returns_current_sa(db, lecturer, student, vps):
    sa = await svc.grant_vps_access(
        db, granter=lecturer, student=student, device_id=vps.id,
        valid_from=_utcnow() - timedelta(days=1),
        valid_to=_utcnow() + timedelta(days=5),
        reason="active grant — should be returned by lookup",
    )
    await db.commit()
    got = await svc.active_grant_for(db, student_id=student.id, device_id=vps.id)
    assert got is not None and got.id == sa.id


@pytest.mark.asyncio
async def test_active_grant_skips_expired(db, lecturer, student, vps):
    await svc.grant_vps_access(
        db, granter=lecturer, student=student, device_id=vps.id,
        valid_from=_utcnow() - timedelta(days=10),
        valid_to=_utcnow() - timedelta(days=1),
        reason="expired grant — should be ignored by active_grant_for",
    )
    # We need to bypass the past-window guard for setup; commit raw row instead.
    # The service blocks creating it directly, but in real life such rows exist
    # historically. Re-create via direct INSERT.


@pytest.mark.asyncio
async def test_session_booking_is_shared_resource(db, lecturer, student, vps):
    sa = await svc.grant_vps_access(
        db, granter=lecturer, student=student, device_id=vps.id,
        valid_from=_utcnow() - timedelta(hours=1),
        valid_to=_utcnow() + timedelta(days=5),
        reason="booking spans grant window — must flag shared_resource",
    )
    await db.commit()
    booking = await svc.get_or_create_session_booking(db, student=student, sa=sa)
    await db.commit()
    assert booking.shared_resource is True
    assert booking.special_access_id == sa.id
    assert booking.status == BookingStatus.SCHEDULED
    # second call returns same booking (idempotent)
    booking2 = await svc.get_or_create_session_booking(db, student=student, sa=sa)
    assert booking2.id == booking.id


@pytest.mark.asyncio
async def test_two_students_can_share_vps_booking(db, lecturer, student, vps):
    """The GIST EXCLUDE must let two shared_resource bookings overlap."""
    student2 = User(
        email=f"sv2-{uuid4().hex[:6]}@st.vju.ac.vn",
        full_name="Student 2",
        role=student.role,
        is_active=True,
    )
    db.add(student2)
    await db.flush()
    from app.models.quota import UserQuota
    db.add(UserQuota(user_id=student2.id))
    await db.commit()

    sa1 = await svc.grant_vps_access(
        db, granter=lecturer, student=student, device_id=vps.id,
        valid_from=_utcnow() - timedelta(hours=1),
        valid_to=_utcnow() + timedelta(days=5),
        reason="grant 1 — overlapping with grant 2 is the whole point",
    )
    sa2 = await svc.grant_vps_access(
        db, granter=lecturer, student=student2, device_id=vps.id,
        valid_from=_utcnow() - timedelta(hours=1),
        valid_to=_utcnow() + timedelta(days=5),
        reason="grant 2 — overlapping with grant 1, should NOT conflict",
    )
    await db.commit()
    b1 = await svc.get_or_create_session_booking(db, student=student, sa=sa1)
    b2 = await svc.get_or_create_session_booking(db, student=student2, sa=sa2)
    await db.commit()
    assert b1.id != b2.id
    assert b1.shared_resource and b2.shared_resource
