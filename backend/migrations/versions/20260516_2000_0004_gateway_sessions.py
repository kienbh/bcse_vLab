"""M5.8 / ADR-0013: gateway sessions — password-auth ProxyJump, replaces ephemeral keypair flow.

Adds `gateway_sessions` (per-booking password+target) and `gateway_auth_log`
(audit row per PAM verify attempt). The legacy `sessions` table stays so M5.6
audit history survives, but the access flow no longer inserts into it.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-16 20:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gateway_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "booking_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bookings.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("ssh_username", sa.String(32), nullable=False, server_default="vlab"),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(64), nullable=True),
        sa.Column("last_auth_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("warning_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("target_host", postgresql.INET, nullable=False),
        sa.Column("target_port", sa.Integer, nullable=False, server_default="22"),
        sa.Column("target_user", sa.String(32), nullable=False),
        sa.Column("client_ip", postgresql.INET, nullable=True),
        sa.Column("active_pid", sa.Integer, nullable=True),
        sa.Column("pty_path", sa.String(64), nullable=True),
        sa.Column("bytes_in", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("bytes_out", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column(
            "regenerate_count", sa.Integer, nullable=False, server_default="0"
        ),
    )

    # Active-session lookup: PAM auth fetches all unrevoked + unexpired rows
    # → keep this index tight so bcrypt-verify scan is cheap.
    op.create_index(
        "ix_gateway_sessions_active",
        "gateway_sessions",
        ["expires_at"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index("ix_gateway_sessions_booking", "gateway_sessions", ["booking_id"])
    op.create_index("ix_gateway_sessions_user", "gateway_sessions", ["user_id"])

    op.create_table(
        "gateway_auth_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gateway_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "booking_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bookings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("client_ip", postgresql.INET, nullable=True),
        sa.Column("ssh_username", sa.String(32), nullable=True),
        # ok | wrong_password | expired | revoked | no_active_session | bad_secret
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
    )
    op.create_index("ix_gateway_auth_log_ts", "gateway_auth_log", ["ts"])
    op.create_index(
        "ix_gateway_auth_log_session", "gateway_auth_log", ["session_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_gateway_auth_log_session", table_name="gateway_auth_log")
    op.drop_index("ix_gateway_auth_log_ts", table_name="gateway_auth_log")
    op.drop_table("gateway_auth_log")
    op.drop_index("ix_gateway_sessions_user", table_name="gateway_sessions")
    op.drop_index("ix_gateway_sessions_booking", table_name="gateway_sessions")
    op.drop_index("ix_gateway_sessions_active", table_name="gateway_sessions")
    op.drop_table("gateway_sessions")
