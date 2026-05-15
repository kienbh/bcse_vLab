"""Domain enumerations matching docs/04-database-schema.md."""
from enum import StrEnum


class UserRole(StrEnum):
    STUDENT = "student"
    TA = "ta"
    LECTURER = "lecturer"
    ADMIN = "admin"


class DeviceType(StrEnum):
    FPGA_KV260 = "fpga_kv260"
    JETSON_NANO = "jetson_nano"
    JETSON_ORIN = "jetson_orin"
    RPI4 = "rpi4"
    RPI5 = "rpi5"


class DeviceStatus(StrEnum):
    AVAILABLE = "available"
    IN_USE = "in_use"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"


class PlugType(StrEnum):
    TASMOTA = "tasmota"
    SHELLY = "shelly"


class BookingGrantedVia(StrEnum):
    CLASS = "class"
    SPECIAL_ACCESS = "special_access"


class BookingStatus(StrEnum):
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    KICKED = "kicked"


class ResetRequestStatus(StrEnum):
    PENDING = "pending"        # waiting for admin/lecturer approval
    APPROVED = "approved"      # decided OK — plug action queued
    REJECTED = "rejected"      # decided NO — no plug action
    COMPLETED = "completed"    # approved + plug power-cycled OK
    FAILED = "failed"          # approved + plug error
