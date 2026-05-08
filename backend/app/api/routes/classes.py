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
    SpecialAccessCreate,
    SpecialAccessOut,
)

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

@router.get("/{class_id}/enrollments", response_model=list[EnrollmentOut])
async def list_enrollments(
    class_id: UUID,
    user: User = Depends(require_lecturer),
    db: AsyncSession = Depends(get_db),
) -> list[Enrollment]:
    cls = await _get_class_or_403(class_id, user, db, write=True)
    result = await db.execute(
        select(Enrollment).where(Enrollment.class_id == cls.id, Enrollment.is_active.is_(True))
    )
    return list(result.scalars().all())


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
