"""SQLAlchemy ORM models — schema per docs/04-database-schema.md."""
from app.models.access import SpecialAccess
from app.models.audit import AuditLog
from app.models.base import Base, TimestampMixin
from app.models.booking import Booking, Session
from app.models.class_ import Class, ClassDeviceAssignment, Enrollment
from app.models.device import Device, DeviceCredential, PlugMapping
from app.models.gateway import GatewayAuthLog, GatewaySession
from app.models.enums import (
    BookingGrantedVia,
    BookingStatus,
    DevicePowerState,
    DeviceStatus,
    DeviceType,
    PlugType,
    ResetRequestStatus,
    SessionStatus,
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
    "SpecialAccess",
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
]
