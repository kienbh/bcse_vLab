"""M-approval: per-booking approval gate.

Adds a nullable `approved` flag to bookings (NULL = pending / chờ duyệt,
true = approved, false = rejected) plus who/when/why decided. No enum change —
the booking_status lifecycle stays as-is; `approved` is a separate gate.

Existing bookings are grandfathered to approved=true so they keep working.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-22 06:00:00
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
    op.add_column("bookings", sa.Column("approved", sa.Boolean(), nullable=True))
    op.add_column(
        "bookings",
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "bookings", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("bookings", sa.Column("decision_note", sa.String(500), nullable=True))
    op.create_foreign_key(
        "fk_bookings_decided_by",
        "bookings",
        "users",
        ["decided_by"],
        ["id"],
        ondelete="SET NULL",
    )
    # Grandfather existing bookings — they predate the approval gate.
    op.execute(
        "UPDATE bookings SET approved = true "
        "WHERE status IN ('scheduled', 'active', 'completed')"
    )


def downgrade() -> None:
    op.drop_constraint("fk_bookings_decided_by", "bookings", type_="foreignkey")
    op.drop_column("bookings", "decision_note")
    op.drop_column("bookings", "decided_at")
    op.drop_column("bookings", "decided_by")
    op.drop_column("bookings", "approved")
