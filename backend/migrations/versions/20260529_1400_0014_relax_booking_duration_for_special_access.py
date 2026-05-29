"""Relax bookings 31-day cap for special_access bookings.

Reserved (ESAS-BCSE) devices allow long grants (up to 365 days, migration
0013 + RESERVED_GRANT_MAX_DAYS). The SA->gateway flow auto-creates a Booking
spanning the whole grant window, which hit ck_bookings_max_duration_31d.
Special-access bookings are already bounded by the SpecialAccess window
(grant_vps_access enforces it), so exempt them from the 31-day cap. Class /
auto bookings keep the 31-day backstop.

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-29 14:00:00
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0014"
down_revision: Union[str, Sequence[str], None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS ck_bookings_max_duration_31d")
    op.execute(
        """
        ALTER TABLE bookings ADD CONSTRAINT ck_bookings_max_duration_31d CHECK (
            granted_via = 'special_access'
            OR EXTRACT(EPOCH FROM (end_time - start_time)) <= 31 * 86400
        )
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS ck_bookings_max_duration_31d")
    op.execute(
        """
        ALTER TABLE bookings ADD CONSTRAINT ck_bookings_max_duration_31d
        CHECK (EXTRACT(EPOCH FROM (end_time - start_time)) <= 31 * 86400)
        """
    )
