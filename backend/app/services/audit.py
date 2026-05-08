"""Append-only audit logging — every mutation + access decision lands here.

Usage:
    await audit_log(db, actor=user, action="booking.create", target_id=booking.id, details={...})
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.models.audit import AuditLog


async def audit_log(
    db: AsyncSession,
    *,
    actor: User | UUID | None,
    action: str,
    target_type: str | None = None,
    target_id: str | UUID | None = None,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
    success: bool = True,
) -> AuditLog:
    actor_id: UUID | None
    if isinstance(actor, User):
        actor_id = actor.id
    elif isinstance(actor, UUID):
        actor_id = actor
    else:
        actor_id = None

    ip: str | None = None
    ua: str | None = None
    if request is not None:
        # Trust X-Forwarded-For from CF/SV08 nginx
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            ip = fwd.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent", "")[:500]

    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details=details or {},
        ip_address=ip,
        user_agent=ua,
        success=success,
    )
    db.add(entry)
    # Don't commit here — caller's transaction owns it; flush only.
    await db.flush()
    return entry
