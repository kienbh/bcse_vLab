"""VPS access — grant + request decision + auto-booking for gateway mint.

Why a separate service:
  - Generic SpecialAccess.grant in `classes.py` doesn't enforce VPS-specific
    rules (30-day cap, device must be VPS).
  - The connect flow auto-creates a Booking spanning the active SA window so
    the existing M5.8 gateway pipeline (`POST /bookings/{id}/access`) works
    unchanged. That booking bypasses class/quota checks — its authorisation
    IS the SpecialAccess.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AccessRequest,
    AccessRequestStatus,
    Booking,
    BookingGrantedVia,
    BookingStatus,
    Device,
    DeviceType,
    SpecialAccess,
    User,
    UserRole,
)


MAX_GRANT_DAYS = 30
# Reserved (ESAS-BCSE) devices are handed to an external team for long-running
# development — allow a much longer grant so the admin grants once and the
# minted gateway password stays valid for the whole period.
RESERVED_GRANT_MAX_DAYS = 365
DEFAULT_GRANT_REASON = "Approved via student request"


class VpsAccessError(Exception):
    """Raised for any service-level business-rule failure.

    Routes catch and translate to HTTPException; keeping the service free of
    HTTP coupling makes it reusable from cron jobs / CLI / tests.
    """

    def __init__(self, code: str, message: str = "", **details):
        super().__init__(message or code)
        self.code = code
        self.details = details


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_window(start: datetime, end: datetime, *, max_days: int = MAX_GRANT_DAYS) -> None:
    if end <= start:
        raise VpsAccessError("INVALID_TIME_RANGE", "end must be after start")
    if (end - start) > timedelta(days=max_days):
        raise VpsAccessError(
            "WINDOW_TOO_LONG",
            f"Khoảng truy cập tối đa {max_days} ngày",
            max_days=max_days,
        )
    if end < _utcnow():
        raise VpsAccessError("PAST_WINDOW", "Khoảng truy cập đã hết hạn")


async def _ensure_vps(db: AsyncSession, device_id: UUID) -> Device:
    device = (
        await db.execute(select(Device).where(Device.id == device_id))
    ).scalar_one_or_none()
    if device is None:
        raise VpsAccessError("DEVICE_NOT_FOUND")
    if device.device_type != DeviceType.VPS:
        raise VpsAccessError(
            "NOT_A_VPS",
            "Cấp quyền truy cập dài ngày chỉ áp dụng cho VPS",
            device_type=device.device_type.value,
        )
    return device


async def grant_vps_access(
    db: AsyncSession,
    *,
    granter: User,
    student: User,
    device_id: UUID,
    valid_from: datetime,
    valid_to: datetime,
    reason: str,
) -> SpecialAccess:
    """Direct grant by lecturer/admin. No prior request needed.

    Reserved (ESAS-BCSE-managed) devices are admin-only: a lecturer cannot
    grant access to them — only an admin can.
    """
    device = await _ensure_vps(db, device_id)
    if device.reserved and granter.role != UserRole.ADMIN:
        raise VpsAccessError(
            "RESERVED_ADMIN_ONLY",
            f"VPS {device.name} do {device.managed_by or 'ESAS-BCSE'} quản lý — "
            "chỉ admin mới cấp quyền truy cập được.",
            managed_by=device.managed_by,
        )
    max_days = RESERVED_GRANT_MAX_DAYS if device.reserved else MAX_GRANT_DAYS
    _ensure_window(valid_from, valid_to, max_days=max_days)

    sa = SpecialAccess(
        user_id=student.id,
        device_id=device_id,
        valid_from=valid_from,
        valid_to=valid_to,
        allowed_time_windows=[],  # VPS = 24/7
        weekly_hours_limit=None,  # no hourly quota for long-running VPS work
        reason=reason,
        granted_by=granter.id,
    )
    db.add(sa)
    await db.flush()
    return sa


async def approve_request(
    db: AsyncSession,
    *,
    request: AccessRequest,
    approver: User,
    decision_note: str | None,
    override_from: datetime | None,
    override_to: datetime | None,
) -> SpecialAccess:
    if request.status != AccessRequestStatus.PENDING:
        raise VpsAccessError("REQUEST_ALREADY_DECIDED", status=request.status.value)

    start = override_from or request.requested_from
    end = override_to or request.requested_to
    student = (
        await db.execute(select(User).where(User.id == request.student_id))
    ).scalar_one_or_none()
    if student is None:
        raise VpsAccessError("STUDENT_GONE")

    sa = await grant_vps_access(
        db,
        granter=approver,
        student=student,
        device_id=request.device_id,
        valid_from=start,
        valid_to=end,
        reason=f"Approved request: {request.reason[:300]}",
    )
    request.status = AccessRequestStatus.APPROVED
    request.decided_by = approver.id
    request.decided_at = _utcnow()
    request.decision_note = decision_note
    request.granted_access_id = sa.id
    return sa


async def reject_request(
    db: AsyncSession,
    *,
    request: AccessRequest,
    approver: User,
    decision_note: str | None,
) -> None:
    if request.status != AccessRequestStatus.PENDING:
        raise VpsAccessError("REQUEST_ALREADY_DECIDED", status=request.status.value)
    request.status = AccessRequestStatus.REJECTED
    request.decided_by = approver.id
    request.decided_at = _utcnow()
    request.decision_note = decision_note


async def cancel_request(
    db: AsyncSession, *, request: AccessRequest, by: User
) -> None:
    if request.status != AccessRequestStatus.PENDING:
        raise VpsAccessError("REQUEST_ALREADY_DECIDED", status=request.status.value)
    if request.student_id != by.id:
        raise VpsAccessError("NOT_OWN_REQUEST")
    request.status = AccessRequestStatus.CANCELLED
    request.decided_at = _utcnow()


async def active_grant_for(
    db: AsyncSession, *, student_id: UUID, device_id: UUID
) -> SpecialAccess | None:
    """Return the SpecialAccess covering now, if any."""
    now = _utcnow()
    row = await db.execute(
        select(SpecialAccess)
        .where(
            SpecialAccess.user_id == student_id,
            SpecialAccess.device_id == device_id,
            SpecialAccess.revoked_at.is_(None),
            SpecialAccess.valid_from <= now,
            SpecialAccess.valid_to >= now,
        )
        .order_by(SpecialAccess.granted_at.desc())
        .limit(1)
    )
    return row.scalar_one_or_none()


async def get_or_create_session_booking(
    db: AsyncSession, *, student: User, sa: SpecialAccess
) -> Booking:
    """Get (or create) a Booking spanning the SA window for gateway minting.

    One booking per (user, device, active SA). Reused for the entire SA
    period so the student gets ONE ssh command for the full 30 days.
    """
    now = _utcnow()
    existing = (
        await db.execute(
            select(Booking)
            .where(
                Booking.user_id == student.id,
                Booking.device_id == sa.device_id,
                Booking.special_access_id == sa.id,
                Booking.status.in_([BookingStatus.SCHEDULED, BookingStatus.ACTIVE]),
                Booking.end_time > now,
            )
            .order_by(Booking.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    booking = Booking(
        user_id=student.id,
        device_id=sa.device_id,
        granted_via=BookingGrantedVia.SPECIAL_ACCESS,
        special_access_id=sa.id,
        start_time=max(sa.valid_from, now),
        end_time=sa.valid_to,
        status=BookingStatus.SCHEDULED,
        shared_resource=True,
        notes="VPS long-running access — auto-created from special access",
    )
    db.add(booking)
    await db.flush()
    return booking
