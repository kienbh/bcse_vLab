"""FastAPI dependencies — current user + role guards."""
from collections.abc import Iterable
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import read_access_cookie, verify_token
from app.models import User, UserRole


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    token = read_access_cookie(request)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "NOT_AUTHENTICATED"})
    try:
        payload = verify_token(token)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "INVALID_TOKEN"})
    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "WRONG_TOKEN_TYPE"})
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "INVALID_TOKEN"})
    try:
        user_id = UUID(sub)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "INVALID_SUBJECT"})

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "USER_INACTIVE"})
    return user


def require_role(*allowed: UserRole):
    """Dependency factory — returns a dependency that allows only the given roles."""
    allowed_set = set(allowed)

    async def dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_set:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail={"code": "FORBIDDEN", "required": [r.value for r in allowed_set]},
            )
        return user

    return dep


require_admin = require_role(UserRole.ADMIN)
require_lecturer = require_role(UserRole.LECTURER, UserRole.ADMIN)
require_staff = require_role(UserRole.LECTURER, UserRole.ADMIN, UserRole.TA)
