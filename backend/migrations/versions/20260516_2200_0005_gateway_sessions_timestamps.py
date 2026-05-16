"""M5.8 fix: add created_at/updated_at to gateway_sessions.

The SQLAlchemy model GatewaySession inherits TimestampMixin, which expects
created_at + updated_at columns. Migration 0004 missed them, so the verify
query against gateway_sessions raises UndefinedColumnError.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-16 22:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent — 0004 was patched after this migration was authored, so
    # fresh installs land with the columns already present. Old SV14
    # installs still need them added here.
    conn = op.get_bind()
    have_created = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='gateway_sessions' AND column_name='created_at'"
        )
    ).first()
    if not have_created:
        op.add_column(
            "gateway_sessions",
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )
    have_updated = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='gateway_sessions' AND column_name='updated_at'"
        )
    ).first()
    if not have_updated:
        op.add_column(
            "gateway_sessions",
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )


def downgrade() -> None:
    op.drop_column("gateway_sessions", "updated_at")
    op.drop_column("gateway_sessions", "created_at")
