"""Device.reserved + managed_by — ESAS-BCSE-managed, non-self-bookable VPS.

A reserved device is NOT self-bookable (no block calendar, no student
access-request); access is granted ONLY by an admin via SpecialAccess.
`managed_by` is a free-text owner label shown in the UI (e.g. "ESAS-BCSE").

Used for the pve3 cluster (sv31-33): students/lecturers see the card but
cannot book or request — an admin grants access, then the existing
SpecialAccess → gateway flow mints a session-spanning (stable) password.

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-29 13:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013"
down_revision: Union[str, Sequence[str], None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column(
            "reserved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "devices",
        sa.Column("managed_by", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("devices", "managed_by")
    op.drop_column("devices", "reserved")
