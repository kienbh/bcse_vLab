"""Local password auth — bcrypt hashing + helpers.

OIDC was tried in earlier sprints but dropped per thầy's request — too much friction
for a small VJU pilot. Approach now:
  - Pre-seed whitelist with @vju.ac.vn / @st.vju.ac.vn accounts + default password.
  - First login forces change. Admin can create more.
"""
from __future__ import annotations

import secrets

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserRole

# DEFAULT_PASSWORD is the password seeded users start with. They MUST change it on first login.
DEFAULT_PASSWORD = "VJU@2026"


def hash_password(plain: str) -> str:
    """Hash plaintext password with bcrypt. Direct lib use avoids passlib/bcrypt version skew."""
    # bcrypt has a 72-byte hard limit on plain length; truncate defensively.
    plain_bytes = plain.encode("utf-8")[:72]
    return bcrypt.hashpw(plain_bytes, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        plain_bytes = plain.encode("utf-8")[:72]
        return bcrypt.checkpw(plain_bytes, hashed.encode("utf-8"))
    except Exception:
        return False


def role_from_email(email: str) -> UserRole:
    e = email.lower().strip()
    if e.endswith("@vju.ac.vn"):
        return UserRole.LECTURER
    if e.endswith("@st.vju.ac.vn"):
        return UserRole.STUDENT
    return UserRole.STUDENT


async def find_by_email(db: AsyncSession, email: str) -> User | None:
    res = await db.execute(select(User).where(User.email == email.lower().strip()))
    return res.scalar_one_or_none()


def gen_state() -> str:
    return secrets.token_urlsafe(32)
