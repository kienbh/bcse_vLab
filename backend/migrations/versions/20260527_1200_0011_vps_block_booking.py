"""VPS block booking PART 1 — add 'auto' enum value.

PostgreSQL gotcha: `ALTER TYPE … ADD VALUE` cannot be followed by any
query that uses the new value WITHIN THE SAME TRANSACTION. Alembic wraps
each migration in a transaction, so we split:
  0011: just ALTER TYPE ADD VALUE  ← commits cleanly on its own
  0012: rewrite the xor CHECK using the now-committed 'auto' value

See [[bcse-vlab-portal]] / migration 0009 — same idempotency pattern
(`ADD VALUE IF NOT EXISTS`) so a partial re-run is safe.

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


def downgrade() -> None:
    # PostgreSQL enum values are immortal — left in the type, no-op downgrade.
    pass
