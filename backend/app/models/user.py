"""User + role tables."""
from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, pg_enum
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.class_ import Enrollment
    from app.models.access import SpecialAccess
    from app.models.quota import UserQuota


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        pg_enum(UserRole, name="user_role"), nullable=False, default=UserRole.STUDENT, index=True
    )
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    must_change_password: Mapped[bool] = mapped_column(default=True, nullable=False)
    oidc_subject: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    student_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    bookings: Mapped[list[Booking]] = relationship(
        back_populates="user", foreign_keys="Booking.user_id", lazy="raise"
    )
    enrollments: Mapped[list[Enrollment]] = relationship(
        back_populates="user", foreign_keys="Enrollment.user_id", lazy="raise"
    )
    special_accesses: Mapped[list[SpecialAccess]] = relationship(
        foreign_keys="SpecialAccess.user_id", back_populates="user", lazy="raise"
    )
    quota: Mapped[UserQuota | None] = relationship(back_populates="user", lazy="raise", uselist=False)

    __table_args__ = (
        Index("ix_users_role_active", "role", "is_active"),
    )
