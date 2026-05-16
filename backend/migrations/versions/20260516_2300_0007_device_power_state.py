"""M5.9: devices.power_state — manual on/off/resetting toggle.

Smart plug API in Hoà Lạc still doesn't expose a programmable interface,
so admins flip kits by hand and need somewhere to record "yes that one
is actually on". Orthogonal to devices.status (which gates whether the
kit is bookable).

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-16 23:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE device_power_state AS ENUM ('on','off','resetting')")
    power_enum = postgresql.ENUM(name="device_power_state", create_type=False)
    op.add_column(
        "devices",
        sa.Column(
            "power_state",
            power_enum,
            nullable=False,
            server_default="on",
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "power_state_changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "power_state_changed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("devices", "power_state_changed_by")
    op.drop_column("devices", "power_state_changed_at")
    op.drop_column("devices", "power_state")
    op.execute("DROP TYPE device_power_state")
