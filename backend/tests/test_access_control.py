"""10 mandatory test cases for can_user_book_device — per docs/10-access-control.md."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Booking,
    BookingGrantedVia,
    BookingStatus,
    Class,
    ClassDeviceAssignment,
    Device,
    Enrollment,
    SpecialAccess,
    User,
)
from app.services.access_control import can_user_book_device


def _slot(hours_offset: int = 24, duration_h: float = 2) -> tuple[datetime, datetime]:
    start = datetime.now(timezone.utc) + timedelta(hours=hours_offset)
    return start, start + timedelta(hours=duration_h)


@pytest.mark.asyncio
async def test_class_path_happy(
    db: AsyncSession, student: User, device: Device, class_with_assignment
) -> None:
    s, e = _slot()
    d = await can_user_book_device(db, user_id=student.id, device_id=device.id, start_time=s, end_time=e)
    assert d.allowed is True
    assert d.reason == "OK"
    assert d.granted_via == "class"
    assert d.class_id is not None


@pytest.mark.asyncio
async def test_no_class_no_special_denies(
    db: AsyncSession, student: User, device: Device
) -> None:
    s, e = _slot()
    d = await can_user_book_device(db, user_id=student.id, device_id=device.id, start_time=s, end_time=e)
    assert d.allowed is False
    assert d.reason == "ACCESS_DENIED"


@pytest.mark.asyncio
async def test_class_but_no_assignment_denies(
    db: AsyncSession, student: User, device: Device, lecturer: User
) -> None:
    cls = Class(
        code=f"C-{uuid4().hex[:4]}",
        name="No-assign class",
        semester="2026-1",
        lecturer_id=lecturer.id,
        starts_at=datetime.now(timezone.utc) - timedelta(days=1),
        ends_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(cls)
    await db.flush()
    db.add(Enrollment(class_id=cls.id, user_id=student.id, enrolled_by=lecturer.id))
    await db.commit()

    s, e = _slot()
    d = await can_user_book_device(db, user_id=student.id, device_id=device.id, start_time=s, end_time=e)
    assert d.allowed is False
    assert d.reason == "ACCESS_DENIED"


@pytest.mark.asyncio
async def test_outside_time_window_denies(
    db: AsyncSession, student: User, device: Device, class_with_assignment
) -> None:
    cls, enr, cda = class_with_assignment
    # Restrict to Monday 08:00-22:00 only
    cda.allowed_time_windows = [{"day_of_week": 1, "start": "08:00", "end": "22:00"}]
    await db.commit()

    # Pick a slot that's NOT Monday 08-22
    # Find next Tuesday
    now = datetime.now(timezone.utc)
    days_to_tue = (2 - now.isoweekday()) % 7 or 7
    tue = (now + timedelta(days=days_to_tue)).replace(hour=10, minute=0, second=0, microsecond=0)
    e = tue + timedelta(hours=2)
    d = await can_user_book_device(db, user_id=student.id, device_id=device.id, start_time=tue, end_time=e)
    assert d.allowed is False
    assert d.reason == "OUTSIDE_TIME_WINDOW"


@pytest.mark.asyncio
async def test_class_quota_exceeded(
    db: AsyncSession, student: User, device: Device, class_with_assignment
) -> None:
    cls, enr, cda = class_with_assignment
    # cda has 5h/week; insert a 4h-completed booking earlier in week
    now = datetime.now(timezone.utc)
    # Use COMPLETED status so it counts toward quota but doesn't conflict
    week_start = (now - timedelta(days=now.isoweekday() - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    db.add(
        Booking(
            user_id=student.id,
            device_id=device.id,
            granted_via=BookingGrantedVia.CLASS,
            class_id=cls.id,
            start_time=week_start + timedelta(hours=1),
            end_time=week_start + timedelta(hours=5),
            status=BookingStatus.COMPLETED,
        )
    )
    await db.commit()

    # Try to add 2h more — would total 6h > 5h limit
    s, e = _slot(hours_offset=24, duration_h=2)
    d = await can_user_book_device(db, user_id=student.id, device_id=device.id, start_time=s, end_time=e)
    assert d.allowed is False
    assert d.reason == "WEEKLY_QUOTA_EXCEEDED"


@pytest.mark.asyncio
async def test_special_access_happy(
    db: AsyncSession, student: User, device: Device, lecturer: User
) -> None:
    sa = SpecialAccess(
        user_id=student.id,
        device_id=device.id,
        valid_from=datetime.now(timezone.utc) - timedelta(days=1),
        valid_to=datetime.now(timezone.utc) + timedelta(days=30),
        allowed_time_windows=[],
        weekly_hours_limit=None,
        reason="Khoá luận",
        granted_by=lecturer.id,
    )
    db.add(sa)
    await db.commit()

    s, e = _slot()
    d = await can_user_book_device(db, user_id=student.id, device_id=device.id, start_time=s, end_time=e)
    assert d.allowed is True
    assert d.granted_via == "special_access"
    assert d.special_access_id == sa.id


@pytest.mark.asyncio
async def test_special_access_expired(
    db: AsyncSession, student: User, device: Device, lecturer: User
) -> None:
    sa = SpecialAccess(
        user_id=student.id,
        device_id=device.id,
        valid_from=datetime.now(timezone.utc) - timedelta(days=30),
        valid_to=datetime.now(timezone.utc) - timedelta(days=1),  # expired
        allowed_time_windows=[],
        reason="Khoá luận đã hết hạn",
        granted_by=lecturer.id,
    )
    db.add(sa)
    await db.commit()

    s, e = _slot()
    d = await can_user_book_device(db, user_id=student.id, device_id=device.id, start_time=s, end_time=e)
    assert d.allowed is False
    assert d.reason == "ACCESS_DENIED"


@pytest.mark.asyncio
async def test_class_assignment_revoked(
    db: AsyncSession, student: User, device: Device, class_with_assignment
) -> None:
    cls, enr, cda = class_with_assignment
    cda.revoked_at = datetime.now(timezone.utc)
    cda.revoked_by = cls.lecturer_id
    await db.commit()

    s, e = _slot()
    d = await can_user_book_device(db, user_id=student.id, device_id=device.id, start_time=s, end_time=e)
    assert d.allowed is False
    assert d.reason == "ACCESS_DENIED"


@pytest.mark.asyncio
async def test_booking_conflict_detected(
    db: AsyncSession, student: User, device: Device, class_with_assignment
) -> None:
    cls, enr, cda = class_with_assignment
    s, e = _slot()
    # Insert an overlapping booking for someone else (or same user — overlap is per device)
    db.add(
        Booking(
            user_id=student.id,
            device_id=device.id,
            granted_via=BookingGrantedVia.CLASS,
            class_id=cls.id,
            start_time=s,
            end_time=e,
            status=BookingStatus.SCHEDULED,
        )
    )
    await db.commit()

    # Try to book the SAME slot
    d = await can_user_book_device(db, user_id=student.id, device_id=device.id, start_time=s, end_time=e)
    # First-line guard fires
    assert d.allowed is False
    assert d.reason in ("BOOKING_CONFLICT", "CONCURRENT_LIMIT_EXCEEDED")


@pytest.mark.asyncio
async def test_invalid_inputs(
    db: AsyncSession, student: User, device: Device
) -> None:
    now = datetime.now(timezone.utc)
    # end <= start
    d = await can_user_book_device(
        db, user_id=student.id, device_id=device.id, start_time=now + timedelta(hours=2), end_time=now
    )
    assert d.allowed is False and d.reason == "INVALID_TIME_RANGE"

    # past
    d = await can_user_book_device(
        db, user_id=student.id, device_id=device.id,
        start_time=now - timedelta(hours=2), end_time=now - timedelta(hours=1),
    )
    assert d.allowed is False and d.reason == "PAST_TIME"

    # > 8h
    d = await can_user_book_device(
        db, user_id=student.id, device_id=device.id,
        start_time=now + timedelta(hours=24), end_time=now + timedelta(hours=24 + 9),
    )
    assert d.allowed is False and d.reason == "DURATION_EXCEEDED"
