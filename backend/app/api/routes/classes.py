"""Class CRUD + enrollment + device assignment — lecturer-scoped, admin can do all."""
from __future__ import annotations

import csv
import io
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin, require_lecturer
from app.core.db import get_db
from app.models import (
    Class,
    ClassDeviceAssignment,
    Device,
    Enrollment,
    Group,
    PlannedSlot,
    SpecialAccess,
    User,
    UserRole,
)
from app.models.quota import UserQuota
from app.schemas import (
    AssignmentCreate,
    ClassCreate,
    ClassDeviceAssignmentOut,
    ClassOut,
    EnrollmentBulkResult,
    EnrollmentOut,
    EnrollmentRow,
    EnrollStudent,
    GroupCreate,
    GroupMemberAdd,
    GroupMemberRow,
    GroupOut,
    GroupUpdate,
    PlannedSlotCreate,
    PlannedSlotOut,
    SpecialAccessCreate,
    SpecialAccessOut,
)
from app.services.audit import audit_log

router = APIRouter(prefix="/classes", tags=["classes"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])
teacher_router = APIRouter(prefix="/teacher", tags=["teacher"])


def _scope_classes(user: User, query):
    """Lecturers see only their own classes; admin sees all."""
    if user.role == UserRole.ADMIN:
        return query
    return query.where(Class.lecturer_id == user.id)


# -------- classes -------------------------------------------------------------

@router.get("", response_model=list[ClassOut])
async def list_classes(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Class]:
    q = select(Class).order_by(Class.created_at.desc())
    q = _scope_classes(user, q)
    result = await db.execute(q)
    return list(result.scalars().all())


@router.post("", response_model=ClassOut, status_code=status.HTTP_201_CREATED)
async def create_class(
    payload: ClassCreate,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> Class:
    lecturer_id = (
        payload.lecturer_id if (user.role == UserRole.ADMIN and payload.lecturer_id) else user.id
    )
    cls = Class(
        code=payload.code,
        name=payload.name,
        semester=payload.semester,
        lecturer_id=lecturer_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )
    db.add(cls)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"code": "CLASS_CODE_TAKEN", "msg": str(e.orig)}
        )
    await db.refresh(cls)
    return cls


async def _get_class_or_403(
    class_id: UUID, user: User, db: AsyncSession, *, write: bool = False
) -> Class:
    result = await db.execute(select(Class).where(Class.id == class_id))
    cls = result.scalar_one_or_none()
    if cls is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "CLASS_NOT_FOUND"})
    if user.role == UserRole.ADMIN:
        return cls
    if write and cls.lecturer_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": "NOT_YOUR_CLASS"})
    if not write:
        # read also restricted: lecturer (own), or enrolled student
        if cls.lecturer_id != user.id:
            res = await db.execute(
                select(Enrollment).where(
                    Enrollment.class_id == cls.id,
                    Enrollment.user_id == user.id,
                    Enrollment.is_active.is_(True),
                )
            )
            if res.scalar_one_or_none() is None:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": "NOT_ENROLLED"})
    return cls


# -------- enrollment ----------------------------------------------------------

@router.get("/{class_id}/enrollments", response_model=list[EnrollmentRow])
async def list_enrollments(
    class_id: UUID,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> list[EnrollmentRow]:
    """Class roster — each row has the student's identity + their group."""
    cls = await _get_class_or_403(class_id, user, db, write=True)
    result = await db.execute(
        select(Enrollment, User, Group)
        .join(User, Enrollment.user_id == User.id)
        .outerjoin(Group, Enrollment.group_id == Group.id)
        .where(Enrollment.class_id == cls.id, Enrollment.is_active.is_(True))
        .order_by(User.email)
    )
    return [
        EnrollmentRow(
            id=enr.id,
            user_id=u.id,
            email=u.email,
            full_name=u.full_name,
            student_code=u.student_code,
            group_id=enr.group_id,
            group_name=g.name if g is not None else None,
            is_active=enr.is_active,
        )
        for enr, u, g in result.all()
    ]


@router.post(
    "/{class_id}/enroll/csv",
    response_model=EnrollmentBulkResult,
    status_code=status.HTTP_200_OK,
)
async def enroll_csv(
    class_id: UUID,
    file: UploadFile = File(...),
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> EnrollmentBulkResult:
    """CSV format: email,full_name,student_code  (header optional, comma-separated)."""
    cls = await _get_class_or_403(class_id, user, db, write=True)

    if file.size and file.size > 1_000_000:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail={"code": "CSV_TOO_LARGE"})
    raw = (await file.read()).decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(raw))

    enrolled = 0
    created_users = 0
    skipped: list[str] = []
    errors: list[dict] = []

    for line_no, row in enumerate(reader, start=1):
        if not row or all(not c.strip() for c in row):
            continue
        if line_no == 1 and row[0].strip().lower() in {"email", "e-mail"}:
            continue
        if len(row) < 1:
            errors.append({"line": line_no, "msg": "empty row"})
            continue
        email = row[0].strip().lower()
        full_name = (row[1].strip() if len(row) > 1 else email.split("@")[0]) or email
        student_code = row[2].strip() if len(row) > 2 else None

        if not email or "@" not in email:
            errors.append({"line": line_no, "msg": "invalid email"})
            continue
        if not (email.endswith("@st.vju.ac.vn") or email.endswith("@vju.ac.vn")):
            skipped.append(email)
            continue

        # Find or create user
        u = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if u is None:
            u = User(
                email=email,
                full_name=full_name,
                role=UserRole.STUDENT,
                student_code=student_code,
                is_active=True,
            )
            db.add(u)
            await db.flush()
            db.add(UserQuota(user_id=u.id))
            created_users += 1

        # Skip if already enrolled
        existing = (
            await db.execute(
                select(Enrollment).where(
                    Enrollment.class_id == cls.id, Enrollment.user_id == u.id
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(Enrollment(class_id=cls.id, user_id=u.id, enrolled_by=user.id))
            enrolled += 1
        elif not existing.is_active:
            existing.is_active = True
            enrolled += 1

    await db.commit()
    return EnrollmentBulkResult(
        enrolled=enrolled, created_users=created_users, skipped=skipped, errors=errors
    )


# -------- device assignments --------------------------------------------------

@router.get("/{class_id}/devices", response_model=list[ClassDeviceAssignmentOut])
async def list_assignments(
    class_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ClassDeviceAssignment]:
    cls = await _get_class_or_403(class_id, user, db, write=False)
    result = await db.execute(
        select(ClassDeviceAssignment).where(
            ClassDeviceAssignment.class_id == cls.id,
            ClassDeviceAssignment.revoked_at.is_(None),
        )
    )
    return list(result.scalars().all())


@router.post(
    "/{class_id}/devices",
    response_model=ClassDeviceAssignmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def assign_device(
    class_id: UUID,
    payload: AssignmentCreate,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> ClassDeviceAssignment:
    cls = await _get_class_or_403(class_id, user, db, write=True)
    # Verify device exists
    device = (
        await db.execute(select(Device).where(Device.id == payload.device_id))
    ).scalar_one_or_none()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "DEVICE_NOT_FOUND"})

    cda = ClassDeviceAssignment(
        class_id=cls.id,
        device_id=payload.device_id,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        allowed_time_windows=[w.model_dump() for w in payload.allowed_time_windows],
        per_student_weekly_hours=payload.per_student_weekly_hours,
        per_student_max_concurrent=payload.per_student_max_concurrent,
        per_student_max_advance_days=payload.per_student_max_advance_days,
        granted_by=user.id,
    )
    db.add(cda)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "ASSIGNMENT_DUPLICATE_FROM", "msg": str(e.orig)},
        )
    await db.refresh(cda)
    return cda


@router.delete(
    "/{class_id}/devices/{assignment_id}", status_code=status.HTTP_200_OK
)
async def revoke_assignment(
    class_id: UUID,
    assignment_id: UUID,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    cls = await _get_class_or_403(class_id, user, db, write=True)
    result = await db.execute(
        select(ClassDeviceAssignment).where(
            ClassDeviceAssignment.id == assignment_id,
            ClassDeviceAssignment.class_id == cls.id,
        )
    )
    cda = result.scalar_one_or_none()
    if cda is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "ASSIGNMENT_NOT_FOUND"})
    if cda.revoked_at is not None:
        return {"status": "already_revoked"}
    from datetime import datetime, timezone

    cda.revoked_at = datetime.now(timezone.utc)
    cda.revoked_by = user.id
    await db.commit()
    return {"status": "revoked"}


# -------- special access ------------------------------------------------------

@teacher_router.post(
    "/special-access",
    response_model=SpecialAccessOut,
    status_code=status.HTTP_201_CREATED,
)
async def grant_special_access(
    payload: SpecialAccessCreate,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> SpecialAccess:
    target = (
        await db.execute(select(User).where(User.email == payload.user_email.lower()))
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "USER_NOT_FOUND"})
    device = (
        await db.execute(select(Device).where(Device.id == payload.device_id))
    ).scalar_one_or_none()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "DEVICE_NOT_FOUND"})

    sa = SpecialAccess(
        user_id=target.id,
        device_id=device.id,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        allowed_time_windows=[w.model_dump() for w in payload.allowed_time_windows],
        weekly_hours_limit=payload.weekly_hours_limit,
        reason=payload.reason,
        granted_by=user.id,
    )
    db.add(sa)
    await db.commit()
    await db.refresh(sa)
    return sa


# ======================================================================
# M6 — group scheduling: single-student enrollment, groups, weekly plan
# ======================================================================

# -------- enrollment: add / remove a single student (replaces CSV) -----------

@router.post(
    "/{class_id}/enroll", response_model=EnrollmentRow, status_code=status.HTTP_201_CREATED
)
async def enroll_student(
    class_id: UUID,
    payload: EnrollStudent,
    request: Request,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> EnrollmentRow:
    """Add one student to the class — creates the account if the email is new.
    Admin/lecturer build the roster directly in the table; no CSV needed."""
    cls = await _get_class_or_403(class_id, user, db, write=True)
    email = payload.email.lower().strip()
    if not (email.endswith("@st.vju.ac.vn") or email.endswith("@vju.ac.vn")):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "BAD_EMAIL_DOMAIN"}
        )
    u = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if u is None:
        u = User(
            email=email,
            full_name=payload.full_name or email.split("@")[0],
            role=UserRole.STUDENT,
            student_code=payload.student_code,
            is_active=True,
        )
        db.add(u)
        await db.flush()
        db.add(UserQuota(user_id=u.id))
    enr = (
        await db.execute(
            select(Enrollment).where(
                Enrollment.class_id == cls.id, Enrollment.user_id == u.id
            )
        )
    ).scalar_one_or_none()
    if enr is None:
        enr = Enrollment(class_id=cls.id, user_id=u.id, enrolled_by=user.id)
        db.add(enr)
        await db.flush()
    elif not enr.is_active:
        enr.is_active = True
    await audit_log(
        db, actor=user, action="enrollment.add", target_type="enrollment",
        target_id=enr.id, details={"class_id": str(cls.id), "email": email},
        request=request,
    )
    await db.commit()
    return EnrollmentRow(
        id=enr.id, user_id=u.id, email=u.email, full_name=u.full_name,
        student_code=u.student_code, group_id=enr.group_id, group_name=None,
        is_active=enr.is_active,
    )


@router.delete("/{class_id}/enrollments/{enrollment_id}", status_code=status.HTTP_200_OK)
async def remove_enrollment(
    class_id: UUID,
    enrollment_id: UUID,
    request: Request,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Drop a student from the class (deactivate enrollment + clear their group)."""
    cls = await _get_class_or_403(class_id, user, db, write=True)
    enr = (
        await db.execute(
            select(Enrollment).where(
                Enrollment.id == enrollment_id, Enrollment.class_id == cls.id
            )
        )
    ).scalar_one_or_none()
    if enr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "ENROLLMENT_NOT_FOUND"})
    enr.is_active = False
    enr.group_id = None
    await audit_log(
        db, actor=user, action="enrollment.remove", target_type="enrollment",
        target_id=enr.id, details={"class_id": str(cls.id)}, request=request,
    )
    await db.commit()
    return {"status": "removed"}


# -------- groups (nhóm) ------------------------------------------------------

async def _group_out(db: AsyncSession, group: Group) -> GroupOut:
    """Build a GroupOut with its members (active enrolled students in the group)."""
    rows = (
        await db.execute(
            select(User)
            .join(Enrollment, Enrollment.user_id == User.id)
            .where(Enrollment.group_id == group.id, Enrollment.is_active.is_(True))
            .order_by(User.email)
        )
    ).scalars().all()
    members = [
        GroupMemberRow(
            user_id=u.id, email=u.email, full_name=u.full_name,
            is_leader=(u.id == group.leader_id),
        )
        for u in rows
    ]
    return GroupOut(
        id=group.id, class_id=group.class_id, name=group.name,
        leader_id=group.leader_id, members=members,
    )


async def _get_group_or_404(class_id: UUID, group_id: UUID, db: AsyncSession) -> Group:
    group = (
        await db.execute(
            select(Group).where(Group.id == group_id, Group.class_id == class_id)
        )
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "GROUP_NOT_FOUND"})
    return group


@router.get("/{class_id}/groups", response_model=list[GroupOut])
async def list_groups(
    class_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[GroupOut]:
    cls = await _get_class_or_403(class_id, user, db, write=False)
    groups = (
        await db.execute(
            select(Group).where(Group.class_id == cls.id).order_by(Group.name)
        )
    ).scalars().all()
    return [await _group_out(db, g) for g in groups]


@router.post(
    "/{class_id}/groups", response_model=GroupOut, status_code=status.HTTP_201_CREATED
)
async def create_group(
    class_id: UUID,
    payload: GroupCreate,
    request: Request,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> GroupOut:
    cls = await _get_class_or_403(class_id, user, db, write=True)
    group = Group(class_id=cls.id, name=payload.name.strip())
    db.add(group)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"code": "GROUP_NAME_TAKEN"})
    await audit_log(
        db, actor=user, action="group.create", target_type="group",
        target_id=group.id, details={"class_id": str(cls.id), "name": group.name},
        request=request,
    )
    await db.commit()
    return await _group_out(db, group)


@router.patch("/{class_id}/groups/{group_id}", response_model=GroupOut)
async def update_group(
    class_id: UUID,
    group_id: UUID,
    payload: GroupUpdate,
    request: Request,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> GroupOut:
    cls = await _get_class_or_403(class_id, user, db, write=True)
    group = await _get_group_or_404(cls.id, group_id, db)
    if payload.name is not None:
        group.name = payload.name.strip()
    if payload.leader_id is not None:
        member = (
            await db.execute(
                select(Enrollment).where(
                    Enrollment.user_id == payload.leader_id,
                    Enrollment.group_id == group.id,
                    Enrollment.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if member is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "LEADER_NOT_A_MEMBER"},
            )
        group.leader_id = payload.leader_id
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"code": "GROUP_NAME_TAKEN"})
    await audit_log(
        db, actor=user, action="group.update", target_type="group",
        target_id=group.id, request=request,
    )
    await db.commit()
    return await _group_out(db, group)


@router.delete("/{class_id}/groups/{group_id}", status_code=status.HTTP_200_OK)
async def delete_group(
    class_id: UUID,
    group_id: UUID,
    request: Request,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    cls = await _get_class_or_403(class_id, user, db, write=True)
    group = await _get_group_or_404(cls.id, group_id, db)
    # planned_slots cascade-delete; enrollments.group_id is SET NULL.
    await db.delete(group)
    await audit_log(
        db, actor=user, action="group.delete", target_type="group",
        target_id=group_id, request=request,
    )
    await db.commit()
    return {"status": "deleted"}


@router.post("/{class_id}/groups/{group_id}/members", response_model=GroupOut)
async def add_group_member(
    class_id: UUID,
    group_id: UUID,
    payload: GroupMemberAdd,
    request: Request,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> GroupOut:
    """Assign an enrolled student to this group (a student belongs to one group;
    adding moves them here if they were in another)."""
    cls = await _get_class_or_403(class_id, user, db, write=True)
    group = await _get_group_or_404(cls.id, group_id, db)
    enr = (
        await db.execute(
            select(Enrollment).where(
                Enrollment.class_id == cls.id,
                Enrollment.user_id == payload.user_id,
                Enrollment.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if enr is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "STUDENT_NOT_ENROLLED"}
        )
    enr.group_id = group.id
    await audit_log(
        db, actor=user, action="group.member.add", target_type="group",
        target_id=group.id, details={"user_id": str(payload.user_id)}, request=request,
    )
    await db.commit()
    return await _group_out(db, group)


@router.delete("/{class_id}/groups/{group_id}/members/{user_id}", response_model=GroupOut)
async def remove_group_member(
    class_id: UUID,
    group_id: UUID,
    user_id: UUID,
    request: Request,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> GroupOut:
    cls = await _get_class_or_403(class_id, user, db, write=True)
    group = await _get_group_or_404(cls.id, group_id, db)
    enr = (
        await db.execute(
            select(Enrollment).where(
                Enrollment.class_id == cls.id,
                Enrollment.user_id == user_id,
                Enrollment.group_id == group.id,
            )
        )
    ).scalar_one_or_none()
    if enr is not None:
        enr.group_id = None
    if group.leader_id == user_id:
        group.leader_id = None  # a non-member cannot stay leader
    await audit_log(
        db, actor=user, action="group.member.remove", target_type="group",
        target_id=group.id, details={"user_id": str(user_id)}, request=request,
    )
    await db.commit()
    return await _group_out(db, group)


# -------- weekly planned slots ----------------------------------------------

@router.get("/{class_id}/planned-slots", response_model=list[PlannedSlotOut])
async def list_planned_slots(
    class_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PlannedSlotOut]:
    cls = await _get_class_or_403(class_id, user, db, write=False)
    rows = (
        await db.execute(
            select(PlannedSlot, Device, Group)
            .join(Device, PlannedSlot.device_id == Device.id)
            .join(Group, PlannedSlot.group_id == Group.id)
            .where(PlannedSlot.class_id == cls.id)
            .order_by(PlannedSlot.day_of_week, PlannedSlot.time_slot)
        )
    ).all()
    return [
        PlannedSlotOut(
            id=ps.id, class_id=ps.class_id, device_id=ps.device_id,
            device_name=d.name, group_id=ps.group_id, group_name=g.name,
            day_of_week=ps.day_of_week, time_slot=ps.time_slot,
        )
        for ps, d, g in rows
    ]


@router.post(
    "/{class_id}/planned-slots",
    response_model=PlannedSlotOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_planned_slot(
    class_id: UUID,
    payload: PlannedSlotCreate,
    request: Request,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> PlannedSlotOut:
    """Assign a group to a kit for a recurring weekday + time slot."""
    cls = await _get_class_or_403(class_id, user, db, write=True)
    device = (
        await db.execute(select(Device).where(Device.id == payload.device_id))
    ).scalar_one_or_none()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "DEVICE_NOT_FOUND"})
    group = await _get_group_or_404(cls.id, payload.group_id, db)
    slot = PlannedSlot(
        class_id=cls.id,
        device_id=device.id,
        group_id=group.id,
        day_of_week=payload.day_of_week,
        time_slot=payload.time_slot,
        created_by=user.id,
    )
    db.add(slot)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "SLOT_TAKEN", "msg": "kit already assigned for that day + slot"},
        )
    await audit_log(
        db, actor=user, action="planned_slot.create", target_type="planned_slot",
        target_id=slot.id,
        details={
            "device": device.name, "group": group.name,
            "day": payload.day_of_week, "slot": payload.time_slot.value,
        },
        request=request,
    )
    await db.commit()
    return PlannedSlotOut(
        id=slot.id, class_id=cls.id, device_id=device.id, device_name=device.name,
        group_id=group.id, group_name=group.name, day_of_week=slot.day_of_week,
        time_slot=slot.time_slot,
    )


@router.delete("/{class_id}/planned-slots/{slot_id}", status_code=status.HTTP_200_OK)
async def delete_planned_slot(
    class_id: UUID,
    slot_id: UUID,
    request: Request,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    cls = await _get_class_or_403(class_id, user, db, write=True)
    slot = (
        await db.execute(
            select(PlannedSlot).where(
                PlannedSlot.id == slot_id, PlannedSlot.class_id == cls.id
            )
        )
    ).scalar_one_or_none()
    if slot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "SLOT_NOT_FOUND"})
    await db.delete(slot)
    await audit_log(
        db, actor=user, action="planned_slot.delete", target_type="planned_slot",
        target_id=slot_id, request=request,
    )
    await db.commit()
    return {"status": "deleted"}
