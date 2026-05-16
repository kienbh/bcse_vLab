"""Gateway access endpoints — ADR-0013 (M5.8).

Two distinct audiences:

  1. Booking owner (cookie-authenticated):
       POST   /api/bookings/{id}/access              issue or rotate password
       GET    /api/bookings/{id}/access              read current session info (no password)
       POST   /api/bookings/{id}/access/regenerate   force new password
       DELETE /api/bookings/{id}/access              user-initiated revoke

  2. The jump host (PAM script, shared-secret authenticated):
       POST   /api/gateway/auth            PAM hands plaintext password → 200/401
       POST   /api/gateway/session-start   sshd records PID + pty for kill
       POST   /api/gateway/session-end     sshd records bytes_in/out
       POST   /api/gateway/resolve-target  ForceCommand fetches target host
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.models import (
    Booking,
    BookingStatus,
    Device,
    GatewaySession,
    User,
)
from app.services import gateway_credentials
from app.services.audit import audit_log

bookings_router = APIRouter(prefix="/bookings", tags=["gateway"])
gateway_router = APIRouter(prefix="/gateway", tags=["gateway-internal"])


# ----------------------------------------------------------------------------
# Booking-owner endpoints
# ----------------------------------------------------------------------------


class AccessIssueResponse(BaseModel):
    """Returned exactly once when password is minted. Plaintext NEVER goes out again."""

    session_id: str
    password: str
    ssh_username: str
    jump_host: str
    jump_port: int
    target_user: str
    target_host: str
    target_port: int
    ssh_command: str
    expires_at: datetime
    issued_at: datetime
    regenerate_count: int


class AccessInfoResponse(BaseModel):
    """Returned by GET — no plaintext password, just lifecycle metadata."""

    session_id: str
    ssh_username: str
    jump_host: str
    jump_port: int
    target_user: str
    target_host: str
    target_port: int
    ssh_command_template: str
    expires_at: datetime
    issued_at: datetime
    last_auth_at: datetime | None
    revoked_at: datetime | None
    regenerate_count: int


def _build_ssh_command(*, jump_user: str, jump_host: str, jump_port: int, target_user: str, target_host: str) -> str:
    # MobaXterm / OpenSSH both understand `ssh -J user@host:port user@host`.
    # Keep the form one-liner so users can paste it verbatim.
    return f"ssh -J {jump_user}@{jump_host}:{jump_port} {target_user}@{target_host}"


async def _load_booking_for_owner(
    db: AsyncSession, booking_id: UUID, user: User
) -> Booking:
    booking = (
        await db.execute(select(Booking).where(Booking.id == booking_id))
    ).scalar_one_or_none()
    if booking is None or booking.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "BOOKING_NOT_FOUND"})
    return booking


def _validate_booking_window(booking: Booking) -> None:
    if booking.status not in (BookingStatus.SCHEDULED, BookingStatus.ACTIVE):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "BOOKING_NOT_ACTIVATABLE", "status": booking.status.value},
        )
    now = datetime.now(timezone.utc)
    # 5-minute grace before slot — same as M5.7 to keep UX identical.
    from datetime import timedelta

    if now < booking.start_time and (booking.start_time - now) > timedelta(minutes=5):
        raise HTTPException(
            status.HTTP_425_TOO_EARLY,
            detail={
                "code": "BOOKING_NOT_STARTED_YET",
                "starts_at": booking.start_time.isoformat(),
            },
        )
    if now >= booking.end_time:
        raise HTTPException(
            status.HTTP_410_GONE, detail={"code": "BOOKING_EXPIRED"}
        )


async def _issue_or_rotate(
    db: AsyncSession,
    *,
    booking: Booking,
    user: User,
    request: Request,
    action: str,
    force_rotate: bool = False,
) -> AccessIssueResponse:
    device = (
        await db.execute(select(Device).where(Device.id == booking.device_id))
    ).scalar_one_or_none()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "DEVICE_NOT_FOUND"})

    settings = get_settings()
    result = await gateway_credentials.issue_for_booking(
        db,
        booking=booking,
        device=device,
        ssh_username=settings.GATEWAY_SSH_USERNAME,
        force_rotate=force_rotate,
    )
    if booking.status == BookingStatus.SCHEDULED:
        booking.status = BookingStatus.ACTIVE

    await audit_log(
        db,
        actor=user,
        action=action,
        target_type="gateway_session",
        target_id=str(result.session.id),
        details={
            "booking_id": str(booking.id),
            "device_id": str(device.id),
            "expires_at": booking.end_time.isoformat(),
            "regenerate_count": result.session.regenerate_count,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(result.session)

    ssh_command = _build_ssh_command(
        jump_user=settings.GATEWAY_SSH_USERNAME,
        jump_host=settings.JUMP_HOST_PUBLIC,
        jump_port=settings.JUMP_HOST_PUBLIC_PORT,
        target_user=device.ssh_user,
        target_host=str(device.internal_ip),
    )
    return AccessIssueResponse(
        session_id=str(result.session.id),
        password=result.password,
        ssh_username=settings.GATEWAY_SSH_USERNAME,
        jump_host=settings.JUMP_HOST_PUBLIC,
        jump_port=settings.JUMP_HOST_PUBLIC_PORT,
        target_user=device.ssh_user,
        target_host=str(device.internal_ip),
        target_port=device.ssh_port,
        ssh_command=ssh_command,
        expires_at=result.session.expires_at,
        issued_at=result.session.issued_at,
        regenerate_count=result.session.regenerate_count,
    )


@bookings_router.post("/{booking_id}/access", response_model=AccessIssueResponse)
async def issue_access(
    booking_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AccessIssueResponse:
    booking = await _load_booking_for_owner(db, booking_id, user)
    _validate_booking_window(booking)
    return await _issue_or_rotate(
        db, booking=booking, user=user, request=request, action="gateway.access.issue"
    )


@bookings_router.post(
    "/{booking_id}/access/regenerate", response_model=AccessIssueResponse
)
async def regenerate_access(
    booking_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AccessIssueResponse:
    booking = await _load_booking_for_owner(db, booking_id, user)
    _validate_booking_window(booking)
    return await _issue_or_rotate(
        db, booking=booking, user=user, request=request,
        action="gateway.access.regenerate", force_rotate=True,
    )


@bookings_router.get("/{booking_id}/access", response_model=AccessInfoResponse)
async def get_access_info(
    booking_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AccessInfoResponse:
    booking = await _load_booking_for_owner(db, booking_id, user)
    sess = (
        await db.execute(
            select(GatewaySession).where(GatewaySession.booking_id == booking_id)
        )
    ).scalar_one_or_none()
    if sess is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "NO_GATEWAY_SESSION"})

    settings = get_settings()
    ssh_command = _build_ssh_command(
        jump_user=sess.ssh_username,
        jump_host=settings.JUMP_HOST_PUBLIC,
        jump_port=settings.JUMP_HOST_PUBLIC_PORT,
        target_user=sess.target_user,
        target_host=str(sess.target_host),
    )
    return AccessInfoResponse(
        session_id=str(sess.id),
        ssh_username=sess.ssh_username,
        jump_host=settings.JUMP_HOST_PUBLIC,
        jump_port=settings.JUMP_HOST_PUBLIC_PORT,
        target_user=sess.target_user,
        target_host=str(sess.target_host),
        target_port=sess.target_port,
        ssh_command_template=ssh_command,
        expires_at=sess.expires_at,
        issued_at=sess.issued_at,
        last_auth_at=sess.last_auth_at,
        revoked_at=sess.revoked_at,
        regenerate_count=sess.regenerate_count,
    )


@bookings_router.delete("/{booking_id}/access")
async def revoke_access(
    booking_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    booking = await _load_booking_for_owner(db, booking_id, user)
    sess = (
        await db.execute(
            select(GatewaySession).where(GatewaySession.booking_id == booking.id)
        )
    ).scalar_one_or_none()
    if sess is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "NO_GATEWAY_SESSION"})
    await gateway_credentials.revoke(db, sess, reason="user_revoked")
    await audit_log(
        db,
        actor=user,
        action="gateway.access.revoke",
        target_type="gateway_session",
        target_id=str(sess.id),
        details={"booking_id": str(booking.id)},
        request=request,
    )
    await db.commit()
    return {"status": "revoked", "session_id": str(sess.id)}


# ----------------------------------------------------------------------------
# Jump-host internal endpoints (shared-secret authenticated)
# ----------------------------------------------------------------------------


class AuthRequest(BaseModel):
    username: str = Field(..., max_length=32)
    password: str = Field(..., max_length=128)
    client_ip: str | None = None


class AuthResponse(BaseModel):
    ok: bool
    session_id: str | None = None
    target_user: str | None = None
    target_host: str | None = None
    target_port: int | None = None
    expires_at: datetime | None = None


class SessionStartRequest(BaseModel):
    session_id: UUID
    pid: int
    pty_path: str | None = None
    client_ip: str | None = None


class SessionEndRequest(BaseModel):
    session_id: UUID
    bytes_in: int = 0
    bytes_out: int = 0


class ResolveTargetRequest(BaseModel):
    username: str | None = None
    client_ip: str | None = None
    # If PAM saved a session_id during auth, the ForceCommand wrapper can pass
    # it through. We don't trust it blindly — still scope to the username.
    session_id: UUID | None = None


def _check_gateway_secret(provided: str | None) -> None:
    settings = get_settings()
    expected = settings.GATEWAY_SHARED_SECRET.get_secret_value()
    if not provided or provided != expected:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail={"code": "BAD_GATEWAY_SECRET"}
        )


@gateway_router.post("/auth", response_model=AuthResponse)
async def gateway_auth(
    payload: AuthRequest,
    x_gateway_secret: str | None = Header(default=None, alias="X-Gateway-Secret"),
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """PAM verify endpoint. 200 with body for success, 401 with body for any fail.

    Returning 200 on auth failure is deliberate — pam_exec only inspects the
    HTTP exit code, but we still write a useful body for debugging. Auth
    decision is signalled by `ok` field, and the PAM script's `jq -e
    '.ok==true'` is the gate. We pair this with a real `Authorization: Bearer`
    style shared-secret header so unauthorized hosts can't even reach the
    bcrypt scan.
    """
    try:
        _check_gateway_secret(x_gateway_secret)
    except HTTPException:
        await gateway_credentials.log_attempt(
            db,
            client_ip=payload.client_ip,
            ssh_username=payload.username,
            outcome="bad_secret",
        )
        await db.commit()
        raise

    result = await gateway_credentials.verify_password(
        db,
        attempted_password=payload.password,
        ssh_username=payload.username,
        client_ip=payload.client_ip,
    )
    await db.commit()

    if result.outcome != "ok" or result.session is None:
        return AuthResponse(ok=False)

    return AuthResponse(
        ok=True,
        session_id=str(result.session.id),
        target_user=result.session.target_user,
        target_host=str(result.session.target_host),
        target_port=result.session.target_port,
        expires_at=result.session.expires_at,
    )


@gateway_router.post("/resolve-target")
async def gateway_resolve_target(
    payload: ResolveTargetRequest,
    x_gateway_secret: str | None = Header(default=None, alias="X-Gateway-Secret"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Used by the ForceCommand wrapper *after* PAM passed — we look up the
    most-recently-authed active session matching the username + client IP, and
    return its target. Keep simple: find session with last_auth_at most recent
    in the last 60s, unrevoked, unexpired, optional username filter."""
    _check_gateway_secret(x_gateway_secret)
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    horizon = now - timedelta(seconds=60)

    q = select(GatewaySession).where(
        GatewaySession.revoked_at.is_(None),
        GatewaySession.expires_at > now,
        GatewaySession.last_auth_at.is_not(None),
        GatewaySession.last_auth_at >= horizon,
    )
    if payload.session_id is not None:
        q = q.where(GatewaySession.id == payload.session_id)
    if payload.username:
        q = q.where(GatewaySession.ssh_username == payload.username)
    if payload.client_ip:
        q = q.where(GatewaySession.client_ip == payload.client_ip)

    q = q.order_by(GatewaySession.last_auth_at.desc()).limit(1)
    sess = (await db.execute(q)).scalar_one_or_none()
    if sess is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"code": "NO_RECENT_AUTH"}
        )
    return {
        "session_id": str(sess.id),
        "target_user": sess.target_user,
        "target_host": str(sess.target_host),
        "target_port": sess.target_port,
        "expires_at": sess.expires_at.isoformat(),
    }


@gateway_router.post("/session-start")
async def gateway_session_start(
    payload: SessionStartRequest,
    x_gateway_secret: str | None = Header(default=None, alias="X-Gateway-Secret"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _check_gateway_secret(x_gateway_secret)
    sess = (
        await db.execute(
            select(GatewaySession).where(GatewaySession.id == payload.session_id)
        )
    ).scalar_one_or_none()
    if sess is None or sess.revoked_at is not None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"code": "SESSION_NOT_ACTIVE"}
        )
    sess.active_pid = payload.pid
    if payload.pty_path:
        sess.pty_path = payload.pty_path[:64]
    if payload.client_ip:
        sess.client_ip = payload.client_ip
    await db.commit()
    return {"ok": True}


@gateway_router.post("/session-end")
async def gateway_session_end(
    payload: SessionEndRequest,
    x_gateway_secret: str | None = Header(default=None, alias="X-Gateway-Secret"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _check_gateway_secret(x_gateway_secret)
    sess = (
        await db.execute(
            select(GatewaySession).where(GatewaySession.id == payload.session_id)
        )
    ).scalar_one_or_none()
    if sess is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"code": "SESSION_NOT_FOUND"}
        )
    sess.bytes_in = (sess.bytes_in or 0) + max(0, payload.bytes_in)
    sess.bytes_out = (sess.bytes_out or 0) + max(0, payload.bytes_out)
    sess.active_pid = None
    await db.commit()
    return {"ok": True}
