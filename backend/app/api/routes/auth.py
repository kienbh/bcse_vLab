"""Local-password authentication routes — replaces the prior OIDC flow.

Pattern:
  - Whitelist seeded ahead of time (see scripts/seed.py).
  - User logs in with email + default password.
  - First login → must_change_password=True → frontend redirects to /change-password.
  - Admin can create more accounts via POST /api/auth/admin/users.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import (
    clear_auth_cookies,
    issue_access_token,
    issue_refresh_token,
    set_auth_cookies,
)
from app.models import User, UserRole
from app.models.quota import UserQuota
from app.schemas.auth import (
    AdminCreateUserRequest,
    AdminResetPasswordRequest,
    ChangePasswordRequest,
    LoginRequest,
)
from app.services import auth as auth_service
from app.services.audit import audit_log

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_dict(u: User) -> dict[str, Any]:
    return {
        "id": str(u.id),
        "email": u.email,
        "full_name": u.full_name,
        "role": u.role.value,
        "student_code": u.student_code,
        "is_active": u.is_active,
        "must_change_password": u.must_change_password,
    }


@router.post("/login")
async def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    user = await auth_service.find_by_email(db, payload.email)
    if user is None or not user.is_active:
        await audit_log(
            db, actor=None, action="auth.login.fail",
            details={"email": payload.email, "reason": "no_user_or_inactive"},
            request=request, success=False,
        )
        await db.commit()
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail={"code": "INVALID_CREDENTIALS"},
        )
    if not auth_service.verify_password(payload.password, user.password_hash):
        await audit_log(
            db, actor=user, action="auth.login.fail",
            details={"email": payload.email, "reason": "wrong_password"},
            request=request, success=False,
        )
        await db.commit()
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail={"code": "INVALID_CREDENTIALS"},
        )

    access = issue_access_token(sub=str(user.id), role=user.role.value)
    refresh = issue_refresh_token(sub=str(user.id))
    set_auth_cookies(response, access=access, refresh=refresh)

    await audit_log(
        db, actor=user, action="auth.login.ok",
        details={"role": user.role.value}, request=request,
    )
    await db.commit()
    return _user_dict(user)


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not auth_service.verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail={"code": "WRONG_CURRENT_PASSWORD"},
        )
    if payload.new_password == payload.current_password:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail={"code": "SAME_AS_OLD"},
        )
    user.password_hash = auth_service.hash_password(payload.new_password)
    user.must_change_password = False
    await audit_log(
        db, actor=user, action="auth.password.change",
        target_type="user", target_id=str(user.id), request=request,
    )
    await db.commit()
    await db.refresh(user)
    return _user_dict(user)


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> dict[str, Any]:
    return _user_dict(user)


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    clear_auth_cookies(response)
    return {"status": "logged_out"}


# -------- dev-mode quick login -----------------------------------------------
# One-click sign-in as a fixed test account per role, for kiểm thử dashboard.
# Entirely gated by settings.DEV_LOGIN_ENABLED — when off the endpoints 404 and
# the only way in is the normal whitelist email+password login.
_DEV_LOGIN_ACCOUNTS = {
    "admin": "admin@vju.ac.vn",
    "lecturer": "hung.le@vju.ac.vn",
    "student": "sv01@st.vju.ac.vn",
}


@router.get("/dev-status")
async def dev_status() -> dict[str, Any]:
    """Whether the dev-mode quick-login buttons should be shown on /login."""
    return {"enabled": get_settings().DEV_LOGIN_ENABLED}


@router.post("/dev-login/{role}")
async def dev_login(
    role: str,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One-click login as the fixed test account for `role` — dev/testing only."""
    if not get_settings().DEV_LOGIN_ENABLED:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"code": "DEV_LOGIN_DISABLED"}
        )
    email = _DEV_LOGIN_ACCOUNTS.get(role)
    if email is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "BAD_ROLE", "allowed": list(_DEV_LOGIN_ACCOUNTS)},
        )
    user = await auth_service.find_by_email(db, email)
    if user is None or not user.is_active:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "DEV_ACCOUNT_MISSING", "email": email},
        )
    # A dev test account should land straight on its dashboard.
    if user.must_change_password:
        user.must_change_password = False

    access = issue_access_token(sub=str(user.id), role=user.role.value)
    refresh = issue_refresh_token(sub=str(user.id))
    set_auth_cookies(response, access=access, refresh=refresh)

    await audit_log(
        db, actor=user, action="auth.dev_login",
        details={"role": user.role.value}, request=request,
    )
    await db.commit()
    return _user_dict(user)


# -------- admin: create / list / reset / role-change users -------------------

@router.post("/admin/users", status_code=status.HTTP_201_CREATED)
async def admin_create_user(
    payload: AdminCreateUserRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    existing = await auth_service.find_by_email(db, payload.email)
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"code": "EMAIL_TAKEN"},
        )
    initial = payload.initial_password or auth_service.DEFAULT_PASSWORD
    u = User(
        email=payload.email.lower().strip(),
        full_name=payload.full_name,
        role=payload.role,
        student_code=payload.student_code,
        password_hash=auth_service.hash_password(initial),
        must_change_password=True,
        is_active=True,
    )
    db.add(u)
    await db.flush()
    db.add(UserQuota(user_id=u.id))
    await audit_log(
        db, actor=admin, action="user.create",
        target_type="user", target_id=str(u.id),
        details={"email": u.email, "role": u.role.value}, request=request,
    )
    await db.commit()
    await db.refresh(u)
    return {
        **_user_dict(u),
        "initial_password": initial,
        "note": "User must change password on first login.",
    }


@router.get("/admin/users")
async def admin_list_users(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    res = await db.execute(select(User).order_by(User.created_at.desc()))
    return [_user_dict(u) for u in res.scalars().all()]


@router.post("/admin/users/{user_id}/reset-password")
async def admin_reset_password(
    user_id: UUID,
    payload: AdminResetPasswordRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    target = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"code": "USER_NOT_FOUND"},
        )
    new_pw = payload.new_password or auth_service.DEFAULT_PASSWORD
    target.password_hash = auth_service.hash_password(new_pw)
    target.must_change_password = True
    await audit_log(
        db, actor=admin, action="user.password.reset",
        target_type="user", target_id=str(target.id),
        details={"email": target.email}, request=request,
    )
    await db.commit()
    return {"status": "reset", "email": target.email, "new_password": new_pw}


@router.patch("/admin/users/{user_id}/role")
async def admin_change_role(
    user_id: UUID,
    role: UserRole,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    target = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"code": "USER_NOT_FOUND"},
        )
    if target.id == admin.id and role != UserRole.ADMIN:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail={"code": "CANNOT_DEMOTE_SELF"},
        )
    old = target.role
    target.role = role
    await audit_log(
        db, actor=admin, action="user.role.change",
        target_type="user", target_id=str(target.id),
        details={"from": old.value, "to": role.value}, request=request,
    )
    await db.commit()
    return _user_dict(target)
