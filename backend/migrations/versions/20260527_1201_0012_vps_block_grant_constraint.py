"""VPS block booking PART 2 — relax ck_bookings_grant_xor to allow 'auto'.

Split from 0011 because PostgreSQL forbids using a freshly-ADD'd enum
value in the same transaction it was added. By the time this migration
runs the enum value is already committed.

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-27 12:01:00
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0012"
down_revision: Union[str, Sequence[str], None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
