"""Power cycle a device via its mapped smart plug — current booking owner OR admin/TA only."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models import Booking, BookingStatus, Device, PlugMapping, User, UserRole
from app.services.audit import audit_log
from app.services.plug_controller import make_adapter

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("/{device_id}/reset")
async def reset_device(
    device_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    device = (
        await db.execute(select(Device).where(Device.id == device_id))
    ).scalar_one_or_none()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "DEVICE_NOT_FOUND"})
    plug = (
        await db.execute(select(PlugMapping).where(PlugMapping.device_id == device_id))
    ).scalar_one_or_none()
    if plug is None:
        raise HTTPException(
            status.HTTP_412_PRECONDITION_FAILED,
            detail={"code": "NO_PLUG_MAPPED", "msg": "Device không có plug — không reset được."},
        )

    # Authz: current active booking owner, or admin/TA
    if user.role not in (UserRole.ADMIN, UserRole.TA):
        now = datetime.now(timezone.utc)
        active = (
            await db.execute(
                select(Booking).where(
                    Booking.device_id == device_id,
                    Booking.user_id == user.id,
                    Booking.status.in_([BookingStatus.SCHEDULED, BookingStatus.ACTIVE]),
                    Booking.start_time <= now,
                    Booking.end_time > now,
                )
            )
        ).scalar_one_or_none()
        if active is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail={"code": "NOT_CURRENT_BOOKER"},
            )

    adapter = make_adapter(
        plug_type=plug.plug_type,
        plug_ip=str(plug.plug_ip),
        relay=plug.plug_relay_index,
        token=plug.api_token,
    )
    try:
        state = await adapter.power_cycle(off_seconds=5)
    except Exception as e:
        await audit_log(
            db,
            actor=user,
            action="device.reset",
            target_type="device",
            target_id=str(device_id),
            details={"error": str(e)},
            request=request,
            success=False,
        )
        await db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail={"code": "PLUG_ERROR", "msg": str(e)})

    await audit_log(
        db,
        actor=user,
        action="device.reset",
        target_type="device",
        target_id=str(device_id),
        details={"plug_ip": str(plug.plug_ip), "result": state.raw},
        request=request,
    )
    await db.commit()
    return {"status": "ok", "powered_on": state.on, "raw": state.raw}
