"""SQLAlchemy ORM models — schema per docs/04-database-schema.md."""
from app.models.access import SpecialAccess
from app.models.access_request import AccessRequest
from app.models.audit import AuditLog
from app.models.base import Base, TimestampMixin
from app.models.booking import Booking, Session
from app.models.class_ import Class, ClassDeviceAssignment, Enrollment, Group
from app.models.device import Device, DeviceCredential, PlugMapping
from app.models.gateway import GatewayAuthLog, GatewaySession
from app.models.schedule import PlannedSlot
from app.models.enums import (
    AccessRequestStatus,
    BookingGrantedVia,
    BookingStatus,
    DevicePowerState,
    DeviceStatus,
    DeviceType,
    PlugType,
    ResetRequestStatus,
    SessionStatus,
    TimeSlot,
    UserRole,
)
from app.models.quota import UserQuota
from app.models.reset_request import ResetRequest
from app.models.user import User

__all__ = [
    "Base",
    "TimestampMixin",
    # tables
    "User",
    "Device",
    "PlugMapping",
    "DeviceCredential",
    "Class",
    "Enrollment",
    "ClassDeviceAssignment",
    "Group",
    "PlannedSlot",
    "SpecialAccess",
    "AccessRequest",
    "Booking",
    "Session",
    "GatewaySession",
    "GatewayAuthLog",
    "AuditLog",
    "UserQuota",
    "ResetRequest",
    # enums
    "UserRole",
    "DeviceType",
    "DeviceStatus",
    "DevicePowerState",
    "PlugType",
    "BookingGrantedVia",
    "BookingStatus",
    "SessionStatus",
    "ResetRequestStatus",
    "AccessRequestStatus",
    "TimeSlot",
]
