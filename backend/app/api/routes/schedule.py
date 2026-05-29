"""M6 runtime routes — student weekly schedule, connect-from-slot, ad-hoc
requests, and the lecturer/admin approval queue."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_lecturer
from app.core.db import get_db
from app.models import (
    Booking,
    BookingGrantedVia,
    BookingStatus,
    Class,
    Device,
    Enrollment,
    Group,
    PlannedSlot,
    User,
    UserRole,
)
from app.models.enums import TimeSlot
from app.schemas import (
    BookingOut,
    MyScheduleOut,
    MySlotOut,
    PendingRequestOut,
    RequestCreate,
    RequestDecide,
)
from app.services import event_bus
from app.services.audit import audit_log

router = APIRouter(tags=["schedule"])

# Fixed daily slots — local Asia/Ho_Chi_Minh wall-clock hours (no DST).
TIME_SLOT_HOURS: dict[TimeSlot, tuple[int, int]] = {
    TimeSlot.MORNING: (8, 12),
    TimeSlot.AFTERNOON: (13, 17),
    TimeSlot.EVENING: (18, 22),
}
_LOCAL_OFFSET = timedelta(hours=7)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hhmm(hour: int) -> str:
    return f"{hour:02d}:00"


def _is_live_now(slot: PlannedSlot, *, now_utc: datetime | None = None) -> bool:
    local = (now_utc or _utcnow()) + _LOCAL_OFFSET
    if local.isoweekday() != slot.day_of_week:
        return False
    start_h, end_h = TIME_SLOT_HOURS[slot.time_slot]
    return start_h <= local.hour < end_h


def _slot_window_today_utc(slot: PlannedSlot) -> tuple[datetime, datetime]:
    """UTC start/end of today's occurrence of this slot."""
    local = _utcnow() + _LOCAL_OFFSET
    start_h, end_h = TIME_SLOT_HOURS[slot.time_slot]
    local_start = local.replace(hour=start_h, minute=0, second=0, microsecond=0)
    local_end = local.replace(hour=end_h, minute=0, second=0, microsecond=0)
    return (local_start - _LOCAL_OFFSET, local_end - _LOCAL_OFFSET)


async def _my_group(
    db: AsyncSession, user: User
) -> tuple[Enrollment, Group, Class] | None:
    """The student's active enrollment that has a group — they're in one group."""
    return (
        await db.execute(
            select(Enrollment, Group, Class)
            .join(Group, Enrollment.group_id == Group.id)
            .join(Class, Enrollment.class_id == Class.id)
            .where(Enrollment.user_id == user.id, Enrollment.is_active.is_(True))
            .limit(1)
        )
    ).first()


async def _led_group(db: AsyncSession, user: User) -> tuple[Group, Class] | None:
    """The group this user leads (if any), with its class."""
    return (
        await db.execute(
            select(Group, Class)
            .join(Class, Group.class_id == Class.id)
            .where(Group.leader_id == user.id)
            .limit(1)
        )
    ).first()


# -------- student: my weekly schedule ---------------------------------------

@router.get("/my/schedule", response_model=MyScheduleOut)
async def my_schedule(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MyScheduleOut:
    """The student's group + its weekly planned slots, with live-now flags."""
    ctx = await _my_group(db, user)
    if ctx is None:
        return MyScheduleOut()
    _enr, group, cls = ctx
    rows = (
        await db.execute(
            select(PlannedSlot, Device)
            .join(Device, PlannedSlot.device_id == Device.id)
            .where(PlannedSlot.group_id == group.id)
            .order_by(PlannedSlot.day_of_week, PlannedSlot.time_slot)
        )
    ).all()
    now = _utcnow()
    slots = [
        MySlotOut(
            id=ps.id,
            device_id=ps.device_id,
            device_name=dev.name,
            day_of_week=ps.day_of_week,
            time_slot=ps.time_slot,
            starts_hhmm=_hhmm(TIME_SLOT_HOURS[ps.time_slot][0]),
            ends_hhmm=_hhmm(TIME_SLOT_HOURS[ps.time_slot][1]),
            is_live_now=_is_live_now(ps, now_utc=now),
        )
        for ps, dev in rows
    ]
    return MyScheduleOut(
        class_id=cls.id,
        class_name=cls.name,
        group_id=group.id,
        group_name=group.name,
        is_leader=(group.leader_id == user.id),
        slots=slots,
    )


# -------- student (leader): start a live planned slot -----------------------

@router.post("/planned-slots/{slot_id}/start", response_model=BookingOut)
async def start_planned_slot(
    slot_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Booking:
    """Group leader starts a live planned slot — materializes a Booking that
    the leader then connects to via POST /bookings/{id}/access."""
    row = (
        await db.execute(
            select(PlannedSlot, Group)
            .join(Group, PlannedSlot.group_id == Group.id)
            .where(PlannedSlot.id == slot_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "SLOT_NOT_FOUND"})
    slot, group = row
    if group.leader_id != user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"code": "NOT_GROUP_LEADER",
                    "hint": "Chỉ nhóm trưởng được kết nối cho nhóm."},
        )
    if not _is_live_now(slot):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "SLOT_NOT_LIVE", "hint": "Chưa tới ca của nhóm bạn."},
        )
    start_utc, end_utc = _slot_window_today_utc(slot)
    existing = (
        await db.execute(
            select(Booking)
            .where(
                Booking.planned_slot_id == slot.id,
                Booking.start_time == start_utc,
                Booking.status.in_([BookingStatus.SCHEDULED, BookingStatus.ACTIVE]),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    booking = Booking(
        user_id=user.id,
        device_id=slot.device_id,
        granted_via=BookingGrantedVia.CLASS,
        class_id=slot.class_id,
        start_time=start_utc,
        end_time=end_utc,
        status=BookingStatus.ACTIVE,
        planned_slot_id=slot.id,
    )
    db.add(booking)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "DEVICE_BUSY", "hint": "Kit đang có phiên khác."},
        )
    await audit_log(
        db, actor=user, action="slot.start", target_type="booking",
        target_id=booking.id, details={"planned_slot_id": str(slot.id)},
        request=request,
    )
    await db.commit()
    return booking


# -------- student (leader): ad-hoc out-of-plan request ----------------------

@router.post("/requests", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
async def create_request(
    payload: RequestCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Booking:
    """A group leader submits an ad-hoc usage request — pending until a
    lecturer/admin approves or rejects it."""
    led = await _led_group(db, user)
    if led is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"code": "NOT_GROUP_LEADER",
                    "hint": "Chỉ nhóm trưởng được gửi đề xuất."},
        )
    _group, cls = led
    if payload.end_time <= payload.start_time:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "BAD_TIME_RANGE"}
        )
    device = (
        await db.execute(select(Device).where(Device.id == payload.device_id))
    ).scalar_one_or_none()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "DEVICE_NOT_FOUND"})
    booking = Booking(
        user_id=user.id,
        device_id=device.id,
        granted_via=BookingGrantedVia.CLASS,
        class_id=cls.id,
        start_time=payload.start_time,
        end_time=payload.end_time,
        status=BookingStatus.PENDING_APPROVAL,
        request_reason=payload.reason,
    )
    db.add(booking)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        if "duration" in str(e.orig).lower():
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "DURATION_TOO_LONG", "hint": "Tối đa 8 giờ / lượt."},
            )
        raise
    await audit_log(
        db, actor=user, action="request.create", target_type="booking",
        target_id=booking.id,
        details={"device": device.name, "reason": payload.reason}, request=request,
    )
    await db.commit()
    event_bus.publish_to_roles(
        [UserRole.ADMIN, UserRole.LECTURER], "request.created",
        {"booking_id": str(booking.id), "device_name": device.name,
         "requester": user.full_name},
    )
    return booking


# -------- lecturer/admin: approval queue ------------------------------------

@router.get("/requests/pending", response_model=list[PendingRequestOut])
async def list_pending_requests(
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> list[PendingRequestOut]:
    """Ad-hoc requests awaiting a decision. Lecturers see only their classes'."""
    q = (
        select(Booking, User, Device)
        .join(User, Booking.user_id == User.id)
        .join(Device, Booking.device_id == Device.id)
        .where(Booking.status == BookingStatus.PENDING_APPROVAL)
        .order_by(Booking.created_at)
    )
    if user.role != UserRole.ADMIN:
        q = q.where(Booking.class_id.in_(select(Class.id).where(Class.lecturer_id == user.id)))
    rows = (await db.execute(q)).all()
    return [
        PendingRequestOut(
            booking_id=b.id,
            requester_id=u.id,
            requester_display=u.student_code or u.full_name or u.email,
            device_id=d.id,
            device_name=d.name,
            class_id=b.class_id,
            start_time=b.start_time,
            end_time=b.end_time,
            request_reason=b.request_reason,
            status=b.status.value,
            created_at=b.created_at,
        )
        for b, u, d in rows
    ]


async def _decide_request(
    *,
    booking_id: UUID,
    user: User,
    db: AsyncSession,
    request: Request,
    decision: Literal["approve", "reject"],
    note: str | None,
) -> Booking:
    b = (
        await db.execute(select(Booking).where(Booking.id == booking_id))
    ).scalar_one_or_none()
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "REQUEST_NOT_FOUND"})
    if b.status != BookingStatus.PENDING_APPROVAL:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "ALREADY_DECIDED", "current_status": b.status.value},
        )
    if user.role != UserRole.ADMIN:
        owns = (
            await db.execute(
                select(Class.id).where(
                    Class.id == b.class_id, Class.lecturer_id == user.id
                )
            )
        ).scalar_one_or_none()
        if owns is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail={"code": "NOT_YOUR_CLASS"}
            )
    b.decided_by = user.id
    b.decided_at = _utcnow()
    b.decision_note = note
    if decision == "reject":
        b.status = BookingStatus.REJECTED
    else:
        b.status = BookingStatus.SCHEDULED
        try:
            await db.flush()  # GIST EXCLUDE fires now that status is 'scheduled'
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={"code": "BOOKING_CONFLICT",
                        "hint": "Khung giờ đã có lịch khác — từ chối hoặc đổi giờ."},
            )
    await audit_log(
        db, actor=user, action=f"request.{decision}", target_type="booking",
        target_id=b.id, details={"note": note, "status": b.status.value},
        request=request,
    )
    await db.commit()
    event_bus.publish_to_user(
        b.user_id, "request.decided",
        {"booking_id": str(b.id), "status": b.status.value, "note": note},
    )
    return b


@router.post("/requests/{booking_id}/approve", response_model=BookingOut)
async def approve_request(
    booking_id: UUID,
    payload: RequestDecide,
    request: Request,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> Booking:
    return await _decide_request(
        booking_id=booking_id, user=user, db=db, request=request,
        decision="approve", note=payload.decision_note,
    )


@router.post("/requests/{booking_id}/reject", response_model=BookingOut)
async def reject_request(
    booking_id: UUID,
    payload: RequestDecide,
    request: Request,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> Booking:
    return await _decide_request(
        booking_id=booking_id, user=user, db=db, request=request,
        decision="reject", note=payload.decision_note,
    )
