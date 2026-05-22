"""M6: weekly group-scheduling — the lecturer's recurring plan of which group
uses which kit on which weekday + time slot."""
from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, pg_enum
from app.models.enums import TimeSlot

if TYPE_CHECKING:
    from app.models.class_ import Class, Group
    from app.models.device import Device


class PlannedSlot(Base, TimestampMixin):
    """One recurring weekly slot: group <group_id> uses device <device_id>
    every <day_of_week> during <time_slot>. Pre-approved by the lecturer —
    the group leader just connects when the slot is live."""

    __tablename__ = "planned_slots"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    class_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("classes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    group_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 1=Mon .. 7=Sun
    time_slot: Mapped[TimeSlot] = mapped_column(
        pg_enum(TimeSlot, name="time_slot"), nullable=False
    )
    created_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    class_: Mapped[Class] = relationship(foreign_keys=[class_id])
    device: Mapped[Device] = relationship(foreign_keys=[device_id])
    group: Mapped[Group] = relationship(foreign_keys=[group_id])

    __table_args__ = (
        CheckConstraint("day_of_week BETWEEN 1 AND 7", name="ck_planned_slots_dow"),
        # one kit + one weekday + one slot → exactly one group
        UniqueConstraint(
            "device_id",
            "day_of_week",
            "time_slot",
            name="uq_planned_slots_device_day_slot",
        ),
    )
