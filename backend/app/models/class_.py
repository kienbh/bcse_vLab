"""Class + enrollment + class-device assignment tables (the access-control trio)."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.device import Device
    from app.models.user import User
    from app.models.booking import Booking


class Class(Base, TimestampMixin):
    __tablename__ = "classes"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    semester: Mapped[str] = mapped_column(String(32), nullable=False)
    lecturer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)

    enrollments: Mapped[list[Enrollment]] = relationship(back_populates="class_", lazy="raise")
    device_assignments: Mapped[list[ClassDeviceAssignment]] = relationship(
        back_populates="class_", lazy="raise"
    )
    bookings: Mapped[list[Booking]] = relationship(back_populates="class_", lazy="raise")

    __table_args__ = (CheckConstraint("ends_at > starts_at", name="ck_classes_time_order"),)


class Enrollment(Base, TimestampMixin):
    __tablename__ = "enrollments"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    class_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    enrolled_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    class_: Mapped[Class] = relationship(back_populates="enrollments", foreign_keys=[class_id])
    user: Mapped[User] = relationship(back_populates="enrollments", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("class_id", "user_id", name="uq_enrollments_class_user"),
        Index("ix_enrollments_user_active", "user_id", "is_active"),
    )


class ClassDeviceAssignment(Base, TimestampMixin):
    """Lecturer grants a device to a class for a time range, with per-student quotas."""

    __tablename__ = "class_device_assignments"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    class_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False
    )
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    allowed_time_windows: Mapped[list[dict]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment='[{"day_of_week":1..7,"start":"08:00","end":"22:00"}]; empty = 24/7',
    )
    per_student_weekly_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    per_student_max_concurrent: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    per_student_max_advance_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    granted_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    revoke_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    class_: Mapped[Class] = relationship(back_populates="device_assignments", foreign_keys=[class_id])
    device: Mapped[Device] = relationship(back_populates="class_assignments")

    __table_args__ = (
        CheckConstraint("valid_to > valid_from", name="ck_cda_time_order"),
        UniqueConstraint("class_id", "device_id", "valid_from", name="uq_cda_class_device_from"),
        Index(
            "ix_cda_active",
            "class_id",
            "device_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )
