"""Student-initiated VPS access request — lecturer approves → SpecialAccess.

Distinct from `ResetRequest` (device reset queue) and the M6 ad-hoc booking
request (`Booking.status=pending_approval`). VPS is a long-lived resource and
the grant model is per-student, not per-group/slot — hence its own table.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, pg_enum
from app.models.enums import AccessRequestStatus

if TYPE_CHECKING:
    from app.models.access import SpecialAccess
    from app.models.device import Device
    from app.models.user import User


class AccessRequest(Base, TimestampMixin):
    __tablename__ = "access_requests"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False
    )
    requested_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    requested_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[AccessRequestStatus] = mapped_column(
        pg_enum(AccessRequestStatus, name="access_request_status"),
        nullable=False,
        default=AccessRequestStatus.PENDING,
        index=True,
    )
    decided_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    granted_access_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("special_access.id", ondelete="SET NULL"),
        nullable=True,
    )

    student: Mapped[User] = relationship(foreign_keys=[student_id])
    device: Mapped[Device] = relationship()
    granted_access: Mapped[SpecialAccess | None] = relationship(foreign_keys=[granted_access_id])

    __table_args__ = (
        CheckConstraint("requested_to > requested_from", name="ck_ar_time_order"),
        CheckConstraint(
            "EXTRACT(EPOCH FROM (requested_to - requested_from)) <= 30 * 86400",
            name="ck_ar_max_30_days",
        ),
        Index("ix_ar_pending", "device_id", postgresql_where=text("status = 'pending'")),
        Index("ix_ar_student", "student_id"),
    )
