"""Device CRUD — admin write, all users read (filtered to their accessible set later)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.core.db import get_db
from app.models import (
    Booking,
    BookingStatus,
    Class,
    ClassDeviceAssignment,
    Device,
    Enrollment,
    PlugMapping,
    SpecialAccess,
    User,
    UserRole,
)
from app.schemas import DeviceCreate, DeviceOut, DeviceUpdate

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceOut])
async def list_devices(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Device]:
    result = await db.execute(select(Device).order_by(Device.name))
    return list(result.scalars().all())


@router.get("/{device_id}", response_model=DeviceOut)
async def get_device(
    device_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Device:
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "DEVICE_NOT_FOUND"})
    return device


@router.post("", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
async def create_device(
    payload: DeviceCreate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Device:
    device = Device(
        name=payload.name,
        device_type=payload.device_type,
        model=payload.model,
        internal_ip=str(payload.internal_ip),
        ssh_port=payload.ssh_port,
        ssh_user=payload.ssh_user,
        capabilities=payload.capabilities,
        notes=payload.notes,
    )
    db.add(device)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"code": "DEVICE_NAME_TAKEN", "msg": str(e.orig)}
        )

    if payload.plug:
        db.add(
            PlugMapping(
                device_id=device.id,
                plug_ip=str(payload.plug.plug_ip),
                plug_type=payload.plug.plug_type,
                plug_relay_index=payload.plug.plug_relay_index,
            )
        )
    await db.commit()
    await db.refresh(device)
    return device


@router.patch("/{device_id}", response_model=DeviceOut)
async def update_device(
    device_id: UUID,
    payload: DeviceUpdate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Device:
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "DEVICE_NOT_FOUND"})
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        if k == "internal_ip" and v is not None:
            v = str(v)
        setattr(device, k, v)
    await db.commit()
    await db.refresh(device)
    return device


async def _user_can_view_device_schedule(
    db: AsyncSession, *, user: User, device_id: UUID
) -> bool:
    """A user can view a device's weekly schedule if they:
    - are admin or lecturer (see everything), or
    - have an active enrollment in a class that has an active assignment for this device, or
    - have an active special_access for this device.
    """
    if user.role in (UserRole.ADMIN, UserRole.LECTURER):
        return True
    res = await db.execute(
        select(ClassDeviceAssignment.id)
        .join(Class, Class.id == ClassDeviceAssignment.class_id)
        .join(Enrollment, Enrollment.class_id == Class.id)
        .where(
            Enrollment.user_id == user.id,
            Enrollment.is_active.is_(True),
            ClassDeviceAssignment.device_id == device_id,
            ClassDeviceAssignment.revoked_at.is_(None),
        )
        .limit(1)
    )
    if res.first() is not None:
        return True
    res = await db.execute(
        select(SpecialAccess.id).where(
            SpecialAccess.user_id == user.id,
            SpecialAccess.device_id == device_id,
            SpecialAccess.revoked_at.is_(None),
        ).limit(1)
    )
    return res.first() is not None


@router.get("/{device_id}/availability")
async def device_availability(
    device_id: UUID,
    days: int = Query(7, ge=1, le=30),
    week_start: datetime | None = Query(
        None,
        description="ISO datetime — if set, return bookings in [week_start, week_start+7d). Overrides `days`.",
    ),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return busy slots (scheduled+active) on this device, with display labels.

    Used by the week-calendar view on `/bookings` to show everyone's bookings on
    a device the caller has access to. Each slot has:
    - `is_mine`: True if booking is the caller's
    - `display`: "Bạn" if mine, else the other user's student_code or "Người dùng"

    Access: admin/lecturer can view any device. Students can only view devices
    they have an active class enrollment OR special_access for.
    """
    device = (
        await db.execute(select(Device).where(Device.id == device_id))
    ).scalar_one_or_none()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "DEVICE_NOT_FOUND"})

    if not await _user_can_view_device_schedule(db, user=user, device_id=device_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"code": "ACCESS_DENIED", "hint": "Bạn chưa được cấp quyền cho thiết bị này."},
        )

    if week_start is not None:
        start = week_start.astimezone(timezone.utc)
        horizon = start + timedelta(days=7)
    else:
        start = datetime.now(timezone.utc)
        horizon = start + timedelta(days=days)

    res = await db.execute(
        select(Booking, User.student_code, User.full_name)
        .join(User, User.id == Booking.user_id)
        .where(
            Booking.device_id == device_id,
            Booking.status.in_([BookingStatus.SCHEDULED, BookingStatus.ACTIVE]),
            Booking.end_time > start,
            Booking.start_time < horizon,
        )
        .order_by(Booking.start_time)
    )
    busy = []
    for b, sc, full_name in res.all():
        is_mine = b.user_id == user.id
        if is_mine:
            display = "Bạn"
        elif user.role in (UserRole.ADMIN, UserRole.LECTURER):
            # Privileged viewer — show full name so lecturer can identify the student
            display = sc or full_name or "Người dùng"
        else:
            # Peer student — privacy: only student_code, no name/email
            display = sc or "Người dùng"
        busy.append({
            "start": b.start_time.isoformat(),
            "end": b.end_time.isoformat(),
            "is_mine": is_mine,
            "booking_id": str(b.id),
            "status": b.status.value,
            "display": display,
        })
    return {
        "device_id": str(device_id),
        "device_name": device.name,
        "from": start.isoformat(),
        "to": horizon.isoformat(),
        "busy": busy,
    }


@router.get("/{device_id}/suggest-slots")
async def suggest_free_slots(
    device_id: UUID,
    duration_hours: float = Query(2, gt=0, le=8),
    days: int = Query(7, ge=1, le=14),
    count: int = Query(5, ge=1, le=20),
    earliest_hour: int = Query(8, ge=0, le=23),
    latest_hour: int = Query(22, ge=1, le=24),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Suggest the next `count` free slots of `duration_hours` length.

    Greedy scan: walk the busy timeline from now, return windows that fit. Only
    looks at booking conflicts (no class-window/quota check — the actual /bookings
    POST will gate that with full access_control).
    """
    device = (
        await db.execute(select(Device).where(Device.id == device_id))
    ).scalar_one_or_none()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "DEVICE_NOT_FOUND"})

    now = datetime.now(timezone.utc)
    # Round next slot up to the next 30 min for friendliness
    minute = (now.minute // 30 + 1) * 30
    cursor = now.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minute)
    horizon = now + timedelta(days=days)
    duration = timedelta(hours=duration_hours)

    res = await db.execute(
        select(Booking.start_time, Booking.end_time)
        .where(
            Booking.device_id == device_id,
            Booking.status.in_([BookingStatus.SCHEDULED, BookingStatus.ACTIVE]),
            Booking.end_time > cursor,
            Booking.start_time < horizon,
        )
        .order_by(Booking.start_time)
    )
    busy = list(res.all())

    suggestions: list[dict] = []
    while cursor + duration <= horizon and len(suggestions) < count:
        # Snap cursor into the day's open window
        local = cursor  # UTC; frontend converts to local for display
        if local.hour < earliest_hour:
            cursor = cursor.replace(hour=earliest_hour, minute=0)
            continue
        if local.hour >= latest_hour or (local + duration).hour > latest_hour:
            cursor = (cursor + timedelta(days=1)).replace(hour=earliest_hour, minute=0)
            continue
        # Find first conflict that overlaps [cursor, cursor+duration)
        next_end = cursor + duration
        conflict = None
        for s, e in busy:
            if e <= cursor:
                continue
            if s >= next_end:
                break
            conflict = (s, e)
            break
        if conflict is None:
            suggestions.append({
                "start": cursor.isoformat(),
                "end": next_end.isoformat(),
            })
            cursor = next_end
        else:
            # Skip past the conflict, snap to the next 30-min mark
            cursor = conflict[1]
            offset = cursor.minute % 30
            if offset:
                cursor = cursor + timedelta(minutes=30 - offset)
    return {
        "device_id": str(device_id),
        "duration_hours": duration_hours,
        "suggestions": suggestions,
    }


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: UUID,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "DEVICE_NOT_FOUND"})
    await db.delete(device)
    await db.commit()
