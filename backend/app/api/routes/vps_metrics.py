"""Live VPS-GPU metrics endpoints (M6.5).

Two endpoints, both behind `/api`:
  - `GET /vps-metrics`         — bulk snapshot for a whole tier (default `gpu`),
                                  used by the family dashboard cards.
  - `GET /vps-metrics/{id}`    — single-device detail, used by the sidebar
                                  panel a student sees while holding a block.

Both are read-only and cheap (25 s cache); any authenticated user may call,
matching the existing `live-status` policy. External users are filtered to
the devices they hold SpecialAccess for, mirroring `list_devices`.
"""
from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models import Device, SpecialAccess, User
from app.models.enums import DeviceType
from app.services.vps_metrics import get_metrics

router = APIRouter(prefix="/vps-metrics", tags=["vps-metrics"])


async def _visible_devices(
    db: AsyncSession, *, user: User, tier: str | None
) -> list[Device]:
    """Devices the caller may probe for metrics.

    - external user → only their granted SpecialAccess devices
    - everyone else → all VPS, optionally filtered to `tier`
    """
    if user.external:
        q = (
            select(Device)
            .join(SpecialAccess, SpecialAccess.device_id == Device.id)
            .where(
                SpecialAccess.user_id == user.id,
                SpecialAccess.revoked_at.is_(None),
                Device.device_type == DeviceType.VPS,
            )
        )
    else:
        q = select(Device).where(Device.device_type == DeviceType.VPS)
    result = await db.execute(q.order_by(Device.name))
    devices = list(result.scalars().all())
    if tier:
        devices = [d for d in devices if (d.capabilities or {}).get("tier") == tier]
    return devices


@router.get("")
async def list_metrics(
    tier: str = Query("gpu", description="Filter by capabilities.tier (default: gpu)"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Bulk metrics snapshot for every VPS in `tier`.

    Cards on the family dashboard render this as a coloured strip — green
    under 50 % util, amber 50-80 %, red above 80 %.
    """
    devices = await _visible_devices(db, user=user, tier=tier)
    if not devices:
        return {"tier": tier, "metrics": []}

    async def _one(d: Device) -> dict:
        gpu_index = (d.capabilities or {}).get("gpu_index")
        snap = await get_metrics(
            device_id=d.id,
            internal_ip=str(d.internal_ip),
            ssh_port=d.ssh_port,
            ssh_user=d.ssh_user,
            gpu_index=gpu_index if isinstance(gpu_index, int) else None,
        )
        return snap.to_dict()

    # Probe all VPS in parallel — each call is either an instant cache hit
    # or one SSH RTT (~5 ms on the same LAN). With ≤ 3 GPU boxes the bulk
    # call finishes in well under the 30 s polling window.
    snaps = await asyncio.gather(*(_one(d) for d in devices))
    return {"tier": tier, "metrics": snaps}


@router.get("/{device_id}")
async def device_metrics(
    device_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Detailed metrics for one VPS — feeds the sidebar dashboard."""
    device = (
        await db.execute(select(Device).where(Device.id == device_id))
    ).scalar_one_or_none()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "DEVICE_NOT_FOUND"})
    if device.device_type != DeviceType.VPS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "NOT_A_VPS", "hint": "Metrics only available for VPS devices."},
        )
    if user.external:
        # External users see only metrics for VPS they were explicitly
        # granted access to via SpecialAccess — mirrors list_devices.
        grant = await db.execute(
            select(SpecialAccess.id).where(
                SpecialAccess.user_id == user.id,
                SpecialAccess.device_id == device_id,
                SpecialAccess.revoked_at.is_(None),
            ).limit(1)
        )
        if grant.first() is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail={"code": "ACCESS_DENIED"},
            )

    gpu_index = (device.capabilities or {}).get("gpu_index")
    snap = await get_metrics(
        device_id=device.id,
        internal_ip=str(device.internal_ip),
        ssh_port=device.ssh_port,
        ssh_user=device.ssh_user,
        gpu_index=gpu_index if isinstance(gpu_index, int) else None,
    )
    return snap.to_dict()
