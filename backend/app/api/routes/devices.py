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
from app.models import Booking, BookingStatus, Device, PlugMapping, User
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


@router.get("/{device_id}/availability")
async def device_availability(
    device_id: UUID,
    days: int = Query(7, ge=1, le=30),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return busy slots (scheduled+active) on this device over `days` from now.

    Frontend calendar uses this to overlay 'busy' blocks. Each slot has
    `is_mine=true` if the booking belongs to the caller (so we don't double-count
    against suggestions).
    """
    device = (
        await db.execute(select(Device).where(Device.id == device_id))
    ).scalar_one_or_none()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "DEVICE_NOT_FOUND"})

    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=days)

    res = await db.execute(
        select(Booking).where(
            Booking.device_id == device_id,
            Booking.status.in_([BookingStatus.SCHEDULED, BookingStatus.ACTIVE]),
            Booking.end_time > now,
            Booking.start_time < horizon,
        ).order_by(Booking.start_time)
    )
    busy = []
    for b in res.scalars().all():
        busy.append({
            "start": b.start_time.isoformat(),
            "end": b.end_time.isoformat(),
            "is_mine": b.user_id == user.id,
            "booking_id": str(b.id),
        })
    return {
        "device_id": str(device_id),
        "device_name": device.name,
        "from": now.isoformat(),
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
