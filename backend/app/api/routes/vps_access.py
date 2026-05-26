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
    Device,
    DeviceType,
    SpecialAccess,
    User,
    UserRole,
)
from app.schemas import (
    AccessRequestCreate,
    AccessRequestDecide,
    AccessRequestOut,
    VpsGrantCreate,
    VpsGrantOut,
)
from app.services import vps_access as svc
from app.services.audit import audit_log

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
    """Mint (or return) a gateway session for the student's active VPS grant.

    Reuses the M5.8 gateway pipeline: we auto-create a Booking spanning the
    SA window, then call the existing `_issue_or_rotate` which mints the
    bcrypt-hashed password and ties it to the booking.
    """
    sa = await svc.active_grant_for(db, student_id=user.id, device_id=device_id)
    if sa is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "NO_ACTIVE_GRANT",
                "hint": "Bạn chưa được cấp quyền truy cập VPS này, hãy gửi yêu cầu hoặc liên hệ giảng viên.",
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
    if sa.revoked_at is not None:
        return {"status": "already_revoked"}
    sa.revoked_at = datetime.now(timezone.utc)
    sa.revoked_by = user.id
    await audit_log(
        db,
        actor=user,
        action="vps_access.grant.revoke",
        target_type="special_access",
        target_id=str(sa.id),
        request=request,
    )
    await db.commit()
    return {"status": "revoked", "grant_id": str(sa.id)}
