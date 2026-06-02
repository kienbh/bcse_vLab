"""VPS block-booking — self-service 4h slots with round-robin queue fairness.

Block model: a day is 6 blocks of 4h each, aligned to UTC midnight:
  block 0 = 00:00-04:00 UTC, block 1 = 04:00-08:00, ..., block 5 = 20:00-24:00.

Rules enforced here (DB layer enforces no-overlap via GIST EXCLUDE):
  1. start_time / end_time must align to 4h boundary (00:00 / 04:00 / ...
     UTC). Front-end picker emits exactly these, but defence-in-depth.
  2. Duration ≤ 24h (= 6 blocks). Anything longer → user must submit a
     proposal via /vps-access (existing SpecialAccess flow).
  3. Per-student per-VPS quota: at most 1 future-or-active booking with
     `granted_via='auto'`. After your block ends you can book again — but
     if any other student has already grabbed the next block in the
     meantime, you're at the back of the queue. That's the round-robin
     guarantee: nobody can hoard a VPS by lining up consecutive blocks.
  4. start_time ≥ now (no time travel).

Long-running access (> 24h, or recurring weekly use) is OUT of scope
here — see [[bcse-vlab-vps-access]] / app.services.vps_access for that.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Booking,
    BookingGrantedVia,
    BookingStatus,
    Device,
    DeviceStatus,
    DeviceType,
    User,
)
from app.services.device_prober import probe_tcp


BLOCK_HOURS = 6
BLOCKS_PER_DAY = 4
# 2026-06-02 (revert to original spec): 6h/block × 4 blocks/day (UTC 00/06/12/18).
# SV picks any free block in present or future, BUT exactly ONE block per booking
# AND only ONE active/future booking row at a time across all VPS. No multi-block
# ranges, no hoarding spots. After their block ends (or they cancel), they can
# book the next one. Longer than 6h continuous → email lecturer for a long grant.
MAX_BLOCKS_AUTO = 1


class BlockBookingError(Exception):
    def __init__(self, code: str, message: str = "", **details):
        super().__init__(message or code)
        self.code = code
        self.details = details


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_block_aligned(dt: datetime) -> bool:
    """True iff `dt` is exactly aligned to a 4h block boundary in UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    if dt.minute != 0 or dt.second != 0 or dt.microsecond != 0:
        return False
    return dt.hour % BLOCK_HOURS == 0


def _validate_window(start: datetime, end: datetime) -> int:
    """Validate alignment + duration. Returns block count."""
    if not _is_block_aligned(start) or not _is_block_aligned(end):
        raise BlockBookingError(
            "NOT_BLOCK_ALIGNED",
            "Thời gian phải trùng đầu block 4h "
            "(00/04/08/12/16/20 giờ UTC)",
        )
    if end <= start:
        raise BlockBookingError("INVALID_TIME_RANGE")
    delta = end - start
    if delta.total_seconds() % (BLOCK_HOURS * 3600) != 0:
        raise BlockBookingError("DURATION_NOT_MULTIPLE_OF_BLOCK")
    blocks = int(delta.total_seconds() // (BLOCK_HOURS * 3600))
    if blocks < 1:
        raise BlockBookingError("ZERO_BLOCKS")
    if blocks > MAX_BLOCKS_AUTO:
        raise BlockBookingError(
            "EXCEEDS_AUTO_LIMIT",
            f"Tối đa {MAX_BLOCKS_AUTO} block liên tiếp "
            f"({MAX_BLOCKS_AUTO * BLOCK_HOURS}h). Cần dài hơn thì gửi proposal.",
            max_blocks=MAX_BLOCKS_AUTO,
            requested_blocks=blocks,
        )
    return blocks


async def _ensure_vps(db: AsyncSession, device_id: UUID) -> Device:
    device = (
        await db.execute(select(Device).where(Device.id == device_id))
    ).scalar_one_or_none()
    if device is None:
        raise BlockBookingError("DEVICE_NOT_FOUND")
    if device.device_type != DeviceType.VPS:
        raise BlockBookingError("NOT_A_VPS", device_type=device.device_type.value)
    if device.reserved:
        # ESAS-BCSE-managed VPS (e.g. pve3 sv31-33) — not self-bookable.
        # Access is granted by an admin via SpecialAccess, not the block queue.
        raise BlockBookingError(
            "RESERVED_DEVICE",
            f"VPS {device.name} do {device.managed_by or 'ESAS-BCSE'} quản lý — "
            "không tự đặt lịch được. Liên hệ admin để được cấp quyền truy cập.",
            managed_by=device.managed_by,
        )
    return device


async def _existing_auto_booking_anywhere(
    db: AsyncSession, *, student_id: UUID
) -> Booking | None:
    """1 SV = 1 booking row max (per thầy's spec 2026-05-27 final). Search
    across ALL VPS for the student's current/future auto booking. Returns
    the offending booking so the UI can quote it back in the error."""
    now = _utcnow()
    row = await db.execute(
        select(Booking)
        .where(
            Booking.user_id == student_id,
            Booking.granted_via == BookingGrantedVia.AUTO,
            Booking.status.in_(
                [BookingStatus.SCHEDULED, BookingStatus.ACTIVE]
            ),
            Booking.end_time > now,
        )
        .order_by(Booking.start_time.asc())
        .limit(1)
    )
    return row.scalar_one_or_none()


def current_block_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    """The 4h block containing `now` (default = utcnow), aligned to
    00/04/08/12/16/20 UTC. Used to enforce "book only the current block"."""
    n = (now or _utcnow()).astimezone(timezone.utc).replace(
        minute=0, second=0, microsecond=0
    )
    start = n.replace(hour=(n.hour // BLOCK_HOURS) * BLOCK_HOURS)
    return start, start + timedelta(hours=BLOCK_HOURS)


async def book_block(
    db: AsyncSession,
    *,
    student: User,
    device_id: UUID,
    start_time: datetime,
    end_time: datetime,
) -> Booking:
    """Book the CURRENT 4h block on `device_id` for `student`.

    Per the 2026-05-27 spec, the only accepted window is the block that's
    currently in progress (no future-block booking, no multi-block ranges).
    The student gets whatever's left of the block; the next block opens for
    a fresh round of FIFO at the next boundary.
    """
    device = await _ensure_vps(db, device_id)
    _validate_window(start_time, end_time)

    # Liveness check — Hoà Lạc loses power often, refuse booking on a dead VPS
    # so a student can't reserve a block they won't be able to SSH into. Reuses
    # the device_prober's TCP-connect probe (3s timeout, no auth).
    if device.status == DeviceStatus.MAINTENANCE:
        raise BlockBookingError(
            "VPS_MAINTENANCE",
            f"VPS {device.name} đang bảo trì, không đặt được",
        )
    is_up = await probe_tcp(str(device.internal_ip), device.ssh_port)
    if not is_up:
        raise BlockBookingError(
            "VPS_OFFLINE",
            f"VPS {device.name} hiện không phản hồi (có thể mất điện / "
            f"đang khởi động lại). Thử lại sau ít phút.",
            device_name=device.name,
        )

    # Reject only true past-block bookings (>5 min in the past). Current block
    # and any future block are fine — flexibility per thầy's 2026-05-27 update.
    if end_time <= _utcnow() - timedelta(minutes=5):
        raise BlockBookingError("PAST_BLOCK", "Block đã kết thúc rồi")

    # Hoarding guard — 1 SV holds at most 1 booking row at a time. After their
    # current one ends they're free to book again.
    existing = await _existing_auto_booking_anywhere(db, student_id=student.id)
    if existing is not None:
        raise BlockBookingError(
            "ALREADY_HOLDING_BLOCK",
            "Bạn đã có 1 lịch đang giữ chỗ. Đợi lịch hiện tại kết thúc "
            "(hoặc huỷ) rồi đặt mới — mỗi SV chỉ giữ 1 chỗ tại 1 lúc.",
            existing_booking_id=str(existing.id),
            existing_device_id=str(existing.device_id),
            existing_start_time=existing.start_time.isoformat(),
            existing_end_time=existing.end_time.isoformat(),
        )

    booking = Booking(
        user_id=student.id,
        device_id=device.id,
        granted_via=BookingGrantedVia.AUTO,
        class_id=None,
        special_access_id=None,
        start_time=start_time,
        end_time=end_time,
        status=BookingStatus.SCHEDULED,
        shared_resource=False,  # auto blocks DO use the GIST no-overlap rule
        notes="VPS block auto-booking",
    )
    db.add(booking)
    try:
        await db.flush()
    except IntegrityError as e:
        # GIST EXCLUDE caught a concurrent insert — turn into a friendly error.
        await db.rollback()
        msg = str(e.orig) if e.orig else str(e)
        if "no_overlap" in msg or "exclude" in msg.lower():
            raise BlockBookingError("BLOCK_TAKEN", "Block này vừa có SV khác book")
        raise
    return booking


async def cancel_block(
    db: AsyncSession, *, student: User, booking_id: UUID
) -> Booking:
    booking = (
        await db.execute(select(Booking).where(Booking.id == booking_id))
    ).scalar_one_or_none()
    if booking is None or booking.user_id != student.id:
        raise BlockBookingError("BOOKING_NOT_FOUND")
    if booking.granted_via != BookingGrantedVia.AUTO:
        raise BlockBookingError("NOT_AN_AUTO_BLOCK")
    if booking.status not in (BookingStatus.SCHEDULED, BookingStatus.ACTIVE):
        raise BlockBookingError(
            "NOT_CANCELLABLE", current_status=booking.status.value
        )
    if booking.end_time <= _utcnow():
        raise BlockBookingError("ALREADY_ENDED")
    booking.status = BookingStatus.CANCELLED
    return booking


async def schedule_for_device(
    db: AsyncSession,
    *,
    device_id: UUID,
    range_from: datetime,
    range_to: datetime,
) -> list[Booking]:
    """All scheduled/active bookings (any granted_via) overlapping the window —
    so the calendar can paint who has what, regardless of how they got it."""
    rows = await db.execute(
        select(Booking)
        .where(
            Booking.device_id == device_id,
            Booking.status.in_(
                [BookingStatus.SCHEDULED, BookingStatus.ACTIVE]
            ),
            Booking.end_time > range_from,
            Booking.start_time < range_to,
        )
        .order_by(Booking.start_time.asc())
    )
    return list(rows.scalars())


async def active_auto_block_for(
    db: AsyncSession, *, student_id: UUID, device_id: UUID
) -> Booking | None:
    """Return the SV's currently-running auto block on this VPS, if any.
    Used by the gateway connect endpoint to mint SSH for a live block."""
    now = _utcnow()
    row = await db.execute(
        select(Booking)
        .where(
            Booking.user_id == student_id,
            Booking.device_id == device_id,
            Booking.granted_via == BookingGrantedVia.AUTO,
            Booking.status.in_(
                [BookingStatus.SCHEDULED, BookingStatus.ACTIVE]
            ),
            Booking.start_time <= now,
            Booking.end_time > now,
        )
        .order_by(Booking.start_time.desc())
        .limit(1)
    )
    return row.scalar_one_or_none()
