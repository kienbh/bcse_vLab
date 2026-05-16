"""Admin-only endpoints — currently audit log read access.

Audit log is append-only and shared across the app (auth, booking,
session, reset, gateway). This endpoint lets admins browse and filter
recent rows from the web UI without touching the DB directly.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.db import get_db
from app.models import AuditLog, User

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
