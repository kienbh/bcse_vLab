"""Pydantic DTOs for API responses + requests."""
from app.schemas.booking import BookingCreate, BookingOut
from app.schemas.class_ import (
    AssignmentCreate,
    AssignmentUpdate,
    ClassCreate,
    ClassDeviceAssignmentOut,
    ClassOut,
    EnrollmentBulkResult,
    EnrollmentOut,
    SpecialAccessCreate,
    SpecialAccessOut,
)
from app.schemas.device import DeviceCreate, DeviceOut, DeviceUpdate, PlugMappingIn
from app.schemas.user import UserOut

__all__ = [
    "UserOut",
    "DeviceCreate",
    "DeviceOut",
    "DeviceUpdate",
    "PlugMappingIn",
    "ClassCreate",
    "ClassOut",
    "EnrollmentOut",
    "EnrollmentBulkResult",
    "AssignmentCreate",
    "AssignmentUpdate",
    "ClassDeviceAssignmentOut",
    "SpecialAccessCreate",
    "SpecialAccessOut",
    "BookingCreate",
    "BookingOut",
]
