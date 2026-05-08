"""M1: initial schema (11 tables + GIST EXCLUDE on bookings)

Revision ID: 0001
Revises:
Create Date: 2026-05-08 11:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Required extensions (also applied via init-extensions.sql, but defensive)
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    # Pre-create enum types and pass create_type=False below to avoid
    # SQLAlchemy auto-creating them again during op.create_table.
    op.execute("CREATE TYPE user_role AS ENUM ('student','ta','lecturer','admin')")
    op.execute("CREATE TYPE device_type AS ENUM ('fpga_kv260','jetson_nano','jetson_orin','rpi4','rpi5')")
    op.execute("CREATE TYPE device_status AS ENUM ('available','in_use','maintenance','offline')")
    op.execute("CREATE TYPE plug_type AS ENUM ('tasmota','shelly')")
    op.execute("CREATE TYPE booking_granted_via AS ENUM ('class','special_access')")
    op.execute("CREATE TYPE booking_status AS ENUM ('scheduled','active','completed','cancelled','no_show')")
    op.execute("CREATE TYPE session_status AS ENUM ('active','completed','failed','kicked')")

    user_role = postgresql.ENUM(name="user_role", create_type=False)
    device_type = postgresql.ENUM(name="device_type", create_type=False)
    device_status = postgresql.ENUM(name="device_status", create_type=False)
    plug_type = postgresql.ENUM(name="plug_type", create_type=False)
    booking_granted_via = postgresql.ENUM(name="booking_granted_via", create_type=False)
    booking_status = postgresql.ENUM(name="booking_status", create_type=False)
    session_status = postgresql.ENUM(name="session_status", create_type=False)

    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", user_role, nullable=False, server_default="student"),
        sa.Column("oidc_subject", sa.String(255), unique=True, nullable=True),
        sa.Column("student_code", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_users_role_active", "users", ["role", "is_active"])
    op.create_index("ix_users_student_code", "users", ["student_code"])

    # --- devices ---
    op.create_table(
        "devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("device_type", device_type, nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("internal_ip", postgresql.INET, nullable=False),
        sa.Column("ssh_port", sa.Integer, nullable=False, server_default="22"),
        sa.Column("ssh_user", sa.String(32), nullable=False, server_default="student"),
        sa.Column("status", device_status, nullable=False, server_default="available"),
        sa.Column("capabilities", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    op.create_table(
        "plug_mappings",
        sa.Column("device_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("plug_ip", postgresql.INET, nullable=False),
        sa.Column("plug_type", plug_type, nullable=False, server_default="tasmota"),
        sa.Column("plug_relay_index", sa.Integer, nullable=False, server_default="1"),
        sa.Column("api_token", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_plug_mappings_plug_ip", "plug_mappings", ["plug_ip"])

    op.create_table(
        "device_credentials",
        sa.Column("device_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("encrypted_admin_key", sa.LargeBinary, nullable=False),
        sa.Column("key_algorithm", sa.String(32), nullable=False, server_default="ed25519"),
        sa.Column("rotated_at", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # --- classes ---
    op.create_table(
        "classes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("semester", sa.String(32), nullable=False),
        sa.Column("lecturer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("ends_at > starts_at", name="ck_classes_time_order"),
    )
    op.create_index("ix_classes_lecturer", "classes", ["lecturer_id"])

    op.create_table(
        "enrollments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("class_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enrolled_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("class_id", "user_id", name="uq_enrollments_class_user"),
    )
    op.create_index("ix_enrollments_user_active", "enrollments", ["user_id", "is_active"])

    op.create_table(
        "class_device_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("class_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("allowed_time_windows", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("per_student_weekly_hours", sa.Integer, nullable=False, server_default="5"),
        sa.Column("per_student_max_concurrent", sa.Integer, nullable=False, server_default="1"),
        sa.Column("per_student_max_advance_days", sa.Integer, nullable=False, server_default="7"),
        sa.Column("granted_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("revoke_reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("valid_to > valid_from", name="ck_cda_time_order"),
        sa.UniqueConstraint("class_id", "device_id", "valid_from", name="uq_cda_class_device_from"),
    )
    op.execute(
        "CREATE INDEX ix_cda_active ON class_device_assignments (class_id, device_id) "
        "WHERE revoked_at IS NULL"
    )

    # --- special_access ---
    op.create_table(
        "special_access",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("allowed_time_windows", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("weekly_hours_limit", sa.Integer, nullable=True),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("granted_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("revoke_reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("valid_to > valid_from", name="ck_sa_time_order"),
    )
    op.execute(
        "CREATE INDEX ix_sa_active ON special_access (user_id, device_id) "
        "WHERE revoked_at IS NULL"
    )

    # --- bookings (with GIST EXCLUDE — last-line race safety) ---
    op.create_table(
        "bookings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("granted_via", booking_granted_via, nullable=False),
        sa.Column("class_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("classes.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("special_access_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("special_access.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", booking_status, nullable=False, server_default="scheduled"),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("end_time > start_time", name="ck_bookings_time_order"),
        sa.CheckConstraint(
            "EXTRACT(EPOCH FROM (end_time - start_time)) <= 8 * 3600",
            name="ck_bookings_max_duration_8h",
        ),
        sa.CheckConstraint(
            "(granted_via = 'class' AND class_id IS NOT NULL AND special_access_id IS NULL) "
            "OR (granted_via = 'special_access' AND special_access_id IS NOT NULL "
            "AND class_id IS NULL)",
            name="ck_bookings_grant_xor",
        ),
    )
    op.create_index("ix_bookings_user_status", "bookings", ["user_id", "status"])
    op.execute(
        "CREATE INDEX ix_bookings_device_active ON bookings (device_id) "
        "WHERE status IN ('scheduled','active')"
    )
    # GIST EXCLUDE — the canonical no-overlap constraint per docs/04 + access_control
    op.execute(
        """
        ALTER TABLE bookings ADD CONSTRAINT no_overlap EXCLUDE USING gist (
            device_id WITH =,
            tstzrange(start_time, end_time, '[)') WITH &&
        ) WHERE (status IN ('scheduled', 'active'))
        """
    )

    # --- sessions ---
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("ssh_pubkey", sa.String(1024), nullable=False),
        sa.Column("ssh_fingerprint", sa.String(128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", session_status, nullable=False, server_default="active"),
        sa.Column("observed_by_lecturer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kicked_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kick_reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_sessions_fp", "sessions", ["ssh_fingerprint"])
    op.create_index("ix_sessions_status", "sessions", ["status"])

    # --- audit_logs ---
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=True),
        sa.Column("target_id", sa.String(64), nullable=True),
        sa.Column("details", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("ip_address", postgresql.INET, nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("success", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_audit_action_ts", "audit_logs", ["action", "timestamp"])
    op.create_index("ix_audit_actor", "audit_logs", ["actor_id"])

    # --- user_quotas ---
    op.create_table(
        "user_quotas",
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("weekly_hours_limit", sa.Integer, nullable=False, server_default="10"),
        sa.Column("max_concurrent_bookings", sa.Integer, nullable=False, server_default="2"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("user_quotas")
    op.drop_table("audit_logs")
    op.drop_table("sessions")
    op.execute("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS no_overlap")
    op.drop_table("bookings")
    op.drop_table("special_access")
    op.drop_table("class_device_assignments")
    op.drop_table("enrollments")
    op.drop_table("classes")
    op.drop_table("device_credentials")
    op.drop_table("plug_mappings")
    op.drop_table("devices")
    op.drop_table("users")
    for enum_name in (
        "session_status", "booking_status", "booking_granted_via",
        "plug_type", "device_status", "device_type", "user_role",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
