"""VPS access — request table + relax booking 8h cap to 31 days.

Adds:
  - access_requests           student-initiated VPS access requests
  - access_request_status     pending/approved/rejected/cancelled
  - bookings constraint       8h → 31 days (VPS long-running grants need it;
                              non-VPS still enforced ≤8h in app layer at
                              access_control.can_user_book_device)

Idempotent (DO/IF NOT EXISTS) — see migration 0009 for the lesson.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-25 11:00:00
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- new enum: access_request_status ---
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE access_request_status
                AS ENUM ('pending','approved','rejected','cancelled');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    # --- access_requests ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS access_requests (
            id                   uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
            student_id           uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            device_id            uuid NOT NULL REFERENCES devices(id) ON DELETE RESTRICT,
            requested_from       timestamptz NOT NULL,
            requested_to         timestamptz NOT NULL,
            reason               varchar(500) NOT NULL,
            status               access_request_status NOT NULL DEFAULT 'pending',
            decided_by           uuid REFERENCES users(id) ON DELETE SET NULL,
            decided_at           timestamptz,
            decision_note        varchar(500),
            granted_access_id    uuid REFERENCES special_access(id) ON DELETE SET NULL,
            created_at           timestamptz NOT NULL DEFAULT now(),
            updated_at           timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_ar_time_order CHECK (requested_to > requested_from),
            CONSTRAINT ck_ar_max_30_days CHECK (
                EXTRACT(EPOCH FROM (requested_to - requested_from)) <= 30 * 86400
            )
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_ar_student ON access_requests (student_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ar_pending ON access_requests (device_id) "
        "WHERE status = 'pending'"
    )

    # --- bookings: relax 8h cap to 31 days for VPS multi-day grants ---
    # CHECK can't reference other tables, so we widen for all device types.
    # Non-VPS bookings still get the 8h enforcement at the application layer
    # (access_control.can_user_book_device + Settings.BOOKING_MAX_DURATION_HOURS).
    op.execute(
        "ALTER TABLE bookings DROP CONSTRAINT IF EXISTS ck_bookings_max_duration_8h"
    )
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE bookings ADD CONSTRAINT ck_bookings_max_duration_31d
            CHECK (EXTRACT(EPOCH FROM (end_time - start_time)) <= 31 * 86400);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    # --- bookings.shared_resource ---
    # Marks bookings that should bypass the per-device no-overlap rule (VPS).
    op.execute(
        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS "
        "shared_resource boolean NOT NULL DEFAULT false"
    )

    # Recreate the GIST EXCLUDE with the new exemption.
    op.execute("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS no_overlap")
    op.execute(
        """
        ALTER TABLE bookings ADD CONSTRAINT no_overlap EXCLUDE USING gist (
            device_id WITH =,
            tstzrange(start_time, end_time, '[)') WITH &&
        ) WHERE (status IN ('scheduled', 'active') AND NOT shared_resource)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS access_requests")
    op.execute("DROP TYPE IF EXISTS access_request_status")
    op.execute(
        "ALTER TABLE bookings DROP CONSTRAINT IF EXISTS ck_bookings_max_duration_31d"
    )
    op.execute(
        """
        ALTER TABLE bookings ADD CONSTRAINT ck_bookings_max_duration_8h
        CHECK (EXTRACT(EPOCH FROM (end_time - start_time)) <= 8 * 3600)
        """
    )
    op.execute("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS no_overlap")
    op.execute(
        """
        ALTER TABLE bookings ADD CONSTRAINT no_overlap EXCLUDE USING gist (
            device_id WITH =,
            tstzrange(start_time, end_time, '[)') WITH &&
        ) WHERE (status IN ('scheduled', 'active'))
        """
    )
    op.execute("ALTER TABLE bookings DROP COLUMN IF EXISTS shared_resource")
