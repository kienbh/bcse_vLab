"""Reset request queue endpoints — user submits, admin/lecturer approves.

Workflow (per thầy 2026-05-15):
- Student requests reset → queue with status=pending
- Auto-approve heuristic: if requester IS the current booker AND there's no
  recent reset on this device (last 10 min), skip the queue and run the plug
  cycle immediately. Otherwise wait for admin/lecturer.
- Admin can approve any request. Lecturer can approve requests whose requester
  is enrolled in one of their classes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models import (
    Booking,
    BookingStatus,
    Class,
    ClassDeviceAssignment,
    Device,
    Enrollment,
    PlugMapping,
    ResetRequest,
    ResetRequestStatus,
    SpecialAccess,
    User,
    UserRole,
)
from app.schemas import ResetRequestCreate, ResetRequestDecide, ResetRequestOut
from app.services import event_bus
from app.services.audit import audit_log
from app.services.plug_controller import make_adapter

router = APIRouter(prefix="/reset-requests", tags=["reset-requests"])

_AUTO_APPROVE_WINDOW = timedelta(minutes=10)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _serialize(
    db: AsyncSession, req: ResetRequest
) -> ResetRequestOut:
    requester = (
        await db.execute(select(User).where(User.id == req.requester_id))
    ).scalar_one()
    device = (
        await db.execute(select(Device).where(Device.id == req.device_id))
    ).scalar_one()
    display = (
        requester.student_code
        or requester.full_name
        or requester.email.split("@")[0]
    )
    return ResetRequestOut(
        id=req.id,
        requester_id=req.requester_id,
        requester_display=display,
        device_id=req.device_id,
        device_name=device.name,
        booking_id=req.booking_id,
        reason=req.reason,
        status=req.status,
        requested_at=req.requested_at,
        decided_by=req.decided_by,
        decided_at=req.decided_at,
        decision_note=req.decision_note,
        completed_at=req.completed_at,
        auto_approved=req.decided_by is None
        and req.status != ResetRequestStatus.PENDING,
    )


async def _find_current_booking(
    db: AsyncSession, *, user_id: UUID, device_id: UUID
) -> Booking | None:
    now = _utcnow()
    res = await db.execute(
        select(Booking).where(
            Booking.user_id == user_id,
            Booking.device_id == device_id,
            Booking.status.in_([BookingStatus.SCHEDULED, BookingStatus.ACTIVE]),
            Booking.start_time <= now,
            Booking.end_time > now,
        ).limit(1)
    )
    return res.scalar_one_or_none()


async def _user_has_access_to_device(
    db: AsyncSession, *, user: User, device_id: UUID
) -> bool:
    """Privileged roles always; students need class or special_access link."""
    if user.role in (UserRole.ADMIN, UserRole.LECTURER):
        return True
    res = await db.execute(
        select(ClassDeviceAssignment.id)
        .join(Class, Class.id == ClassDeviceAssignment.class_id)
        .join(Enrollment, Enrollment.class_id == Class.id)
        .where(
            Enrollment.user_id == user.id,
            Enrollment.is_active.is_(True),
            ClassDeviceAssignment.device_id == device_id,
            ClassDeviceAssignment.revoked_at.is_(None),
        )
        .limit(1)
    )
    if res.first() is not None:
        return True
    res = await db.execute(
        select(SpecialAccess.id).where(
            SpecialAccess.user_id == user.id,
            SpecialAccess.device_id == device_id,
            SpecialAccess.revoked_at.is_(None),
        ).limit(1)
    )
    return res.first() is not None


async def _lecturer_owns_requester(
    db: AsyncSession, *, lecturer_id: UUID, requester_id: UUID
) -> bool:
    """True if `requester` is enrolled in any class taught by `lecturer`."""
    res = await db.execute(
        select(Enrollment.id)
        .join(Class, Class.id == Enrollment.class_id)
        .where(
            Class.lecturer_id == lecturer_id,
            Enrollment.user_id == requester_id,
            Enrollment.is_active.is_(True),
        )
        .limit(1)
    )
    return res.first() is not None


async def _can_decide(
    db: AsyncSession, *, deciders: User, req: ResetRequest
) -> bool:
    if deciders.role == UserRole.ADMIN:
        return True
    if deciders.role == UserRole.LECTURER:
        return await _lecturer_owns_requester(
            db, lecturer_id=deciders.id, requester_id=req.requester_id
        )
    return False


async def _trigger_plug_cycle(
    db: AsyncSession, *, device_id: UUID
) -> tuple[bool, dict]:
    """Returns (success, plug_result dict). Does NOT commit."""
    plug = (
        await db.execute(
            select(PlugMapping).where(PlugMapping.device_id == device_id)
        )
    ).scalar_one_or_none()
    if plug is None:
        return False, {"error": "NO_PLUG_MAPPED"}
    adapter = make_adapter(
        plug_type=plug.plug_type,
        plug_ip=str(plug.plug_ip),
        relay=plug.plug_relay_index,
        token=plug.api_token,
    )
    try:
        state = await adapter.power_cycle(off_seconds=5)
        return True, {"powered_on": state.on, "raw": state.raw}
    except Exception as e:
        return False, {"error": str(e)}


@router.post("", response_model=ResetRequestOut, status_code=status.HTTP_201_CREATED)
async def create_reset_request(
    payload: ResetRequestCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResetRequestOut:
    # 1. Device must exist
    device = (
        await db.execute(select(Device).where(Device.id == payload.device_id))
    ).scalar_one_or_none()
    if device is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"code": "DEVICE_NOT_FOUND"}
        )

    # 2. User must have access to the device
    if not await _user_has_access_to_device(db, user=user, device_id=payload.device_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "ACCESS_DENIED",
                "hint": "Bạn chưa được cấp quyền cho thiết bị này.",
            },
        )

    # 3. Reject if there's already a pending request on the same device — avoid spam
    existing = (
        await db.execute(
            select(ResetRequest).where(
                ResetRequest.device_id == payload.device_id,
                ResetRequest.status == ResetRequestStatus.PENDING,
            ).limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "REQUEST_ALREADY_PENDING",
                "hint": "Thiết bị này đã có 1 yêu cầu reset đang chờ admin/giảng viên duyệt.",
                "existing_id": str(existing.id),
            },
        )

    booking = await _find_current_booking(
        db, user_id=user.id, device_id=payload.device_id
    )

    # 4. Auto-approve heuristic: user is current booker AND no recent reset
    auto_eligible = False
    if booking is not None:
        recent_cutoff = _utcnow() - _AUTO_APPROVE_WINDOW
        recent = (
            await db.execute(
                select(ResetRequest).where(
                    ResetRequest.device_id == payload.device_id,
                    ResetRequest.requested_at >= recent_cutoff,
                    ResetRequest.status.in_(
                        [
                            ResetRequestStatus.COMPLETED,
                            ResetRequestStatus.APPROVED,
                            ResetRequestStatus.FAILED,
                        ]
                    ),
                ).limit(1)
            )
        ).scalar_one_or_none()
        if recent is None:
            auto_eligible = True

    req = ResetRequest(
        requester_id=user.id,
        device_id=payload.device_id,
        booking_id=booking.id if booking else None,
        reason=payload.reason,
        status=ResetRequestStatus.PENDING,
    )
    db.add(req)
    await db.flush()

    payload_event = {
        "id": str(req.id),
        "device_id": str(req.device_id),
        "device_name": device.name,
        "requester_id": str(user.id),
        "requester_display": user.student_code or user.full_name,
        "reason": req.reason,
        "auto_approved": False,
    }

    if auto_eligible:
        ok, plug_res = await _trigger_plug_cycle(db, device_id=payload.device_id)
        now = _utcnow()
        req.decided_at = now
        req.completed_at = now
        req.plug_result = plug_res
        req.status = (
            ResetRequestStatus.COMPLETED if ok else ResetRequestStatus.FAILED
        )
        # decided_by stays NULL — semantic: "auto-approved by system, no human gate"
        payload_event["auto_approved"] = True
        payload_event["status"] = req.status.value
        payload_event["plug_result"] = plug_res

    await audit_log(
        db,
        actor=user,
        action="reset.request.create",
        target_type="device",
        target_id=str(payload.device_id),
        details={
            "request_id": str(req.id),
            "reason": req.reason,
            "auto_approved": auto_eligible,
            "status": req.status.value,
        },
        request=request,
    )
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "DB_ERROR", "msg": str(e.orig)},
        )
    await db.refresh(req)

    # Notify
    if auto_eligible:
        # Tell the requester their auto-approve resolved
        event_bus.publish_to_user(user.id, "reset.decided", payload_event)
    else:
        # New pending request: notify admins + lecturers
        event_bus.publish_to_roles(
            [UserRole.ADMIN, UserRole.LECTURER], "reset.requested", payload_event
        )

    return await _serialize(db, req)


@router.get("", response_model=list[ResetRequestOut])
async def list_reset_requests(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    status_filter: ResetRequestStatus | None = Query(None, alias="status"),
    device_id: UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> list[ResetRequestOut]:
    q = select(ResetRequest)
    conds = []

    if user.role == UserRole.STUDENT:
        # Students only see their own requests
        conds.append(ResetRequest.requester_id == user.id)
    elif user.role == UserRole.LECTURER:
        # Lecturers see requests from their own students OR their own requests
        # (Lecturer can also be a requester for kits they manage)
        owned_requesters = (
            select(Enrollment.user_id)
            .join(Class, Class.id == Enrollment.class_id)
            .where(
                Class.lecturer_id == user.id,
                Enrollment.is_active.is_(True),
            )
        )
        conds.append(
            or_(
                ResetRequest.requester_id == user.id,
                ResetRequest.requester_id.in_(owned_requesters),
            )
        )
    # admin: no filter — sees everything

    if status_filter is not None:
        conds.append(ResetRequest.status == status_filter)
    if device_id is not None:
        conds.append(ResetRequest.device_id == device_id)

    if conds:
        q = q.where(and_(*conds))
    q = q.order_by(ResetRequest.requested_at.desc()).limit(limit)

    res = await db.execute(q)
    out: list[ResetRequestOut] = []
    for r in res.scalars().all():
        out.append(await _serialize(db, r))
    return out


@router.get("/pending/count")
async def pending_count(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Count of pending requests visible to this user. Used for the navbar
    'đèn sáng' badge on admin/lecturer accounts."""
    if user.role == UserRole.STUDENT:
        # Student sees only their own pending — useful for "your queue"
        res = await db.execute(
            select(ResetRequest).where(
                ResetRequest.requester_id == user.id,
                ResetRequest.status == ResetRequestStatus.PENDING,
            )
        )
        return {"count": len(res.scalars().all())}

    base = select(ResetRequest).where(ResetRequest.status == ResetRequestStatus.PENDING)
    if user.role == UserRole.LECTURER:
        owned_requesters = (
            select(Enrollment.user_id)
            .join(Class, Class.id == Enrollment.class_id)
            .where(
                Class.lecturer_id == user.id,
                Enrollment.is_active.is_(True),
            )
        )
        base = base.where(ResetRequest.requester_id.in_(owned_requesters))
    # admin: no extra filter
    res = await db.execute(base)
    return {"count": len(res.scalars().all())}


async def _decide(
    *,
    req_id: UUID,
    user: User,
    db: AsyncSession,
    request: Request,
    decision: Literal["approve", "reject"],
    note: str | None,
) -> ResetRequestOut:
    req = (
        await db.execute(select(ResetRequest).where(ResetRequest.id == req_id))
    ).scalar_one_or_none()
    if req is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"code": "REQUEST_NOT_FOUND"}
        )
    if req.status != ResetRequestStatus.PENDING:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "ALREADY_DECIDED", "current_status": req.status.value},
        )
    if not await _can_decide(db, deciders=user, req=req):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"code": "NOT_AUTHORIZED_TO_DECIDE"},
        )

    now = _utcnow()
    req.decided_by = user.id
    req.decided_at = now
    req.decision_note = note

    if decision == "reject":
        req.status = ResetRequestStatus.REJECTED
        plug_res = None
    else:
        ok, plug_res = await _trigger_plug_cycle(db, device_id=req.device_id)
        req.plug_result = plug_res
        req.completed_at = now
        req.status = (
            ResetRequestStatus.COMPLETED if ok else ResetRequestStatus.FAILED
        )

    await audit_log(
        db,
        actor=user,
        action=f"reset.request.{decision}",
        target_type="reset_request",
        target_id=str(req.id),
        details={
            "device_id": str(req.device_id),
            "requester_id": str(req.requester_id),
            "status": req.status.value,
            "plug_result": plug_res,
            "note": note,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(req)

    event_payload = {
        "id": str(req.id),
        "device_id": str(req.device_id),
        "status": req.status.value,
        "decided_by": str(user.id),
        "decision_note": note,
        "plug_result": plug_res,
    }
    event_bus.publish_to_user(req.requester_id, "reset.decided", event_payload)
    # Also let other admins/lecturers refresh their queue
    event_bus.publish_to_roles(
        [UserRole.ADMIN, UserRole.LECTURER], "reset.queue.updated", event_payload
    )

    return await _serialize(db, req)


@router.post("/{request_id}/approve", response_model=ResetRequestOut)
async def approve_request(
    request_id: UUID,
    payload: ResetRequestDecide,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResetRequestOut:
    return await _decide(
        req_id=request_id,
        user=user,
        db=db,
        request=request,
        decision="approve",
        note=payload.decision_note,
    )


@router.post("/{request_id}/reject", response_model=ResetRequestOut)
async def reject_request(
    request_id: UUID,
    payload: ResetRequestDecide,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResetRequestOut:
    return await _decide(
        req_id=request_id,
        user=user,
        db=db,
        request=request,
        decision="reject",
        note=payload.decision_note,
    )
