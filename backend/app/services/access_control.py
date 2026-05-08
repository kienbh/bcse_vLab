"""Canonical access control logic — verbatim from docs/10-access-control.md.

Two paths to grant device access:
  1. Class path: user enrolled in class C, class C has active assignment for device D
  2. Special access path: lecturer granted personal override

The function is fail-fast and orders cheap checks (memory) before DB hits.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import (
    Booking,
    BookingStatus,
    Class,
    ClassDeviceAssignment,
    Device,
    DeviceStatus,
    Enrollment,
    SpecialAccess,
)


@dataclass
class AccessDecision:
    allowed: bool
    reason: str
    details: dict[str, Any] = field(default_factory=dict)
    granted_via: str | None = None
    class_id: UUID | None = None
    special_access_id: UUID | None = None
    assignment_id: UUID | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_within_time_windows(
    start: datetime, end: datetime, windows: list[dict] | None
) -> bool:
    """
    windows = [{"day_of_week":1..7, "start":"08:00", "end":"22:00"}]
    Slot must lie wholly within ONE single-day window.
    Empty windows = 24/7 allowed.
    """
    if not windows:
        return True
    if start.date() != end.date():
        return False
    day = start.isoweekday()
    for w in windows:
        if int(w.get("day_of_week", 0)) != day:
            continue
        try:
            win_start = time.fromisoformat(w["start"])
            win_end = time.fromisoformat(w["end"])
        except (KeyError, ValueError):
            continue
        if start.time() >= win_start and end.time() <= win_end:
            return True
    return False


def _hours(td: timedelta) -> float:
    return td.total_seconds() / 3600.0


async def _hours_used_this_week(
    db: AsyncSession, *, user_id: UUID, device_id: UUID, ref: datetime
) -> float:
    """Sum of booking durations (scheduled+active+completed) within current ISO week."""
    # ISO week: Monday 00:00 — Sunday 23:59, in user's local TZ would be ideal,
    # but DB is UTC; close enough for quota math. Tests can pin reference.
    weekday = ref.isoweekday()  # 1=Mon
    week_start = (ref - timedelta(days=weekday - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_end = week_start + timedelta(days=7)

    result = await db.execute(
        select(
            func.coalesce(
                func.sum(
                    func.extract("epoch", Booking.end_time - Booking.start_time)
                ),
                0,
            )
        ).where(
            Booking.user_id == user_id,
            Booking.device_id == device_id,
            Booking.start_time >= week_start,
            Booking.start_time < week_end,
            Booking.status.in_(
                [
                    BookingStatus.SCHEDULED,
                    BookingStatus.ACTIVE,
                    BookingStatus.COMPLETED,
                ]
            ),
        )
    )
    seconds = result.scalar_one() or 0
    return float(seconds) / 3600.0


async def _concurrent_count(
    db: AsyncSession, *, user_id: UUID, device_id: UUID
) -> int:
    """Count of currently-scheduled/active bookings for this user-device pair."""
    result = await db.execute(
        select(func.count(Booking.id)).where(
            Booking.user_id == user_id,
            Booking.device_id == device_id,
            Booking.status.in_([BookingStatus.SCHEDULED, BookingStatus.ACTIVE]),
        )
    )
    return int(result.scalar_one() or 0)


async def _global_user_concurrent(db: AsyncSession, *, user_id: UUID) -> int:
    result = await db.execute(
        select(func.count(Booking.id)).where(
            Booking.user_id == user_id,
            Booking.status.in_([BookingStatus.SCHEDULED, BookingStatus.ACTIVE]),
        )
    )
    return int(result.scalar_one() or 0)


async def _global_user_weekly_hours(
    db: AsyncSession, *, user_id: UUID, ref: datetime
) -> float:
    weekday = ref.isoweekday()
    week_start = (ref - timedelta(days=weekday - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_end = week_start + timedelta(days=7)
    result = await db.execute(
        select(
            func.coalesce(
                func.sum(
                    func.extract("epoch", Booking.end_time - Booking.start_time)
                ),
                0,
            )
        ).where(
            Booking.user_id == user_id,
            Booking.start_time >= week_start,
            Booking.start_time < week_end,
            Booking.status.in_(
                [
                    BookingStatus.SCHEDULED,
                    BookingStatus.ACTIVE,
                    BookingStatus.COMPLETED,
                ]
            ),
        )
    )
    return float(result.scalar_one() or 0) / 3600.0


async def _has_overlap(
    db: AsyncSession, *, device_id: UUID, start: datetime, end: datetime
) -> bool:
    """Check via tstzrange overlap on existing scheduled/active bookings."""
    sql = text(
        """
        SELECT 1 FROM bookings
        WHERE device_id = :device_id
          AND status IN ('scheduled','active')
          AND tstzrange(start_time, end_time, '[)') && tstzrange(:s, :e, '[)')
        LIMIT 1
        """
    )
    res = await db.execute(sql, {"device_id": device_id, "s": start, "e": end})
    return res.first() is not None


async def _check_via_class(
    db: AsyncSession,
    *,
    user_id: UUID,
    device_id: UUID,
    start_time: datetime,
    end_time: datetime,
) -> AccessDecision:
    # 2a. find active enrollment + active class_device_assignment covering window
    result = await db.execute(
        select(ClassDeviceAssignment, Class)
        .join(Class, Class.id == ClassDeviceAssignment.class_id)
        .join(Enrollment, Enrollment.class_id == Class.id)
        .where(
            Enrollment.user_id == user_id,
            Enrollment.is_active.is_(True),
            ClassDeviceAssignment.device_id == device_id,
            ClassDeviceAssignment.revoked_at.is_(None),
            ClassDeviceAssignment.valid_from <= start_time,
            ClassDeviceAssignment.valid_to >= end_time,
        )
        .order_by(ClassDeviceAssignment.granted_at.desc())
        .limit(1)
    )
    row = result.first()
    if row is None:
        return AccessDecision(False, "NO_CLASS_ASSIGNMENT")
    assignment, class_ = row

    # 2b. time-window check
    if not _is_within_time_windows(start_time, end_time, assignment.allowed_time_windows):
        return AccessDecision(
            False,
            "OUTSIDE_TIME_WINDOW",
            {"windows": assignment.allowed_time_windows},
            class_id=class_.id,
            assignment_id=assignment.id,
        )

    # 2c. weekly hours
    hours_used = await _hours_used_this_week(
        db, user_id=user_id, device_id=device_id, ref=start_time
    )
    requested = _hours(end_time - start_time)
    if hours_used + requested > assignment.per_student_weekly_hours:
        return AccessDecision(
            False,
            "WEEKLY_QUOTA_EXCEEDED",
            {
                "limit": assignment.per_student_weekly_hours,
                "used": hours_used,
                "requested": requested,
            },
            class_id=class_.id,
            assignment_id=assignment.id,
        )

    # 2d. concurrent
    concurrent = await _concurrent_count(db, user_id=user_id, device_id=device_id)
    if concurrent >= assignment.per_student_max_concurrent:
        return AccessDecision(
            False,
            "CONCURRENT_LIMIT_EXCEEDED",
            {"limit": assignment.per_student_max_concurrent, "current": concurrent},
            class_id=class_.id,
            assignment_id=assignment.id,
        )

    # 2e. advance days
    days_ahead = (start_time - _utcnow()).total_seconds() / 86400
    if days_ahead > assignment.per_student_max_advance_days:
        return AccessDecision(
            False,
            "TOO_FAR_IN_ADVANCE",
            {"max_days": assignment.per_student_max_advance_days, "requested_days": days_ahead},
            class_id=class_.id,
            assignment_id=assignment.id,
        )

    return AccessDecision(
        True, "OK", granted_via="class", class_id=class_.id, assignment_id=assignment.id
    )


async def _check_via_special_access(
    db: AsyncSession,
    *,
    user_id: UUID,
    device_id: UUID,
    start_time: datetime,
    end_time: datetime,
) -> AccessDecision:
    result = await db.execute(
        select(SpecialAccess)
        .where(
            SpecialAccess.user_id == user_id,
            SpecialAccess.device_id == device_id,
            SpecialAccess.revoked_at.is_(None),
            SpecialAccess.valid_from <= start_time,
            SpecialAccess.valid_to >= end_time,
        )
        .order_by(SpecialAccess.granted_at.desc())
        .limit(1)
    )
    sa = result.scalar_one_or_none()
    if sa is None:
        return AccessDecision(False, "NO_SPECIAL_ACCESS")

    if not _is_within_time_windows(start_time, end_time, sa.allowed_time_windows):
        return AccessDecision(
            False,
            "OUTSIDE_TIME_WINDOW",
            {"windows": sa.allowed_time_windows},
            special_access_id=sa.id,
        )

    if sa.weekly_hours_limit is not None:
        used = await _hours_used_this_week(
            db, user_id=user_id, device_id=device_id, ref=start_time
        )
        requested = _hours(end_time - start_time)
        if used + requested > sa.weekly_hours_limit:
            return AccessDecision(
                False,
                "WEEKLY_QUOTA_EXCEEDED",
                {"limit": sa.weekly_hours_limit, "used": used, "requested": requested},
                special_access_id=sa.id,
            )

    return AccessDecision(
        True, "OK", granted_via="special_access", special_access_id=sa.id
    )


async def can_user_book_device(
    db: AsyncSession,
    *,
    user_id: UUID,
    device_id: UUID,
    start_time: datetime,
    end_time: datetime,
) -> AccessDecision:
    settings = get_settings()
    # 0. Sanity
    if end_time <= start_time:
        return AccessDecision(False, "INVALID_TIME_RANGE")
    if start_time < _utcnow():
        return AccessDecision(False, "PAST_TIME")
    duration = end_time - start_time
    max_h = settings.BOOKING_MAX_DURATION_HOURS
    if _hours(duration) > max_h:
        return AccessDecision(
            False,
            "DURATION_EXCEEDED",
            {"max_hours": max_h, "requested_hours": _hours(duration)},
        )

    # 1. Device must exist + be bookable
    device = (
        await db.execute(select(Device).where(Device.id == device_id))
    ).scalar_one_or_none()
    if device is None:
        return AccessDecision(False, "DEVICE_NOT_FOUND")
    if device.status in (DeviceStatus.MAINTENANCE, DeviceStatus.OFFLINE):
        return AccessDecision(False, "DEVICE_NOT_AVAILABLE", {"status": device.status.value})

    # 2 + 3. Try class path then special access
    cls = await _check_via_class(
        db, user_id=user_id, device_id=device_id, start_time=start_time, end_time=end_time
    )
    if cls.allowed:
        decision = cls
    else:
        sa = await _check_via_special_access(
            db, user_id=user_id, device_id=device_id, start_time=start_time, end_time=end_time
        )
        if sa.allowed:
            decision = sa
        else:
            # both denied — surface the most specific reason
            if cls.reason == "NO_CLASS_ASSIGNMENT" and sa.reason == "NO_SPECIAL_ACCESS":
                return AccessDecision(
                    False,
                    "ACCESS_DENIED",
                    {"hint": "Liên hệ giảng viên để được cấp quyền cho thiết bị này."},
                )
            return cls if cls.reason != "NO_CLASS_ASSIGNMENT" else sa

    # 4. Global per-user quota (independent of class/special)
    g_concurrent = await _global_user_concurrent(db, user_id=user_id)
    if g_concurrent >= settings.BOOKING_DEFAULT_MAX_CONCURRENT:
        return AccessDecision(
            False,
            "GLOBAL_CONCURRENT_LIMIT",
            {"limit": settings.BOOKING_DEFAULT_MAX_CONCURRENT, "current": g_concurrent},
        )
    g_hours = await _global_user_weekly_hours(db, user_id=user_id, ref=start_time)
    requested_h = _hours(duration)
    if g_hours + requested_h > settings.BOOKING_DEFAULT_QUOTA_HOURS_PER_WEEK:
        return AccessDecision(
            False,
            "GLOBAL_WEEKLY_HOURS_EXCEEDED",
            {
                "limit": settings.BOOKING_DEFAULT_QUOTA_HOURS_PER_WEEK,
                "used": g_hours,
                "requested": requested_h,
            },
        )

    # 5. Conflict check (app-layer; GIST EXCLUDE is the DB-layer last line)
    if await _has_overlap(db, device_id=device_id, start=start_time, end=end_time):
        return AccessDecision(False, "BOOKING_CONFLICT")

    return decision
