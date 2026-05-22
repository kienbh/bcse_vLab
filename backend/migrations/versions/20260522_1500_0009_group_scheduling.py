"""M6: group scheduling — groups, planned_slots, booking approval lifecycle.

Adds the weekly group-scheduling model:
  - groups            : student groups (nhóm) within a class, each with a leader
  - enrollments.group_id : which group a student belongs to
  - planned_slots     : lecturer's recurring weekly plan (group x kit x day x slot)
  - bookings          : + pending_approval / rejected statuses
                        + decided_by / decided_at / decision_note
                        + planned_slot_id (booking realized from a slot)
                        + request_reason (ad-hoc out-of-plan request)

Written fully idempotent (IF [NOT] EXISTS): an earlier session added
bookings.decided_by/decided_at/decision_note directly via SQL, so a plain
add_column collides. Idempotent DDL is safe whether those columns pre-exist
or not, and lets the migration be re-run after a partial failure.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-22 15:00:00
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- new enum: time_slot (idempotent) ---
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE time_slot AS ENUM ('morning','afternoon','evening');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    # --- extend booking_status with the approval-lifecycle states ---
    op.execute("ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'pending_approval'")
    op.execute("ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'rejected'")

    # --- groups ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS groups (
            id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
            class_id    uuid NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
            name        varchar(64) NOT NULL,
            leader_id   uuid REFERENCES users(id) ON DELETE SET NULL,
            created_at  timestamptz NOT NULL DEFAULT now(),
            updated_at  timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_groups_class_name UNIQUE (class_id, name)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_groups_class_id ON groups (class_id)")

    # --- enrollments.group_id ---
    op.execute(
        "ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS group_id uuid "
        "REFERENCES groups(id) ON DELETE SET NULL"
    )

    # --- planned_slots ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS planned_slots (
            id           uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
            class_id     uuid NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
            device_id    uuid NOT NULL REFERENCES devices(id) ON DELETE RESTRICT,
            group_id     uuid NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            day_of_week  integer NOT NULL,
            time_slot    time_slot NOT NULL,
            created_by   uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at   timestamptz NOT NULL DEFAULT now(),
            updated_at   timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_planned_slots_dow CHECK (day_of_week BETWEEN 1 AND 7),
            CONSTRAINT uq_planned_slots_device_day_slot
                UNIQUE (device_id, day_of_week, time_slot)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_planned_slots_class_id ON planned_slots (class_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_planned_slots_device_id ON planned_slots (device_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_planned_slots_group_id ON planned_slots (group_id)")

    # --- bookings: approval-lifecycle columns ---
    # decided_by / decided_at / decision_note may already exist (added by direct
    # SQL in an earlier session); IF NOT EXISTS keeps this safe either way.
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS request_reason varchar(500)")
    op.execute(
        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS planned_slot_id uuid "
        "REFERENCES planned_slots(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS decided_by uuid "
        "REFERENCES users(id) ON DELETE SET NULL"
    )
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS decided_at timestamptz")
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS decision_note varchar(500)")


def downgrade() -> None:
    op.execute("ALTER TABLE bookings DROP COLUMN IF EXISTS decision_note")
    op.execute("ALTER TABLE bookings DROP COLUMN IF EXISTS decided_at")
    op.execute("ALTER TABLE bookings DROP COLUMN IF EXISTS decided_by")
    op.execute("ALTER TABLE bookings DROP COLUMN IF EXISTS planned_slot_id")
    op.execute("ALTER TABLE bookings DROP COLUMN IF EXISTS request_reason")
    op.execute("DROP TABLE IF EXISTS planned_slots")
    op.execute("ALTER TABLE enrollments DROP COLUMN IF EXISTS group_id")
    op.execute("DROP TABLE IF EXISTS groups")
    op.execute("DROP TYPE IF EXISTS time_slot")
    # booking_status enum values pending_approval / rejected: PostgreSQL cannot
    # drop enum values — left in the type (harmless).
