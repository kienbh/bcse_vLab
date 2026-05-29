"""VPS access endpoints — long-running (up to 30 days) grants.

Three audiences:
  - Student        : create / cancel / list own requests; list active grants;
                     POST /vps/{id}/access to mint a gateway session.
  - Lecturer/admin : grant directly, revoke, list grants for a device,
                     decide pending requests.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_lecturer
from app.api.routes.gateway import AccessIssueResponse, _build_ssh_command, _issue_or_rotate
from app.core.config import get_settings
from app.core.db import get_db
from app.models import (
    AccessRequest,
    AccessRequestStatus,
    Booking,
    BookingStatus,
    Device,
    DeviceType,
    GatewaySession,
    SpecialAccess,
    User,
    UserRole,
)
from app.schemas import (
    AccessRequestCreate,
    AccessRequestDecide,
    AccessRequestOut,
    BlockBookingCreate,
    BlockBookingOut,
    VpsGrantCreate,
    VpsGrantOut,
)
from app.services import gateway_credentials
from app.services import vps_access as svc
from app.services import vps_admin as admin_svc
from app.services import vps_block_booking as block_svc
from app.services.audit import audit_log
from app.services.notifier import send_proposal_email

router = APIRouter(prefix="/vps-access", tags=["vps-access"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ar_out(ar: AccessRequest, *, student: User | None, device: Device | None) -> AccessRequestOut:
    return AccessRequestOut(
        id=ar.id,
        student_id=ar.student_id,
        device_id=ar.device_id,
        requested_from=ar.requested_from,
        requested_to=ar.requested_to,
        reason=ar.reason,
        status=ar.status.value,
        decided_by=ar.decided_by,
        decided_at=ar.decided_at,
        decision_note=ar.decision_note,
        granted_access_id=ar.granted_access_id,
        created_at=ar.created_at,
        student_email=student.email if student else None,
        student_name=student.full_name if student else None,
        device_name=device.name if device else None,
    )


def _grant_out(sa: SpecialAccess, *, student: User | None, device: Device | None) -> VpsGrantOut:
    return VpsGrantOut(
        id=sa.id,
        user_id=sa.user_id,
        device_id=sa.device_id,
        valid_from=sa.valid_from,
        valid_to=sa.valid_to,
        reason=sa.reason,
        granted_by=sa.granted_by,
        granted_at=sa.granted_at,
        revoked_at=sa.revoked_at,
        student_email=student.email if student else None,
        student_name=student.full_name if student else None,
        device_name=device.name if device else None,
    )


async def _hydrate_request(db: AsyncSession, rows: list[AccessRequest]) -> list[AccessRequestOut]:
    if not rows:
        return []
    user_ids = {r.student_id for r in rows}
    dev_ids = {r.device_id for r in rows}
    users = {
        u.id: u
        for u in (
            await db.execute(select(User).where(User.id.in_(user_ids)))
        ).scalars()
    }
    devs = {
        d.id: d
        for d in (
            await db.execute(select(Device).where(Device.id.in_(dev_ids)))
        ).scalars()
    }
    return [_ar_out(r, student=users.get(r.student_id), device=devs.get(r.device_id)) for r in rows]


async def _hydrate_grants(db: AsyncSession, rows: list[SpecialAccess]) -> list[VpsGrantOut]:
    if not rows:
        return []
    user_ids = {r.user_id for r in rows}
    dev_ids = {r.device_id for r in rows}
    users = {
        u.id: u
        for u in (
            await db.execute(select(User).where(User.id.in_(user_ids)))
        ).scalars()
    }
    devs = {
        d.id: d
        for d in (
            await db.execute(select(Device).where(Device.id.in_(dev_ids)))
        ).scalars()
    }
    return [_grant_out(r, student=users.get(r.user_id), device=devs.get(r.device_id)) for r in rows]


def _svc_to_http(err: svc.VpsAccessError) -> HTTPException:
    mapping = {
        "DEVICE_NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "NOT_A_VPS": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "WINDOW_TOO_LONG": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "INVALID_TIME_RANGE": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "PAST_WINDOW": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "REQUEST_ALREADY_DECIDED": status.HTTP_409_CONFLICT,
        "STUDENT_GONE": status.HTTP_404_NOT_FOUND,
        "NOT_OWN_REQUEST": status.HTTP_403_FORBIDDEN,
        "RESERVED_ADMIN_ONLY": status.HTTP_403_FORBIDDEN,
        "RESERVED_DEVICE": status.HTTP_403_FORBIDDEN,
    }
    return HTTPException(
        mapping.get(err.code, status.HTTP_400_BAD_REQUEST),
        detail={"code": err.code, "message": str(err), **err.details},
    )


# ---------------------------------------------------------------------------
# Student endpoints
# ---------------------------------------------------------------------------


@router.post("/requests", response_model=AccessRequestOut, status_code=status.HTTP_201_CREATED)
async def create_request(
    payload: AccessRequestCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AccessRequestOut:
    try:
        device = await svc._ensure_vps(db, payload.device_id)
        svc._ensure_window(payload.requested_from, payload.requested_to)
    except svc.VpsAccessError as e:
        raise _svc_to_http(e)

    if device.reserved:
        # ESAS-BCSE-managed VPS — students can't request; admin grants directly.
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "RESERVED_DEVICE",
                "message": (
                    f"VPS {device.name} do {device.managed_by or 'ESAS-BCSE'} quản lý — "
                    "không gửi yêu cầu được. Liên hệ admin để được cấp quyền."
                ),
            },
        )

    ar = AccessRequest(
        student_id=user.id,
        device_id=payload.device_id,
        requested_from=payload.requested_from,
        requested_to=payload.requested_to,
        reason=payload.reason,
        status=AccessRequestStatus.PENDING,
    )
    db.add(ar)
    await db.flush()
    await audit_log(
        db,
        actor=user,
        action="vps_access.request.create",
        target_type="access_request",
        target_id=str(ar.id),
        details={"device_name": device.name, "days": (payload.requested_to - payload.requested_from).days},
        request=request,
    )
    await db.commit()
    await db.refresh(ar)
    # Notify the lecturer by email — best-effort, doesn't block the API on
    # SMTP failure (the request row is the source of truth).
    try:
        await send_proposal_email(
            student_email=user.email,
            student_name=user.full_name or user.email,
            student_code=user.student_code,
            device_name=device.name,
            requested_from=ar.requested_from.strftime("%d/%m/%Y"),
            requested_to=ar.requested_to.strftime("%d/%m/%Y"),
            reason=ar.reason,
            request_id=str(ar.id),
        )
    except Exception:
        pass
    return _ar_out(ar, student=user, device=device)


@router.get("/requests/mine", response_model=list[AccessRequestOut])
async def my_requests(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AccessRequestOut]:
    rows = list(
        (
            await db.execute(
                select(AccessRequest)
                .where(AccessRequest.student_id == user.id)
                .order_by(AccessRequest.created_at.desc())
            )
        ).scalars()
    )
    return await _hydrate_request(db, rows)


@router.post("/requests/{request_id}/cancel", response_model=AccessRequestOut)
async def cancel_my_request(
    request_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AccessRequestOut:
    ar = (
        await db.execute(select(AccessRequest).where(AccessRequest.id == request_id))
    ).scalar_one_or_none()
    if ar is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "REQUEST_NOT_FOUND"})
    try:
        await svc.cancel_request(db, request=ar, by=user)
    except svc.VpsAccessError as e:
        raise _svc_to_http(e)
    await audit_log(
        db,
        actor=user,
        action="vps_access.request.cancel",
        target_type="access_request",
        target_id=str(ar.id),
        request=request,
    )
    await db.commit()
    await db.refresh(ar)
    device = (await db.execute(select(Device).where(Device.id == ar.device_id))).scalar_one_or_none()
    return _ar_out(ar, student=user, device=device)


@router.get("/grants/mine", response_model=list[VpsGrantOut])
async def my_grants(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    active_only: bool = Query(default=False),
) -> list[VpsGrantOut]:
    q = (
        select(SpecialAccess)
        .join(Device, Device.id == SpecialAccess.device_id)
        .where(
            SpecialAccess.user_id == user.id,
            Device.device_type == DeviceType.VPS,
        )
        .order_by(SpecialAccess.granted_at.desc())
    )
    if active_only:
        now = datetime.now(timezone.utc)
        q = q.where(
            SpecialAccess.revoked_at.is_(None),
            SpecialAccess.valid_from <= now,
            SpecialAccess.valid_to >= now,
        )
    rows = list((await db.execute(q)).scalars())
    return await _hydrate_grants(db, rows)


@router.post("/{device_id}/access", response_model=AccessIssueResponse)
async def connect_to_vps(
    device_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AccessIssueResponse:
    """Mint (or return) a gateway session for the student's VPS access.

    Two valid access paths, checked in order:
      1. Active auto-booked block (self-service 4h slot, currently running).
         Booking already exists, we just mint the gateway session on it.
      2. Long-running SpecialAccess (≤30-day proposal-approved grant).
         We auto-create a session-spanning Booking (existing behaviour).

    No path → 403 with a hint pointing to the booking calendar.
    """
    # Path 1: live block-booking
    active_block = await block_svc.active_auto_block_for(
        db, student_id=user.id, device_id=device_id
    )
    if active_block is not None:
        return await _issue_or_rotate(
            db,
            booking=active_block,
            user=user,
            request=request,
            action="gateway.access.issue.vps.block",
        )

    # Path 2: long grant
    sa = await svc.active_grant_for(db, student_id=user.id, device_id=device_id)
    if sa is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "NO_ACTIVE_GRANT",
                "hint": (
                    "Bạn chưa có block nào đang chạy trên VPS này. "
                    "Mở lịch để đặt block 4h, hoặc gửi proposal cho block dài (>24h)."
                ),
            },
        )
    booking = await svc.get_or_create_session_booking(db, student=user, sa=sa)
    return await _issue_or_rotate(
        db,
        booking=booking,
        user=user,
        request=request,
        action="gateway.access.issue.vps",
    )


# ---------------------------------------------------------------------------
# Block booking — self-service 4h slots with round-robin fairness
# ---------------------------------------------------------------------------


def _block_svc_to_http(err: block_svc.BlockBookingError) -> HTTPException:
    mapping = {
        "DEVICE_NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "BOOKING_NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "NOT_A_VPS": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "NOT_BLOCK_ALIGNED": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "INVALID_TIME_RANGE": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "DURATION_NOT_MULTIPLE_OF_BLOCK": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "ZERO_BLOCKS": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "EXCEEDS_AUTO_LIMIT": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "PAST_BLOCK": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "BLOCK_TAKEN": status.HTTP_409_CONFLICT,
        "ALREADY_HOLDING_BLOCK": status.HTTP_409_CONFLICT,
        "NOT_AN_AUTO_BLOCK": status.HTTP_409_CONFLICT,
        "NOT_CANCELLABLE": status.HTTP_409_CONFLICT,
        "ALREADY_ENDED": status.HTTP_409_CONFLICT,
        "VPS_OFFLINE": status.HTTP_503_SERVICE_UNAVAILABLE,
        "VPS_MAINTENANCE": status.HTTP_503_SERVICE_UNAVAILABLE,
        "RESERVED_DEVICE": status.HTTP_403_FORBIDDEN,
    }
    return HTTPException(
        mapping.get(err.code, status.HTTP_400_BAD_REQUEST),
        detail={"code": err.code, "message": str(err), **err.details},
    )


def _block_out(b: Booking, *, owner: User | None, viewer_id: UUID) -> BlockBookingOut:
    return BlockBookingOut(
        id=b.id,
        user_id=b.user_id,
        device_id=b.device_id,
        start_time=b.start_time,
        end_time=b.end_time,
        status=b.status.value,
        granted_via=b.granted_via.value,
        student_email=owner.email if owner else None,
        student_name=owner.full_name if owner else None,
        is_mine=(b.user_id == viewer_id),
    )


@router.post(
    "/{device_id}/blocks/current",
    response_model=BlockBookingOut,
    status_code=status.HTTP_201_CREATED,
)
async def book_current_block(
    device_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BlockBookingOut:
    """Book the CURRENT 4h block on this VPS for the calling student.

    No payload — the backend computes the window from the server clock so
    the front-end can't accidentally drift / send a future block. The single-
    block-at-a-time rule is enforced inside `book_block`.
    """
    cur_start, cur_end = block_svc.current_block_window()
    try:
        booking = await block_svc.book_block(
            db,
            student=user,
            device_id=device_id,
            start_time=cur_start,
            end_time=cur_end,
        )
    except block_svc.BlockBookingError as e:
        raise _block_svc_to_http(e)
    await audit_log(
        db,
        actor=user,
        action="vps_block.book_current",
        target_type="booking",
        target_id=str(booking.id),
        details={
            "device_id": str(device_id),
            "start_time": booking.start_time.isoformat(),
            "end_time": booking.end_time.isoformat(),
        },
        request=request,
    )
    await db.commit()
    await db.refresh(booking)
    return _block_out(booking, owner=user, viewer_id=user.id)


@router.post("/{device_id}/blocks", response_model=BlockBookingOut, status_code=status.HTTP_201_CREATED)
async def book_block(
    device_id: UUID,
    payload: BlockBookingCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BlockBookingOut:
    """Self-book a 4h-aligned block on a VPS (must be the current block window)."""
    try:
        booking = await block_svc.book_block(
            db,
            student=user,
            device_id=device_id,
            start_time=payload.start_time,
            end_time=payload.end_time,
        )
    except block_svc.BlockBookingError as e:
        raise _block_svc_to_http(e)
    await audit_log(
        db,
        actor=user,
        action="vps_block.book",
        target_type="booking",
        target_id=str(booking.id),
        details={
            "device_id": str(device_id),
            "start_time": booking.start_time.isoformat(),
            "end_time": booking.end_time.isoformat(),
        },
        request=request,
    )
    await db.commit()
    await db.refresh(booking)
    return _block_out(booking, owner=user, viewer_id=user.id)


@router.delete("/{device_id}/blocks/{booking_id}")
async def cancel_block(
    device_id: UUID,
    booking_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        booking = await block_svc.cancel_block(db, student=user, booking_id=booking_id)
    except block_svc.BlockBookingError as e:
        raise _block_svc_to_http(e)
    await audit_log(
        db,
        actor=user,
        action="vps_block.cancel",
        target_type="booking",
        target_id=str(booking.id),
        request=request,
    )
    await db.commit()
    return {"status": "cancelled", "booking_id": str(booking.id)}


@router.get("/{device_id}/blocks", response_model=list[BlockBookingOut])
async def list_blocks(
    device_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    days: int = Query(default=7, ge=1, le=30),
) -> list[BlockBookingOut]:
    """All scheduled+active bookings on this VPS for the next N days —
    used to paint the calendar. Includes auto blocks AND any spans created
    from SpecialAccess so students see "this VPS is in use" even outside
    their own bookings."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    rows = await block_svc.schedule_for_device(
        db, device_id=device_id, range_from=now, range_to=now + timedelta(days=days)
    )
    if not rows:
        return []
    user_ids = {b.user_id for b in rows}
    owners = {
        u.id: u
        for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars()
    }
    return [_block_out(b, owner=owners.get(b.user_id), viewer_id=user.id) for b in rows]


@router.get("/blocks/mine", response_model=list[BlockBookingOut])
async def my_blocks(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[BlockBookingOut]:
    """SV's own future-or-active auto blocks across all VPS — for /vps-access page."""
    from datetime import datetime, timezone
    from app.models import BookingGrantedVia, BookingStatus
    now = datetime.now(timezone.utc)
    rows = list(
        (
            await db.execute(
                select(Booking)
                .where(
                    Booking.user_id == user.id,
                    Booking.granted_via == BookingGrantedVia.AUTO,
                    Booking.status.in_(
                        [BookingStatus.SCHEDULED, BookingStatus.ACTIVE]
                    ),
                    Booking.end_time > now,
                )
                .order_by(Booking.start_time.asc())
            )
        ).scalars()
    )
    return [_block_out(b, owner=user, viewer_id=user.id) for b in rows]


# ---------------------------------------------------------------------------
# Lecturer / admin endpoints
# ---------------------------------------------------------------------------


@router.get("/requests", response_model=list[AccessRequestOut])
async def list_requests(
    _: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
    status_filter: str | None = Query(default="pending", alias="status"),
) -> list[AccessRequestOut]:
    q = select(AccessRequest).order_by(AccessRequest.created_at.desc())
    if status_filter and status_filter != "all":
        try:
            q = q.where(AccessRequest.status == AccessRequestStatus(status_filter))
        except ValueError:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "BAD_STATUS_FILTER"}
            )
    rows = list((await db.execute(q)).scalars())
    return await _hydrate_request(db, rows)


@router.post("/requests/{request_id}/approve", response_model=AccessRequestOut)
async def approve(
    request_id: UUID,
    payload: AccessRequestDecide,
    request: Request,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> AccessRequestOut:
    ar = (
        await db.execute(select(AccessRequest).where(AccessRequest.id == request_id))
    ).scalar_one_or_none()
    if ar is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "REQUEST_NOT_FOUND"})
    try:
        sa = await svc.approve_request(
            db,
            request=ar,
            approver=user,
            decision_note=payload.decision_note,
            override_from=payload.override_from,
            override_to=payload.override_to,
        )
    except svc.VpsAccessError as e:
        raise _svc_to_http(e)
    await audit_log(
        db,
        actor=user,
        action="vps_access.request.approve",
        target_type="access_request",
        target_id=str(ar.id),
        details={
            "granted_access_id": str(sa.id),
            "valid_from": sa.valid_from.isoformat(),
            "valid_to": sa.valid_to.isoformat(),
        },
        request=request,
    )
    await db.commit()
    await db.refresh(ar)
    student = (await db.execute(select(User).where(User.id == ar.student_id))).scalar_one_or_none()
    device = (await db.execute(select(Device).where(Device.id == ar.device_id))).scalar_one_or_none()
    return _ar_out(ar, student=student, device=device)


@router.post("/requests/{request_id}/reject", response_model=AccessRequestOut)
async def reject(
    request_id: UUID,
    payload: AccessRequestDecide,
    request: Request,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> AccessRequestOut:
    ar = (
        await db.execute(select(AccessRequest).where(AccessRequest.id == request_id))
    ).scalar_one_or_none()
    if ar is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "REQUEST_NOT_FOUND"})
    try:
        await svc.reject_request(
            db, request=ar, approver=user, decision_note=payload.decision_note
        )
    except svc.VpsAccessError as e:
        raise _svc_to_http(e)
    await audit_log(
        db,
        actor=user,
        action="vps_access.request.reject",
        target_type="access_request",
        target_id=str(ar.id),
        details={"note": payload.decision_note},
        request=request,
    )
    await db.commit()
    await db.refresh(ar)
    student = (await db.execute(select(User).where(User.id == ar.student_id))).scalar_one_or_none()
    device = (await db.execute(select(Device).where(Device.id == ar.device_id))).scalar_one_or_none()
    return _ar_out(ar, student=student, device=device)


@router.post("/grants", response_model=VpsGrantOut, status_code=status.HTTP_201_CREATED)
async def grant_direct(
    payload: VpsGrantCreate,
    request: Request,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> VpsGrantOut:
    student = (
        await db.execute(select(User).where(User.email == payload.user_email.lower()))
    ).scalar_one_or_none()
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "USER_NOT_FOUND"})
    if student.role != UserRole.STUDENT:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "NOT_A_STUDENT", "role": student.role.value},
        )
    try:
        sa = await svc.grant_vps_access(
            db,
            granter=user,
            student=student,
            device_id=payload.device_id,
            valid_from=payload.valid_from,
            valid_to=payload.valid_to,
            reason=payload.reason,
        )
    except svc.VpsAccessError as e:
        raise _svc_to_http(e)
    await audit_log(
        db,
        actor=user,
        action="vps_access.grant.create",
        target_type="special_access",
        target_id=str(sa.id),
        details={
            "student_email": student.email,
            "device_id": str(payload.device_id),
            "valid_from": sa.valid_from.isoformat(),
            "valid_to": sa.valid_to.isoformat(),
        },
        request=request,
    )
    await db.commit()
    await db.refresh(sa)
    device = (await db.execute(select(Device).where(Device.id == sa.device_id))).scalar_one_or_none()
    return _grant_out(sa, student=student, device=device)


@router.get("/grants", response_model=list[VpsGrantOut])
async def list_grants(
    _: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
    device_id: UUID | None = Query(default=None),
    active_only: bool = Query(default=True),
) -> list[VpsGrantOut]:
    q = (
        select(SpecialAccess)
        .join(Device, Device.id == SpecialAccess.device_id)
        .where(Device.device_type == DeviceType.VPS)
        .order_by(SpecialAccess.granted_at.desc())
    )
    if device_id:
        q = q.where(SpecialAccess.device_id == device_id)
    if active_only:
        now = datetime.now(timezone.utc)
        q = q.where(
            SpecialAccess.revoked_at.is_(None),
            SpecialAccess.valid_to >= now,
        )
    rows = list((await db.execute(q)).scalars())
    return await _hydrate_grants(db, rows)


@router.post("/admin/{device_id}/cleanup")
async def cleanup_vps(
    device_id: UUID,
    request: Request,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
    force: bool = Query(default=False),
) -> dict:
    """Light cleanup of a VPS (rm /home/<user>/* except .ssh, /tmp, apt clean,
    docker restart). Refuses if anyone has an active gateway session, unless
    `?force=true`. Admin/lecturer only."""
    try:
        result = await admin_svc.cleanup_vps(db, device_id=device_id, force=force)
    except admin_svc.VpsAdminError as e:
        mapping = {
            "DEVICE_NOT_FOUND": status.HTTP_404_NOT_FOUND,
            "NOT_A_VPS": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "ACTIVE_SESSION": status.HTTP_409_CONFLICT,
            "MISSING_BACKEND_KEY": status.HTTP_500_INTERNAL_SERVER_ERROR,
        }
        raise HTTPException(
            mapping.get(e.code, status.HTTP_400_BAD_REQUEST),
            detail={"code": e.code, "message": str(e), **e.details},
        )
    await audit_log(
        db,
        actor=user,
        action="vps_admin.cleanup",
        target_type="device",
        target_id=str(device_id),
        details={
            "force": force,
            "status": result["status"],
            "duration_seconds": result["duration_seconds"],
        },
        success=result["status"] == "ok",
        request=request,
    )
    await db.commit()
    return result


@router.delete("/grants/{grant_id}")
async def revoke_grant(
    grant_id: UUID,
    request: Request,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    sa = (
        await db.execute(select(SpecialAccess).where(SpecialAccess.id == grant_id))
    ).scalar_one_or_none()
    if sa is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "GRANT_NOT_FOUND"})
    now = datetime.now(timezone.utc)
    if sa.revoked_at is None:
        sa.revoked_at = now
        sa.revoked_by = user.id

    # Free the device immediately: the SA→gateway flow auto-creates a Booking
    # spanning the grant window (get_or_create_session_booking). Revoking the
    # grant alone leaves that booking SCHEDULED/ACTIVE, so /live-status keeps
    # painting the student as "occupying" the VPS and the gateway session stays
    # valid until expiry. Cancel the spanning booking(s) + revoke the live
    # session so the card frees up and SSH is cut now. Runs even if the grant
    # was already revoked (idempotent repair of any orphaned booking/session).
    bookings = list(
        (
            await db.execute(
                select(Booking).where(
                    Booking.special_access_id == sa.id,
                    Booking.status.in_(
                        [BookingStatus.SCHEDULED, BookingStatus.ACTIVE]
                    ),
                )
            )
        ).scalars()
    )
    for b in bookings:
        b.status = BookingStatus.CANCELLED
        sess = (
            await db.execute(
                select(GatewaySession).where(GatewaySession.booking_id == b.id)
            )
        ).scalar_one_or_none()
        if sess is not None:
            await gateway_credentials.revoke(db, sess, reason="grant revoked")

    await audit_log(
        db,
        actor=user,
        action="vps_access.grant.revoke",
        target_type="special_access",
        target_id=str(sa.id),
        details={"bookings_cancelled": len(bookings)},
        request=request,
    )
    await db.commit()
    return {
        "status": "revoked",
        "grant_id": str(sa.id),
        "bookings_cancelled": len(bookings),
    }
