"""Admin-only endpoints.

- Audit log browse (paginated reader + distinct actions for filter)
- Device power state toggle (M5.9 — pilot plugs in Hoà Lạc don't expose
  an API yet, so admins flip the rocker by hand and record state here)
- Mark-reset-done shortcut that flips both the device.power_state row and
  any pending reset_requests for that device to "completed"
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin, require_lecturer
from app.core.db import get_db
from app.models import (
    AuditLog,
    Device,
    DevicePowerState,
    ResetRequest,
    ResetRequestStatus,
    User,
)
from app.services.audit import audit_log

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/audit")
async def list_audit_logs(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    action: str | None = Query(default=None, max_length=64),
    actor_id: UUID | None = Query(default=None),
    target_type: str | None = Query(default=None, max_length=32),
    since: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Return the most-recent audit rows (newest first) joined to actor email.

    Filters are optional. Pagination uses limit+offset — the UI lazy-loads
    pages of 100; the table is BIGSERIAL+timestamp-indexed so this is cheap
    even past a million rows.
    """
    q = (
        select(
            AuditLog.id,
            AuditLog.timestamp,
            AuditLog.actor_id,
            User.email.label("actor_email"),
            AuditLog.action,
            AuditLog.target_type,
            AuditLog.target_id,
            AuditLog.details,
            AuditLog.ip_address,
            AuditLog.success,
        )
        .outerjoin(User, User.id == AuditLog.actor_id)
        .order_by(AuditLog.timestamp.desc())
    )
    if action:
        q = q.where(AuditLog.action == action)
    if actor_id:
        q = q.where(AuditLog.actor_id == actor_id)
    if target_type:
        q = q.where(AuditLog.target_type == target_type)
    if since:
        q = q.where(AuditLog.timestamp >= since)

    total = (
        await db.execute(
            select(func.count(AuditLog.id)).select_from(q.subquery())
        )
    ).scalar_one()

    rows = (await db.execute(q.limit(limit).offset(offset))).all()
    items = [
        {
            "id": r.id,
            "timestamp": r.timestamp.isoformat(),
            "actor_id": str(r.actor_id) if r.actor_id else None,
            "actor_email": r.actor_email,
            "action": r.action,
            "target_type": r.target_type,
            "target_id": r.target_id,
            "details": r.details,
            "ip_address": str(r.ip_address) if r.ip_address else None,
            "success": r.success,
        }
        for r in rows
    ]
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@router.get("/audit/actions")
async def list_audit_actions(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Distinct action values + counts — used to populate the filter dropdown."""
    rows = (
        await db.execute(
            select(AuditLog.action, func.count(AuditLog.id).label("n"))
            .group_by(AuditLog.action)
            .order_by(func.count(AuditLog.id).desc())
        )
    ).all()
    return [{"action": r.action, "count": r.n} for r in rows]


# ----------------------------------------------------------------------------
# M5.9 — device power state manual toggle
# ----------------------------------------------------------------------------


class PowerStateUpdate(BaseModel):
    power_state: DevicePowerState
    note: str | None = Field(default=None, max_length=255)


def _serialize_device_power(d: Device, actor_email: str | None) -> dict:
    return {
        "device_id": str(d.id),
        "name": d.name,
        "power_state": d.power_state.value,
        "power_state_changed_at": d.power_state_changed_at.isoformat(),
        "power_state_changed_by_id": (
            str(d.power_state_changed_by) if d.power_state_changed_by else None
        ),
        "power_state_changed_by_email": actor_email,
    }


@router.patch("/devices/{device_id}/power-state")
async def set_device_power_state(
    device_id: UUID,
    payload: PowerStateUpdate,
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Manually record what the smart plug is actually doing.

    Pilot reality: the plug API in Hoà Lạc is not online, so this endpoint
    lets admins record state changes after physically toggling the rocker.
    Every change goes to the audit log so we can replay history.
    """
    d = (
        await db.execute(select(Device).where(Device.id == device_id))
    ).scalar_one_or_none()
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "DEVICE_NOT_FOUND"})

    if d.power_state == payload.power_state:
        # idempotent — return current state without touching the row or audit log
        return _serialize_device_power(d, user.email)

    prev = d.power_state.value
    now = datetime.now(timezone.utc)
    d.power_state = payload.power_state
    d.power_state_changed_at = now
    d.power_state_changed_by = user.id

    await audit_log(
        db,
        actor=user,
        action="device.power_state.set",
        target_type="device",
        target_id=str(d.id),
        details={
            "device_name": d.name,
            "from": prev,
            "to": payload.power_state.value,
            "note": payload.note,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(d)
    return _serialize_device_power(d, user.email)


@router.post("/devices/{device_id}/mark-reset-done")
async def mark_reset_done(
    device_id: UUID,
    request: Request,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """One-click shortcut for the admin reset-queue flow.

    Effect:
      - device.power_state → ON
      - any in-flight reset_requests for this device (status pending or
        approved) → COMPLETED, with this admin as decided_by
      - audit row for traceability

    Used by the "Đã reset xong" button on the admin reset-queue page after
    the admin has physically power-cycled the kit.
    """
    d = (
        await db.execute(select(Device).where(Device.id == device_id))
    ).scalar_one_or_none()
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "DEVICE_NOT_FOUND"})

    now = datetime.now(timezone.utc)
    prev_power = d.power_state.value
    d.power_state = DevicePowerState.ON
    d.power_state_changed_at = now
    d.power_state_changed_by = user.id

    # PENDING + APPROVED = normal "still open" states.
    # FAILED = plug API call errored (mock mode never succeeds against the
    # offline Hoà Lạc plugs), but the admin's manual reset still closes the
    # business case so we treat it as the same bucket.
    rows = (
        await db.execute(
            select(ResetRequest).where(
                ResetRequest.device_id == device_id,
                ResetRequest.status.in_(
                    [
                        ResetRequestStatus.PENDING,
                        ResetRequestStatus.APPROVED,
                        ResetRequestStatus.FAILED,
                    ]
                ),
            )
        )
    ).scalars().all()
    closed_ids = []
    for req in rows:
        req.status = ResetRequestStatus.COMPLETED
        req.completed_at = now
        if req.decided_by is None:
            req.decided_by = user.id
            req.decided_at = now
        closed_ids.append(str(req.id))

    await audit_log(
        db,
        actor=user,
        action="device.reset.mark_done",
        target_type="device",
        target_id=str(d.id),
        details={
            "device_name": d.name,
            "power_state_from": prev_power,
            "closed_reset_request_ids": closed_ids,
        },
        request=request,
    )
    await db.commit()
    return {
        "device_id": str(d.id),
        "power_state": d.power_state.value,
        "closed_reset_request_ids": closed_ids,
    }
