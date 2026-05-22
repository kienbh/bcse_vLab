"""M6: group scheduling — groups, planned_slots, booking approval lifecycle.

Adds the weekly group-scheduling model:
  - groups            : student groups (nhóm) within a class, each with a leader
  - enrollments.group_id : which group a student belongs to
  - planned_slots     : lecturer's recurring weekly plan (group x kit x day x slot)
  - bookings          : + pending_approval / rejected statuses
                        + decided_by / decided_at / decision_note
                        + planned_slot_id (booking realized from a slot)
                        + request_reason (ad-hoc out-of-plan request)

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-22 15:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- new enum: time_slot ---
    op.execute("CREATE TYPE time_slot AS ENUM ('morning','afternoon','evening')")
    time_slot = postgresql.ENUM(name="time_slot", create_type=False)

    # --- extend booking_status with the approval-lifecycle states ---
    # PostgreSQL 12+ allows ADD VALUE inside a transaction; the new values are
    # not referenced in this migration, only by the app at runtime.
    op.execute("ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'pending_approval'")
    op.execute("ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'rejected'")

    # --- groups ---
    op.create_table(
        "groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("class_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("leader_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("class_id", "name", name="uq_groups_class_name"),
    )
    op.create_index("ix_groups_class_id", "groups", ["class_id"])

    # --- enrollments.group_id ---
    op.add_column(
        "enrollments",
        sa.Column("group_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("groups.id", ondelete="SET NULL"), nullable=True),
    )

    # --- planned_slots ---
    op.create_table(
        "planned_slots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("class_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day_of_week", sa.Integer, nullable=False),
        sa.Column("time_slot", time_slot, nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("day_of_week BETWEEN 1 AND 7", name="ck_planned_slots_dow"),
        sa.UniqueConstraint("device_id", "day_of_week", "time_slot",
                            name="uq_planned_slots_device_day_slot"),
    )
    op.create_index("ix_planned_slots_class_id", "planned_slots", ["class_id"])
    op.create_index("ix_planned_slots_device_id", "planned_slots", ["device_id"])
    op.create_index("ix_planned_slots_group_id", "planned_slots", ["group_id"])

    # --- bookings: approval-lifecycle columns ---
    op.add_column("bookings", sa.Column("request_reason", sa.String(500), nullable=True))
    op.add_column(
        "bookings",
        sa.Column("planned_slot_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("planned_slots.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "bookings",
        sa.Column("decided_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("bookings", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bookings", sa.Column("decision_note", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("bookings", "decision_note")
    op.drop_column("bookings", "decided_at")
    op.drop_column("bookings", "decided_by")
    op.drop_column("bookings", "planned_slot_id")
    op.drop_column("bookings", "request_reason")
    op.drop_index("ix_planned_slots_group_id", table_name="planned_slots")
    op.drop_index("ix_planned_slots_device_id", table_name="planned_slots")
    op.drop_index("ix_planned_slots_class_id", table_name="planned_slots")
    op.drop_table("planned_slots")
    op.drop_column("enrollments", "group_id")
    op.drop_index("ix_groups_class_id", table_name="groups")
    op.drop_table("groups")
    op.execute("DROP TYPE time_slot")
    # booking_status: PostgreSQL cannot drop enum values — pending_approval /
    # rejected are left in the type (harmless).
