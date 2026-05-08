"""Special access (per-user, per-device override) — for thesis / research work."""
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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.device import Device
    from app.models.user import User
    from app.models.booking import Booking


class SpecialAccess(Base, TimestampMixin):
    __tablename__ = "special_access"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False
    )
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    allowed_time_windows: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    weekly_hours_limit: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="overrides global quota; null = use global"
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
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

    user: Mapped[User] = relationship(
        foreign_keys=[user_id], back_populates="special_accesses"
    )
    device: Mapped[Device] = relationship(back_populates="special_accesses")
    bookings: Mapped[list[Booking]] = relationship(back_populates="special_access", lazy="raise")

    __table_args__ = (
        CheckConstraint("valid_to > valid_from", name="ck_sa_time_order"),
        Index(
            "ix_sa_active",
            "user_id",
            "device_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )
