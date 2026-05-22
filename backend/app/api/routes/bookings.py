"""Booking endpoints — race-safe creation with GIST EXCLUDE fallback."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_lecturer
from app.core.config import get_settings
from app.core.db import get_db
from app.models import Booking, BookingGrantedVia, BookingStatus, Device, User
from app.models.quota import UserQuota
from app.schemas import BookingCreate, BookingOut
from app.services.access_control import can_user_book_device

router = APIRouter(prefix="/bookings", tags=["bookings"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _week_bounds(ref: datetime) -> tuple[datetime, datetime]:
    weekday = ref.isoweekday()  # 1=Mon..7=Sun
    start = (ref - timedelta(days=weekday - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return start, start + timedelta(days=7)


@router.get("", response_model=list[BookingOut])
async def list_my_bookings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Booking]:
    result = await db.execute(
        select(Booking).where(Booking.user_id == user.id).order_by(Booking.start_time.desc())
    )
    return list(result.scalars().all())


@router.get("/quota")
async def my_quota(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Per-user weekly quota summary for the dashboard widget. Must come BEFORE /{booking_id}."""
    settings = get_settings()
    now = _utcnow()
    week_start, week_end = _week_bounds(now)

    res = await db.execute(
        select(
            func.coalesce(
                func.sum(func.extract("epoch", Booking.end_time - Booking.start_time)),
                0,
            )
        ).where(
            Booking.user_id == user.id,
            Booking.start_time >= week_start,
            Booking.start_time < week_end,
            Booking.status.in_(
                [BookingStatus.SCHEDULED, BookingStatus.ACTIVE, BookingStatus.COMPLETED]
            ),
        )
    )
    hours_used = float(res.scalar_one() or 0) / 3600.0

    res = await db.execute(
        select(func.count(Booking.id)).where(
            Booking.user_id == user.id,
            Booking.status.in_([BookingStatus.SCHEDULED, BookingStatus.ACTIVE]),
        )
    )
    concurrent = int(res.scalar_one() or 0)

    q = (
        await db.execute(select(UserQuota).where(UserQuota.user_id == user.id))
    ).scalar_one_or_none()
    weekly_limit = q.weekly_hours_limit if q else settings.BOOKING_DEFAULT_QUOTA_HOURS_PER_WEEK
    concurrent_limit = (
        q.max_concurrent_bookings if q else settings.BOOKING_DEFAULT_MAX_CONCURRENT
    )

    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "hours_used": round(hours_used, 2),
        "weekly_hours_limit": weekly_limit,
        "hours_remaining": round(max(0.0, weekly_limit - hours_used), 2),
        "concurrent": concurrent,
        "concurrent_limit": concurrent_limit,
        "max_advance_days": settings.BOOKING_DEFAULT_ADVANCE_DAYS,
        "max_duration_hours": settings.BOOKING_MAX_DURATION_HOURS,
    }


@router.get("/pending")
async def list_pending_bookings(
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Bookings awaiting approval — for lecturer/admin to approve or reject.

    Defined before /{booking_id} so the literal path wins the route match.
    """
    rows = (
        await db.execute(
            select(Booking, User, Device)
            .join(User, User.id == Booking.user_id)
            .join(Device, Device.id == Booking.device_id)
            .where(
                Booking.approved.is_(None),
                Booking.status == BookingStatus.SCHEDULED,
            )
            .order_by(Booking.start_time)
        )
    ).all()
    return [
        {
            "id": str(b.id),
            "student_name": owner.full_name,
            "student_email": owner.email,
            "student_code": owner.student_code,
            "device_name": device.name,
            "start_time": b.start_time.isoformat(),
            "end_time": b.end_time.isoformat(),
            "granted_via": b.granted_via.value,
            "notes": b.notes,
        }
        for b, owner, device in rows
    ]


@router.get("/{booking_id}", response_model=BookingOut)
async def get_booking(
    booking_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Booking:
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    b = result.scalar_one_or_none()
    if b is None or b.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "BOOKING_NOT_FOUND"})
    return b


@router.post("", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
async def create_booking(
    payload: BookingCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Booking:
    decision = await can_user_book_device(
        db,
        user_id=user.id,
        device_id=payload.device_id,
        start_time=payload.start_time,
        end_time=payload.end_time,
    )
    if not decision.allowed:
        http = (
            status.HTTP_403_FORBIDDEN
            if decision.reason == "ACCESS_DENIED"
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(http, detail={"code": decision.reason, "details": decision.details})

    booking = Booking(
        user_id=user.id,
        device_id=payload.device_id,
        granted_via=(
            BookingGrantedVia.CLASS
            if decision.granted_via == "class"
            else BookingGrantedVia.SPECIAL_ACCESS
        ),
        class_id=decision.class_id,
        special_access_id=decision.special_access_id,
        start_time=payload.start_time,
        end_time=payload.end_time,
        status=BookingStatus.SCHEDULED,
        notes=payload.notes,
    )
    db.add(booking)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        msg = str(e.orig).lower()
        if "no_overlap" in msg or "exclude" in msg:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "BOOKING_CONFLICT"},
            )
        raise
    await db.refresh(booking)
    return booking


@router.post("/{booking_id}/cancel", response_model=BookingOut)
async def cancel_booking(
    booking_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Booking:
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    b = result.scalar_one_or_none()
    if b is None or b.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "BOOKING_NOT_FOUND"})
    if b.status not in (BookingStatus.SCHEDULED, BookingStatus.ACTIVE):
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"code": "BOOKING_NOT_CANCELLABLE"}
        )
    b.status = BookingStatus.CANCELLED
    await db.commit()
    await db.refresh(b)
    return b


@router.post("/{booking_id}/approve", response_model=BookingOut)
async def approve_booking(
    booking_id: UUID,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> Booking:
    """Lecturer/admin approves a pending booking so the student can connect."""
    b = (
        await db.execute(select(Booking).where(Booking.id == booking_id))
    ).scalar_one_or_none()
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "BOOKING_NOT_FOUND"})
    if b.approved is True:
        return b
    if b.status != BookingStatus.SCHEDULED:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"code": "BOOKING_NOT_PENDING"}
        )
    b.approved = True
    b.decided_by = user.id
    b.decided_at = _utcnow()
    await db.commit()
    await db.refresh(b)
    return b


@router.post("/{booking_id}/reject", response_model=BookingOut)
async def reject_booking(
    booking_id: UUID,
    note: str | None = None,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> Booking:
    """Lecturer/admin rejects a pending booking — frees the slot."""
    b = (
        await db.execute(select(Booking).where(Booking.id == booking_id))
    ).scalar_one_or_none()
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "BOOKING_NOT_FOUND"})
    if b.status != BookingStatus.SCHEDULED:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"code": "BOOKING_NOT_PENDING"}
        )
    b.approved = False
    b.decided_by = user.id
    b.decided_at = _utcnow()
    b.decision_note = note
    b.status = BookingStatus.CANCELLED
    await db.commit()
    await db.refresh(b)
    return b
