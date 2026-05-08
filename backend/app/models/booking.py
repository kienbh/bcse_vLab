"""Booking + Session tables. The booking GIST EXCLUDE constraint is the last-line race-condition guard."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, pg_enum
from app.models.enums import BookingGrantedVia, BookingStatus, SessionStatus

if TYPE_CHECKING:
    from app.models.device import Device
    from app.models.user import User
    from app.models.class_ import Class
    from app.models.access import SpecialAccess


class Booking(Base, TimestampMixin):
    __tablename__ = "bookings"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    device_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    granted_via: Mapped[BookingGrantedVia] = mapped_column(
        pg_enum(BookingGrantedVia, name="booking_granted_via"), nullable=False
    )
    class_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("classes.id", ondelete="RESTRICT"), nullable=True
    )
    special_access_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("special_access.id", ondelete="RESTRICT"), nullable=True
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[BookingStatus] = mapped_column(
        pg_enum(BookingStatus, name="booking_status"),
        nullable=False,
        default=BookingStatus.SCHEDULED,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    user: Mapped[User] = relationship(back_populates="bookings")
    device: Mapped[Device] = relationship(back_populates="bookings")
    class_: Mapped[Class | None] = relationship(back_populates="bookings", foreign_keys=[class_id])
    special_access: Mapped[SpecialAccess | None] = relationship(
        back_populates="bookings", foreign_keys=[special_access_id]
    )
    session: Mapped[Session | None] = relationship(
        back_populates="booking", lazy="raise", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("end_time > start_time", name="ck_bookings_time_order"),
        CheckConstraint(
            "EXTRACT(EPOCH FROM (end_time - start_time)) <= 8 * 3600",
            name="ck_bookings_max_duration_8h",
        ),
        CheckConstraint(
            """
            (granted_via = 'class' AND class_id IS NOT NULL AND special_access_id IS NULL)
            OR
            (granted_via = 'special_access' AND special_access_id IS NOT NULL AND class_id IS NULL)
            """,
            name="ck_bookings_grant_xor",
        ),
        # The GIST EXCLUDE — see migration 0001 for the actual table-level
        # constraint with `tstzrange(start_time, end_time, '[)')`.
        Index("ix_bookings_user_status", "user_id", "status"),
        Index("ix_bookings_device_active", "device_id", postgresql_where=text("status IN ('scheduled','active')")),
    )


class Session(Base, TimestampMixin):
    """Active SSH session bound to a booking. Created on session start, finalized on end."""

    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    booking_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("bookings.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    ssh_pubkey: Mapped[str] = mapped_column(String(1024), nullable=False)
    ssh_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[SessionStatus] = mapped_column(
        pg_enum(SessionStatus, name="session_status"),
        nullable=False,
        default=SessionStatus.ACTIVE,
        index=True,
    )
    observed_by_lecturer_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    kicked_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    kick_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    booking: Mapped[Booking] = relationship(back_populates="session")
