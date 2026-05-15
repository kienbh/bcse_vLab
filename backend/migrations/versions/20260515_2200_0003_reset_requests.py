"""M5.6: reset request queue — user asks for FPGA power-cycle, admin/lecturer approves.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-15 22:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE reset_request_status AS ENUM "
        "('pending','approved','rejected','completed','failed')"
    )
    reset_status = postgresql.ENUM(name="reset_request_status", create_type=False)

    op.create_table(
        "reset_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "requester_id",
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
        sa.Column(
            "booking_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bookings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("status", reset_status, nullable=False, server_default="pending"),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "decided_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.String(500), nullable=True),
        sa.Column("plug_result", postgresql.JSONB, nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_reset_requests_requester_id", "reset_requests", ["requester_id"])
    op.create_index("ix_reset_requests_device_id", "reset_requests", ["device_id"])
    op.create_index("ix_reset_requests_status", "reset_requests", ["status"])
    op.create_index(
        "ix_reset_requests_pending", "reset_requests", ["status", "requested_at"]
    )
    op.create_index(
        "ix_reset_requests_device_pending", "reset_requests", ["device_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_reset_requests_device_pending", table_name="reset_requests")
    op.drop_index("ix_reset_requests_pending", table_name="reset_requests")
    op.drop_index("ix_reset_requests_status", table_name="reset_requests")
    op.drop_index("ix_reset_requests_device_id", table_name="reset_requests")
    op.drop_index("ix_reset_requests_requester_id", table_name="reset_requests")
    op.drop_table("reset_requests")
    op.execute("DROP TYPE reset_request_status")
