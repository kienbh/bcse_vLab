"""VPS block booking — adds 'auto' grant kind for self-service VPS slots.

The existing booking pipeline already validates ranges + GIST EXCLUDE
no-overlap; the only schema move is letting `granted_via='auto'` exist
with class_id=NULL AND special_access_id=NULL. The fair-share / 4h-block
rules are enforced at the service layer (app.services.vps_block_booking)
because they involve a per-student future-booking count that doesn't
translate cleanly into a CHECK constraint.

Idempotent — uses ALTER TYPE … ADD VALUE IF NOT EXISTS + recreates the
xor constraint via DROP+ADD (PostgreSQL doesn't have ALTER CONSTRAINT).

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-27 12:00:00
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0011"
down_revision: Union[str, Sequence[str], None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE booking_granted_via ADD VALUE IF NOT EXISTS 'auto'")

    op.execute("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS ck_bookings_grant_xor")
    op.execute(
        """
        ALTER TABLE bookings ADD CONSTRAINT ck_bookings_grant_xor CHECK (
            (granted_via = 'class' AND class_id IS NOT NULL AND special_access_id IS NULL)
            OR
            (granted_via = 'special_access' AND special_access_id IS NOT NULL AND class_id IS NULL)
            OR
            (granted_via = 'auto' AND class_id IS NULL AND special_access_id IS NULL)
        )
        """
    )


def downgrade() -> None:
    # 'auto' enum value cannot be removed (PostgreSQL limitation) — left in type.
    # Restore the strict xor that forbids auto.
    op.execute("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS ck_bookings_grant_xor")
    op.execute(
        """
        ALTER TABLE bookings ADD CONSTRAINT ck_bookings_grant_xor CHECK (
            (granted_via = 'class' AND class_id IS NOT NULL AND special_access_id IS NULL)
            OR
            (granted_via = 'special_access' AND special_access_id IS NOT NULL AND class_id IS NULL)
        )
        """
    )
