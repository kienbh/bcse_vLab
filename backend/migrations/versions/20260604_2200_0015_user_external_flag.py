"""User.external — flag for non-VJU accounts (e.g. ESAS-BCSE).

An external user is scoped to whatever's been explicitly granted via
SpecialAccess: list_devices filters to only granted devices, the VPS
block self-booking flow refuses them entirely, and the schedule-view
helper skips its role-based bypass. This keeps the existing student
pool (free-for-all on sv21-30 / ai01-03) untouched, while letting an
admin park an external team account that can only see + use the
reserved devices it has SA for.

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-04 22:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015"
down_revision: Union[str, Sequence[str], None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "external",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "external")
