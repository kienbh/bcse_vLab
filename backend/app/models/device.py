"""Device + plug + admin-credential tables."""
from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, LargeBinary, text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, pg_enum
from app.models.enums import DevicePowerState, DeviceStatus, DeviceType, PlugType

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.class_ import ClassDeviceAssignment
    from app.models.access import SpecialAccess


class Device(Base, TimestampMixin):
    __tablename__ = "devices"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    device_type: Mapped[DeviceType] = mapped_column(
        pg_enum(DeviceType, name="device_type"), nullable=False, index=True
    )
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    internal_ip: Mapped[str] = mapped_column(INET, nullable=False)
    ssh_port: Mapped[int] = mapped_column(Integer, nullable=False, default=22)
    ssh_user: Mapped[str] = mapped_column(String(32), nullable=False, default="student")
    status: Mapped[DeviceStatus] = mapped_column(
        pg_enum(DeviceStatus, name="device_status"),
        nullable=False,
        default=DeviceStatus.AVAILABLE,
        index=True,
    )
    # M5.9 — admin-toggled power state. Orthogonal to `status` (which is the
    # operational state for booking eligibility). See migration 0007.
    power_state: Mapped[DevicePowerState] = mapped_column(
        pg_enum(DevicePowerState, name="device_power_state"),
        nullable=False,
        default=DevicePowerState.ON,
    )
    power_state_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    power_state_changed_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    capabilities: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Reserved (ESAS-BCSE-managed) devices are NOT self-bookable: no block
    # calendar, no student access-request. Access is granted ONLY by an admin
    # via SpecialAccess. See migration 0013. `managed_by` is a UI owner label.
    reserved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    managed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    plug: Mapped[PlugMapping | None] = relationship(
        back_populates="device", lazy="raise", uselist=False, cascade="all, delete-orphan"
    )
    credential: Mapped[DeviceCredential | None] = relationship(
        back_populates="device", lazy="raise", uselist=False, cascade="all, delete-orphan"
    )
    bookings: Mapped[list[Booking]] = relationship(back_populates="device", lazy="raise")
    class_assignments: Mapped[list[ClassDeviceAssignment]] = relationship(
        back_populates="device", lazy="raise"
    )
    special_accesses: Mapped[list[SpecialAccess]] = relationship(
        back_populates="device", lazy="raise"
    )


class PlugMapping(Base, TimestampMixin):
    __tablename__ = "plug_mappings"

    device_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True
    )
    plug_ip: Mapped[str] = mapped_column(INET, nullable=False)
    plug_type: Mapped[PlugType] = mapped_column(
        pg_enum(PlugType, name="plug_type"), nullable=False, default=PlugType.TASMOTA
    )
    plug_relay_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    api_token: Mapped[str | None] = mapped_column(String(255), nullable=True)

    device: Mapped[Device] = relationship(back_populates="plug")

    __table_args__ = (Index("ix_plug_mappings_plug_ip", "plug_ip"),)


class DeviceCredential(Base, TimestampMixin):
    """Per-device admin SSH key, encrypted at rest with AES-256-GCM."""

    __tablename__ = "device_credentials"

    device_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True
    )
    encrypted_admin_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_algorithm: Mapped[str] = mapped_column(String(32), nullable=False, default="ed25519")
    rotated_at: Mapped[str | None] = mapped_column(String(32), nullable=True)

    device: Mapped[Device] = relationship(back_populates="credential")
