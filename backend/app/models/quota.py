"""Per-user quota override (defaults from .env)."""
from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class UserQuota(Base, TimestampMixin):
    __tablename__ = "user_quotas"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    weekly_hours_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    max_concurrent_bookings: Mapped[int] = mapped_column(Integer, nullable=False, default=2)

    user: Mapped[User] = relationship(back_populates="quota")
