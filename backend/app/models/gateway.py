"""Gateway session + auth log — ADR-0013 (M5.8).

A `GatewaySession` represents one issued SSH password for one booking.
PAM on the jump host (PVE) POSTs to `/api/gateway/auth` which scans the
unrevoked, unexpired rows and bcrypt-verifies. `GatewayAuthLog` records
every attempt for audit + rate-limiting visibility.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, LargeBinary, String, text
from sqlalchemy.dialects.postgresql import INET, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.device import Device
    from app.models.user import User


class GatewaySession(Base, TimestampMixin):
    """One issued SSH password binding a booking to a kit, hashed with bcrypt."""

    __tablename__ = "gateway_sessions"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    booking_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    device_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    ssh_username: Mapped[str] = mapped_column(String(32), nullable=False, default="vlab")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # AES-256-GCM ciphertext of the plaintext password (`nonce || ct || tag`).
    # NULL = legacy row from before the persist-per-slot feature; the API
    # treats it as "rotate on next read" so users aren't locked out.
    password_ciphertext: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )

    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_auth_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    warning_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    target_host: Mapped[str] = mapped_column(INET, nullable=False)
    target_port: Mapped[int] = mapped_column(Integer, nullable=False, default=22)
    target_user: Mapped[str] = mapped_column(String(32), nullable=False)
    client_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    active_pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pty_path: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bytes_in: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    bytes_out: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    regenerate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    booking: Mapped[Booking] = relationship(foreign_keys=[booking_id])
    user: Mapped[User] = relationship(foreign_keys=[user_id])
    device: Mapped[Device] = relationship(foreign_keys=[device_id])

    __table_args__ = (
        Index(
            "ix_gateway_sessions_active",
            "expires_at",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index("ix_gateway_sessions_booking", "booking_id"),
        Index("ix_gateway_sessions_user", "user_id"),
    )


class GatewayAuthLog(Base):
    """Audit row per PAM verify attempt — append-only, no updated_at."""

    __tablename__ = "gateway_auth_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    session_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("gateway_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    booking_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    client_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    ssh_username: Mapped[str | None] = mapped_column(String(32), nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_gateway_auth_log_ts", "ts"),
        Index("ix_gateway_auth_log_session", "session_id"),
    )
