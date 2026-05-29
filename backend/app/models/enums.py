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
    VPS = "vps"  # máy chủ ảo Proxmox (BCSE i7 node) — see migration 0008


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
    AUTO = "auto"                # self-booked VPS block (round-robin queue)


class BookingStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"  # M6: ad-hoc request awaiting lecturer
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    REJECTED = "rejected"  # M6: ad-hoc request denied by lecturer


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


class AccessRequestStatus(StrEnum):
    """VPS access request lifecycle. Approved → SpecialAccess row created."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"   # student withdrew before decision


class DevicePowerState(StrEnum):
    """ADR-0013 / M5.9: orthogonal to DeviceStatus. Reflects the smart plug
    state when the API works, or the admin's manual toggle when it doesn't
    (pilot — plugs in Hoà Lạc still need someone to flip them by hand).

    Difference from DeviceStatus:
      - status: is this kit usable? (available / in_use / maintenance / offline)
      - power_state: is electricity actually flowing? (on / off / resetting)
    """
    ON = "on"
    OFF = "off"
    RESETTING = "resetting"


class TimeSlot(StrEnum):
    """M6: fixed daily usage slots for the weekly group schedule.

    Display hours: morning 08:00–12:00, afternoon 13:00–17:00,
    evening 18:00–22:00 (see app.core.config TIME_SLOT_* settings).
    """
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
