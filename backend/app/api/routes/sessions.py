"""Session lifecycle — provision SSH key on booking start, revoke on end.

For M0/M1 we expose synchronous endpoints; M4 will move provision/revoke into RQ jobs
scheduled at start_time / end_time of the booking.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_lecturer
from app.core.config import get_settings
from app.core.db import get_db
from app.models import (
    Booking,
    BookingStatus,
    Device,
    Session as DBSession,
    SessionStatus,
    User,
    UserRole,
)
from app.services import ssh_manager
from app.services.audit import audit_log

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/provision/{booking_id}")
async def provision(
    booking_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Generate an ephemeral SSH key for the booking owner and push to the device.

    Returns the **private key once** — caller must save it locally; the server discards it.
    """
    booking = (
        await db.execute(select(Booking).where(Booking.id == booking_id))
    ).scalar_one_or_none()
    if booking is None or booking.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "BOOKING_NOT_FOUND"})
    if booking.status not in (BookingStatus.SCHEDULED, BookingStatus.ACTIVE):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "BOOKING_NOT_ACTIVATABLE", "status": booking.status.value},
        )
    now = datetime.now(timezone.utc)
    if now < booking.start_time:
        # Allow 5 min grace before slot starts
        from datetime import timedelta

        if booking.start_time - now > timedelta(minutes=5):
            raise HTTPException(
                status.HTTP_425_TOO_EARLY,
                detail={"code": "BOOKING_NOT_STARTED_YET", "starts_at": booking.start_time.isoformat()},
            )
    if now >= booking.end_time:
        raise HTTPException(
            status.HTTP_410_GONE, detail={"code": "BOOKING_EXPIRED"}
        )

    device = (
        await db.execute(select(Device).where(Device.id == booking.device_id))
    ).scalar_one_or_none()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "DEVICE_NOT_FOUND"})

    # If a session already exists for this booking, rotate it: strip the old
    # ephemeral pubkey from the KIT, mark the old session COMPLETED, then
    # generate a fresh one. The private key is only ever in transit once, so
    # re-click Connect must mint a new key — we cannot replay the old one.
    existing = (
        await db.execute(select(DBSession).where(DBSession.booking_id == booking_id))
    ).scalar_one_or_none()
    if existing is not None:
        old_tag = ""
        if "session=" in (existing.ssh_pubkey or ""):
            old_tag = existing.ssh_pubkey.split("session=")[-1].split(" ")[0]
        if old_tag:
            try:
                await ssh_manager.revoke_session(
                    device_internal_ip=str(device.internal_ip),
                    device_ssh_port=device.ssh_port,
                    device_ssh_user=device.ssh_user,
                    backend_admin_key_path=get_settings().BACKEND_SSH_KEY_PATH,
                    session_tag=old_tag,
                )
            except Exception:
                # Don't block re-issue if revoke best-effort fails — sed/ssh might be flaky.
                pass
        existing.status = SessionStatus.COMPLETED
        existing.ended_at = datetime.now(timezone.utc)
        await db.flush()

    settings = get_settings()
    session_tag = f"sess-{uuid4().hex[:12]}"
    result = await ssh_manager.provision_session(
        device_internal_ip=str(device.internal_ip),
        device_ssh_port=device.ssh_port,
        device_ssh_user=device.ssh_user,
        backend_admin_key_path=settings.BACKEND_SSH_KEY_PATH,
        session_tag=session_tag,
        expires_at_iso=booking.end_time.isoformat(),
    )

    sess = DBSession(
        booking_id=booking.id,
        ssh_pubkey=result.public_key_line,
        ssh_fingerprint=result.fingerprint,
        status=SessionStatus.ACTIVE,
    )
    db.add(sess)
    booking.status = BookingStatus.ACTIVE
    await audit_log(
        db,
        actor=user,
        action="session.provision",
        target_type="session",
        target_id=session_tag,
        details={
            "booking_id": str(booking.id),
            "device_id": str(device.id),
            "fingerprint": result.fingerprint,
            "mocked": result.mocked,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(sess)

    return {
        "session_id": str(sess.id),
        "booking_id": str(booking.id),
        "ssh_user": device.ssh_user,
        "ssh_host": str(device.internal_ip),
        "ssh_port": device.ssh_port,
        "fingerprint": result.fingerprint,
        "private_key": result.private_key_pem,
        # Wetty 2.x path syntax: /term/ssh/<user>@<host>:<port>. The wetty
        # container has portal_admin_ed25519 mounted at /keys/ and authenticates
        # to every KIT with it (publickey only, --allow-remote-hosts).
        "wetty_url": f"/term/ssh/{device.ssh_user}@{device.internal_ip}:{device.ssh_port}",
        "expires_at": booking.end_time.isoformat(),
        "mocked": result.mocked,
    }


@router.post("/{session_id}/end")
async def end(
    session_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    sess = (
        await db.execute(select(DBSession).where(DBSession.id == session_id))
    ).scalar_one_or_none()
    if sess is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "SESSION_NOT_FOUND"})
    booking = (
        await db.execute(select(Booking).where(Booking.id == sess.booking_id))
    ).scalar_one()
    if booking.user_id != user.id and user.role not in (UserRole.ADMIN, UserRole.LECTURER):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": "FORBIDDEN"})

    device = (
        await db.execute(select(Device).where(Device.id == booking.device_id))
    ).scalar_one()
    settings = get_settings()
    session_tag = sess.ssh_pubkey.split("session=")[-1].split(" ")[0] if "session=" in sess.ssh_pubkey else ""
    await ssh_manager.revoke_session(
        device_internal_ip=str(device.internal_ip),
        device_ssh_port=device.ssh_port,
        device_ssh_user=device.ssh_user,
        backend_admin_key_path=settings.BACKEND_SSH_KEY_PATH,
        session_tag=session_tag,
    )
    sess.status = SessionStatus.COMPLETED
    sess.ended_at = datetime.now(timezone.utc)
    booking.status = BookingStatus.COMPLETED
    await audit_log(
        db,
        actor=user,
        action="session.end",
        target_type="session",
        target_id=str(sess.id),
        details={"booking_id": str(booking.id), "by_user": user.email},
        request=request,
    )
    await db.commit()
    return {"status": "ended", "session_id": str(sess.id)}


@router.get("/active")
async def list_active(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """All active sessions visible to the caller (own + lecturer's classes + admin all)."""
    q = (
        select(DBSession, Booking, Device, User)
        .join(Booking, Booking.id == DBSession.booking_id)
        .join(Device, Device.id == Booking.device_id)
        .join(User, User.id == Booking.user_id)
        .where(DBSession.status == SessionStatus.ACTIVE)
    )
    rows = (await db.execute(q)).all()
    out: list[dict] = []
    for sess, booking, device, owner in rows:
        # admin sees all; lecturer sees students enrolled in their classes; user sees own
        if user.role == UserRole.ADMIN or owner.id == user.id:
            visible = True
        elif user.role == UserRole.LECTURER:
            # Cheap check: booking.class_id and class.lecturer_id == user.id
            from app.models import Class
            cls_lec = await db.execute(
                select(Class.lecturer_id).where(Class.id == booking.class_id)
                if booking.class_id is not None
                else select(Class.lecturer_id).where(Class.id == None)  # noqa: E711
            )
            row = cls_lec.scalar_one_or_none()
            visible = row == user.id
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
                    "started_at": sess.started_at.isoformat(),
                    "ends_at": booking.end_time.isoformat(),
                    "fingerprint": sess.ssh_fingerprint,
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
    """Lecturer/admin kicks a student session (revokes SSH key + marks as kicked)."""
    sess = (
        await db.execute(select(DBSession).where(DBSession.id == session_id))
    ).scalar_one_or_none()
    if sess is None or sess.status != SessionStatus.ACTIVE:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "SESSION_NOT_FOUND"})

    booking = (
        await db.execute(select(Booking).where(Booking.id == sess.booking_id))
    ).scalar_one()
    device = (
        await db.execute(select(Device).where(Device.id == booking.device_id))
    ).scalar_one()
    settings = get_settings()
    session_tag = sess.ssh_pubkey.split("session=")[-1].split(" ")[0] if "session=" in sess.ssh_pubkey else ""
    await ssh_manager.revoke_session(
        device_internal_ip=str(device.internal_ip),
        device_ssh_port=device.ssh_port,
        device_ssh_user=device.ssh_user,
        backend_admin_key_path=settings.BACKEND_SSH_KEY_PATH,
        session_tag=session_tag,
    )
    sess.status = SessionStatus.KICKED
    sess.kicked_by = user.id
    sess.ended_at = datetime.now(timezone.utc)
    booking.status = BookingStatus.CANCELLED
    await audit_log(
        db,
        actor=user,
        action="session.kick",
        target_type="session",
        target_id=str(sess.id),
        details={"booking_id": str(booking.id), "device": device.name},
        request=request,
    )
    await db.commit()
    return {"status": "kicked", "session_id": str(sess.id)}
