# 10 — Access Control Logic

Đây là **logic core** quyết định SV có được dùng kit không. Mọi booking action **bắt buộc** đi qua các check này. **Skip = security violation**.

## Nguyên tắc

1. **Default deny** — SV không có quyền dùng bất kỳ kit nào trừ khi có path "yes" rõ ràng.
2. **2 path để có quyền**: qua class assignment hoặc qua special access.
3. **Mọi check phải atomic** — không có race condition.
4. **Audit cho mọi denial** — biết tại sao bị reject.

## Decision tree

```
[SV muốn book device D từ T1 đến T2]
                │
                ▼
   [SV có active enrollment trong class C
    với class_device_assignments(C, D) active không?]
                │
        ┌───────┴──────┐
        │ YES          │ NO
        ▼              ▼
   [Slot T1-T2 có        [SV có active
    nằm trong            special_access(SV, D)
    allowed_time_        không?]
    windows của          │
    assignment đó?]      ├─── YES ──┐
        │                │          │
   ┌────┴────┐           │          ▼
   │ YES     │ NO        │     [Slot T1-T2 có
   ▼         ▼           │      nằm trong
[Quota lớp]  ❌          │      allowed_time_windows?]
   │         OUTSIDE_    │           │
   ▼         TIME        │      ┌────┴────┐
[Quota       _WINDOW     │      │ YES     │ NO
 global SV?]             │      ▼         ▼
   │                     │  [Quota         ❌
   ▼                     │   special?]
[Conflict booking?]      │      │
   │                     │      ▼
   ▼                     │   [Quota global?]
   ✅ ALLOW              │      │
                         │      ▼
                         │   [Conflict?]
                         │      │
                         │      ▼
                         │      ✅ ALLOW
                         │
                         └─── NO ───▶ ❌ ACCESS_DENIED
```

## Function chính

```python
# backend/app/services/access_control.py

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

@dataclass
class AccessDecision:
    allowed: bool
    reason: str  # mã lỗi để frontend i18n
    details: dict  # context để debug + log
    granted_via: str | None = None  # "class" | "special_access"
    class_id: UUID | None = None
    special_access_id: UUID | None = None


async def can_user_book_device(
    db: AsyncSession,
    user_id: UUID,
    device_id: UUID,
    start_time: datetime,
    end_time: datetime,
) -> AccessDecision:
    """
    Kiểm tra SV có quyền book device trong khoảng thời gian không.
    Return AccessDecision với allowed=True hoặc False + reason cụ thể.
    """
    
    # 0. Sanity check
    if end_time <= start_time:
        return AccessDecision(False, "INVALID_TIME_RANGE", {})
    
    if start_time < datetime.utcnow():
        return AccessDecision(False, "PAST_TIME", {})
    
    duration = end_time - start_time
    if duration > timedelta(hours=8):
        return AccessDecision(False, "DURATION_EXCEEDED", 
                             {"max_hours": 8, "requested_hours": duration.total_seconds() / 3600})
    
    # 1. Check device exists + bookable
    device = await get_device(db, device_id)
    if not device:
        return AccessDecision(False, "DEVICE_NOT_FOUND", {})
    if device.status in ("maintenance", "offline"):
        return AccessDecision(False, "DEVICE_NOT_AVAILABLE", {"status": device.status})
    
    # 2. Try CLASS path
    class_path = await _check_via_class(db, user_id, device_id, start_time, end_time)
    if class_path.allowed:
        return class_path
    
    # 3. Try SPECIAL ACCESS path
    special_path = await _check_via_special_access(db, user_id, device_id, start_time, end_time)
    if special_path.allowed:
        return special_path
    
    # 4. Cả 2 đều fail → deny với reason cụ thể nhất
    if class_path.reason == "NO_CLASS_ASSIGNMENT" and special_path.reason == "NO_SPECIAL_ACCESS":
        return AccessDecision(False, "ACCESS_DENIED", 
                             {"hint": "Liên hệ giảng viên để được cấp quyền"})
    # Nếu fail vì lý do khác (vd time window, quota), trả lỗi gần nhất
    return class_path if class_path.reason != "NO_CLASS_ASSIGNMENT" else special_path


async def _check_via_class(
    db: AsyncSession,
    user_id: UUID,
    device_id: UUID,
    start_time: datetime,
    end_time: datetime,
) -> AccessDecision:
    
    # 2a. Find active class assignment cho device này mà user enrolled
    query = """
    SELECT cda.*, c.id as class_id, c.name as class_name
    FROM class_device_assignments cda
    JOIN classes c ON c.id = cda.class_id
    JOIN enrollments e ON e.class_id = c.id
    WHERE e.user_id = :user_id
      AND cda.device_id = :device_id
      AND cda.revoked_at IS NULL
      AND e.is_active = TRUE
      AND :start_time >= cda.valid_from
      AND :end_time <= cda.valid_to
    ORDER BY cda.granted_at DESC
    LIMIT 1
    """
    assignment = await db.fetch_one(query, {
        "user_id": user_id, 
        "device_id": device_id,
        "start_time": start_time,
        "end_time": end_time,
    })
    
    if not assignment:
        return AccessDecision(False, "NO_CLASS_ASSIGNMENT", {})
    
    # 2b. Check time window
    if not _is_within_time_windows(start_time, end_time, assignment.allowed_time_windows):
        return AccessDecision(False, "OUTSIDE_TIME_WINDOW",
                             {"allowed_windows": assignment.allowed_time_windows,
                              "class_name": assignment.class_name})
    
    # 2c. Check quota class
    hours_used_this_week = await _get_class_hours_used_this_week(
        db, user_id, device_id, assignment.class_id
    )
    requested_hours = (end_time - start_time).total_seconds() / 3600
    if hours_used_this_week + requested_hours > assignment.per_student_weekly_hours:
        return AccessDecision(False, "CLASS_QUOTA_EXCEEDED",
                             {"used": hours_used_this_week,
                              "limit": assignment.per_student_weekly_hours,
                              "requested": requested_hours})
    
    # 2d. Check concurrent booking
    concurrent = await _count_concurrent_bookings(db, user_id, device_id, start_time, end_time)
    if concurrent >= assignment.per_student_max_concurrent:
        return AccessDecision(False, "CONCURRENT_LIMIT_EXCEEDED",
                             {"max": assignment.per_student_max_concurrent})
    
    # 2e. Advance booking limit
    days_ahead = (start_time - datetime.utcnow()).days
    if days_ahead > assignment.per_student_max_advance_days:
        return AccessDecision(False, "ADVANCE_LIMIT_EXCEEDED",
                             {"max_days": assignment.per_student_max_advance_days})
    
    # 2f. Check global user quota
    global_check = await _check_global_quota(db, user_id, requested_hours)
    if not global_check.allowed:
        return global_check
    
    # 2g. Check booking conflict trên device
    conflict = await _check_device_conflict(db, device_id, start_time, end_time)
    if conflict:
        return AccessDecision(False, "BOOKING_CONFLICT",
                             {"conflicting_booking_id": conflict.id})
    
    return AccessDecision(
        allowed=True,
        reason="OK",
        details={"weekly_quota_remaining": assignment.per_student_weekly_hours - hours_used_this_week - requested_hours},
        granted_via="class",
        class_id=assignment.class_id,
    )


async def _check_via_special_access(
    db: AsyncSession,
    user_id: UUID,
    device_id: UUID,
    start_time: datetime,
    end_time: datetime,
) -> AccessDecision:
    """Tương tự _check_via_class nhưng query special_access table."""
    
    query = """
    SELECT * FROM special_access
    WHERE user_id = :user_id
      AND device_id = :device_id
      AND revoked_at IS NULL
      AND :start_time >= valid_from
      AND :end_time <= valid_to
    ORDER BY granted_at DESC
    LIMIT 1
    """
    sa = await db.fetch_one(query, {...})
    
    if not sa:
        return AccessDecision(False, "NO_SPECIAL_ACCESS", {})
    
    # Time window
    if sa.allowed_time_windows and not _is_within_time_windows(
        start_time, end_time, sa.allowed_time_windows
    ):
        return AccessDecision(False, "OUTSIDE_TIME_WINDOW",
                             {"allowed_windows": sa.allowed_time_windows})
    
    # Quota special
    if sa.weekly_hours_limit:
        used = await _get_special_hours_used_this_week(db, user_id, device_id, sa.id)
        requested = (end_time - start_time).total_seconds() / 3600
        if used + requested > sa.weekly_hours_limit:
            return AccessDecision(False, "SPECIAL_QUOTA_EXCEEDED",
                                 {"used": used, "limit": sa.weekly_hours_limit})
    
    # Global quota + conflict (như class path)
    # ...
    
    return AccessDecision(
        allowed=True,
        reason="OK",
        details={},
        granted_via="special_access",
        special_access_id=sa.id,
    )
```

## Helper: Time window check

```python
def _is_within_time_windows(
    start: datetime, end: datetime, windows: list[dict]
) -> bool:
    """
    windows = [{"day_of_week": 1, "start": "08:00", "end": "22:00"}, ...]
    day_of_week: 1=Monday, 7=Sunday
    
    Slot phải nằm trong 1 window đơn (không thể span nhiều ngày).
    """
    if not windows:
        return True  # empty = 24/7
    
    if start.date() != end.date():
        return False  # không cho span nhiều ngày
    
    day = start.isoweekday()  # 1-7
    
    for w in windows:
        if w["day_of_week"] != day:
            continue
        win_start = time.fromisoformat(w["start"])
        win_end = time.fromisoformat(w["end"])
        if start.time() >= win_start and end.time() <= win_end:
            return True
    
    return False
```

## Helper: Quota check

```python
async def _get_class_hours_used_this_week(
    db: AsyncSession, user_id: UUID, device_id: UUID, class_id: UUID
) -> float:
    """Tổng số giờ user đã book/dùng trên device này trong class này, tuần hiện tại."""
    query = """
    SELECT COALESCE(SUM(EXTRACT(EPOCH FROM (end_time - start_time)) / 3600.0), 0) as hours
    FROM bookings
    WHERE user_id = :user_id
      AND device_id = :device_id
      AND granted_via = 'class'
      AND class_id = :class_id
      AND status IN ('scheduled', 'active', 'completed')
      AND start_time >= date_trunc('week', NOW() AT TIME ZONE 'Asia/Ho_Chi_Minh')
      AND start_time < date_trunc('week', NOW() AT TIME ZONE 'Asia/Ho_Chi_Minh') + INTERVAL '1 week'
    """
    row = await db.fetch_one(query, {"user_id": user_id, "device_id": device_id, "class_id": class_id})
    return row["hours"]
```

## Helper: Conflict check

```python
async def _check_device_conflict(
    db: AsyncSession, device_id: UUID, start: datetime, end: datetime
) -> Booking | None:
    """Trả booking trùng slot (nếu có). Dùng GIST index của Postgres."""
    query = """
    SELECT * FROM bookings
    WHERE device_id = :device_id
      AND status IN ('scheduled', 'active')
      AND tstzrange(start_time, end_time) && tstzrange(:start, :end)
    LIMIT 1
    """
    return await db.fetch_one(query, {"device_id": device_id, "start": start, "end": end})
```

> **CRITICAL**: Constraint EXCLUDE ở DB là **last line of defense**. Nếu race condition slip qua app check, DB sẽ raise exception. Backend phải catch và return BOOKING_CONFLICT.

## Khi tạo booking — atomic transaction

```python
async def create_booking(db: AsyncSession, user_id: UUID, payload: BookingCreate) -> Booking:
    async with db.begin():
        # 1. Access control check (read-only)
        decision = await can_user_book_device(
            db, user_id, payload.device_id, payload.start_time, payload.end_time
        )
        if not decision.allowed:
            raise HTTPException(403 if decision.reason == "ACCESS_DENIED" else 422,
                               detail={"code": decision.reason, "details": decision.details})
        
        # 2. Insert booking
        booking = Booking(
            user_id=user_id,
            device_id=payload.device_id,
            granted_via=decision.granted_via,
            class_id=decision.class_id,
            special_access_id=decision.special_access_id,
            start_time=payload.start_time,
            end_time=payload.end_time,
            purpose=payload.purpose,
            status="scheduled",
        )
        db.add(booking)
        try:
            await db.flush()
        except IntegrityError as e:
            # GIST EXCLUDE constraint vi phạm
            if "no_overlap" in str(e):
                raise HTTPException(422, detail={"code": "BOOKING_CONFLICT"})
            raise
        
        # 3. Audit
        await audit_log(db, user_id, "booking.create", "booking", booking.id, {
            "device_id": str(payload.device_id),
            "granted_via": decision.granted_via,
            "details": decision.details,
        })
        
        return booking
```

## Khi cancel booking

Đơn giản hơn — chỉ check ownership:

```python
async def cancel_booking(db: AsyncSession, user_id: UUID, booking_id: UUID, role: str):
    booking = await get_booking(db, booking_id)
    if not booking:
        raise HTTPException(404)
    
    # Owner hoặc admin/lecturer mới được cancel
    if booking.user_id != user_id and role not in ("admin", "lecturer", "ta"):
        raise HTTPException(403)
    
    # Lecturer chỉ cancel được booking SV trong lớp mình
    if role == "lecturer" and booking.class_id:
        class_obj = await get_class(db, booking.class_id)
        if class_obj.lecturer_id != user_id:
            raise HTTPException(403)
    
    if booking.status != "scheduled":
        raise HTTPException(422, "Chỉ cancel được booking chưa active")
    
    booking.status = "cancelled"
    booking.cancelled_at = datetime.utcnow()
    booking.cancelled_by = user_id
    await db.commit()
    
    await audit_log(db, user_id, "booking.cancel", "booking", booking.id, {})
```

## Lecturer scope check

Khi lecturer thao tác observe/kick session:

```python
async def lecturer_can_access_session(
    db: AsyncSession, lecturer_id: UUID, session_id: UUID
) -> bool:
    """Lecturer chỉ access được session của SV trong lớp mình dạy."""
    query = """
    SELECT 1 FROM sessions s
    JOIN bookings b ON b.id = s.booking_id
    WHERE s.id = :session_id
      AND b.granted_via = 'class'
      AND EXISTS (
          SELECT 1 FROM classes c
          WHERE c.id = b.class_id
            AND c.lecturer_id = :lecturer_id
      )
    """
    return await db.fetch_one(query, {...}) is not None
```

> Note: nếu booking via special_access do lecturer này cấp, cũng cho phép observe/kick. Chỉnh query union 2 case.

## Test cases bắt buộc

`backend/tests/test_access_control.py`:

```python
# Path 1: SV thuộc class với assignment đầy đủ → allow
async def test_class_path_happy():
    decision = await can_user_book_device(db, sv_id, device_id, t1, t2)
    assert decision.allowed
    assert decision.granted_via == "class"

# Path 2: SV không thuộc class nào → deny
async def test_no_class_no_special():
    decision = await can_user_book_device(db, random_sv_id, device_id, t1, t2)
    assert not decision.allowed
    assert decision.reason == "ACCESS_DENIED"

# Path 3: SV thuộc class nhưng device chưa assign → deny
async def test_class_no_assignment():
    decision = await can_user_book_device(db, sv_id, other_device_id, t1, t2)
    assert not decision.allowed

# Path 4: Slot ngoài khung giờ → deny
async def test_outside_time_window():
    # Class allowed T2-T6 8h-22h, SV book T7 14h
    saturday_2pm = ...
    decision = await can_user_book_device(db, sv_id, device_id, saturday_2pm, saturday_2pm + 1h)
    assert not decision.allowed
    assert decision.reason == "OUTSIDE_TIME_WINDOW"

# Path 5: Quota exceeded → deny
async def test_quota_exceeded():
    # Đã book 4.5h trong tuần, quota 5h, request thêm 1h
    await create_booking(...)  # 4.5h
    decision = await can_user_book_device(db, sv_id, device_id, t1, t1 + 1h)
    assert not decision.allowed
    assert decision.reason == "CLASS_QUOTA_EXCEEDED"

# Path 6: Special access path → allow
async def test_special_access_path():
    # SV không trong class, nhưng có special access
    await grant_special_access(db, sv_id, device_id, ...)
    decision = await can_user_book_device(db, sv_id, device_id, t1, t2)
    assert decision.allowed
    assert decision.granted_via == "special_access"

# Path 7: Special access expired → deny
async def test_special_access_expired():
    # Special access valid_to = past
    await grant_special_access(db, sv_id, device_id, valid_to=yesterday)
    decision = await can_user_book_device(db, sv_id, device_id, t1, t2)
    assert not decision.allowed

# Path 8: Class assignment revoked → deny
async def test_class_assignment_revoked():
    await revoke_class_assignment(db, ...)
    decision = await can_user_book_device(db, sv_id, device_id, t1, t2)
    assert not decision.allowed

# Path 9: Booking conflict (device đã có booking khác) → deny
async def test_booking_conflict():
    await create_booking(db, other_sv, device_id, t1, t2)
    decision = await can_user_book_device(db, sv_id, device_id, t1, t2)
    assert not decision.allowed
    assert decision.reason == "BOOKING_CONFLICT"

# Path 10: Race condition — 2 SV book cùng slot
async def test_race_condition_db_constraint():
    # Cả 2 pass app check, DB constraint giữ
    results = await asyncio.gather(
        create_booking(db, sv1, device, t1, t2),
        create_booking(db, sv2, device, t1, t2),
        return_exceptions=True
    )
    success = [r for r in results if isinstance(r, Booking)]
    assert len(success) == 1
```

**Coverage requirement**: ≥ 90% cho file `access_control.py`.

## Tổng kết: order of checks

Từ rẻ → đắt, fail-fast:

1. Sanity (input validation) — 0 query
2. Device exists + status — 1 query
3. Class assignment exists — 1 query
4. Time window — 0 query (in-memory)
5. Class quota — 1 query (sum)
6. Concurrent limit — 1 query (count)
7. Advance limit — 0 query
8. Global quota — 1 query
9. Device conflict — 1 query
10. (DB-level) GIST EXCLUDE — fallback safety

Tổng: ~5-6 query cho 1 booking attempt. Có thể optimize thành 1 query lớn nếu cần.
