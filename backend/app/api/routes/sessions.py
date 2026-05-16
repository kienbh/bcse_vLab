"""Session monitoring endpoints — ADR-0013 (M5.8).

The credential-issuing endpoints moved to `gateway.py`
(`/api/bookings/{id}/access*`). What remains here is the read-side dashboard
view + lecturer/admin kick: both now query `gateway_sessions`.

The legacy `sessions` table (M5.6 ed25519 flow) is kept untouched for audit
history but is no longer written to.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_lecturer
from app.core.db import get_db
from app.models import (
    Booking,
    BookingStatus,
    Class,
    Device,
    GatewaySession,
    User,
    UserRole,
)
from app.services import gateway_credentials
from app.services.audit import audit_log

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/active")
async def list_active(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """All active gateway sessions visible to the caller.

    Visibility:
      - admin → every active row
      - lecturer → sessions whose booking.class_.lecturer_id == user.id
      - student → own only
    """
    now = datetime.now(timezone.utc)
    q = (
        select(GatewaySession, Booking, Device, User)
        .join(Booking, Booking.id == GatewaySession.booking_id)
        .join(Device, Device.id == GatewaySession.device_id)
        .join(User, User.id == GatewaySession.user_id)
        .where(
            GatewaySession.revoked_at.is_(None),
            GatewaySession.expires_at > now,
        )
    )
    rows = (await db.execute(q)).all()

    out: list[dict] = []
    for sess, booking, device, owner in rows:
        if user.role == UserRole.ADMIN or owner.id == user.id:
            visible = True
        elif user.role == UserRole.LECTURER and booking.class_id is not None:
            cls_lec = await db.execute(
                select(Class.lecturer_id).where(Class.id == booking.class_id)
            )
            visible = cls_lec.scalar_one_or_none() == user.id
        else:
            visible = False

        if visible:
            out.append(
                {
                    "session_id": str(sess.id),
                    "booking_id": str(booking.id),
                    "device": device.name,
                    "user_email": owner.email,
                    "user_name": owner.full_name,
                    "issued_at": sess.issued_at.isoformat(),
                    "ends_at": sess.expires_at.isoformat(),
                    "last_auth_at": sess.last_auth_at.isoformat() if sess.last_auth_at else None,
                    "client_ip": str(sess.client_ip) if sess.client_ip else None,
                    "regenerate_count": sess.regenerate_count,
                    "active_connection": sess.active_pid is not None,
                }
            )
    return out


@router.post("/{session_id}/kick")
async def kick(
    session_id: UUID,
    request: Request,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Lecturer/admin force-revokes a gateway session.

    Effect:
      - sets revoked_at → next auth attempt fails
      - cancels the underlying booking
      - the janitor worker will kill any TCP-still-open ssh process within 30s
    """
    sess = (
        await db.execute(select(GatewaySession).where(GatewaySession.id == session_id))
    ).scalar_one_or_none()
    if sess is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "SESSION_NOT_FOUND"})
    if sess.revoked_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "SESSION_ALREADY_REVOKED"},
        )

    booking = (
        await db.execute(select(Booking).where(Booking.id == sess.booking_id))
    ).scalar_one()
    device = (
        await db.execute(select(Device).where(Device.id == booking.device_id))
    ).scalar_one()

    await gateway_credentials.revoke(db, sess, reason=f"kicked_by:{user.email}")
    if booking.status == BookingStatus.ACTIVE:
        booking.status = BookingStatus.CANCELLED

    await audit_log(
        db,
        actor=user,
        action="gateway.session.kick",
        target_type="gateway_session",
        target_id=str(sess.id),
        details={"booking_id": str(booking.id), "device": device.name},
        request=request,
    )
    await db.commit()
    return {"status": "kicked", "session_id": str(sess.id)}
