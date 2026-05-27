"""Pydantic DTOs for API responses + requests."""
from app.schemas.access import (
    AccessRequestCreate,
    AccessRequestDecide,
    AccessRequestOut,
    VpsGrantCreate,
    VpsGrantOut,
)
from app.schemas.booking import BookingCreate, BookingOut
from app.schemas.vps_block import BlockBookingCreate, BlockBookingOut
from app.schemas.class_ import (
    AssignmentCreate,
    ClassCreate,
    ClassDeviceAssignmentOut,
    ClassOut,
    EnrollmentBulkResult,
    EnrollmentOut,
    SpecialAccessCreate,
    SpecialAccessOut,
)
from app.schemas.device import DeviceCreate, DeviceOut, DeviceUpdate, PlugMappingIn
from app.schemas.reset_request import (
    ResetRequestCreate,
    ResetRequestDecide,
    ResetRequestOut,
)
from app.schemas.schedule import (
    EnrollmentRow,
    EnrollStudent,
    GroupCreate,
    GroupMemberAdd,
    GroupMemberRow,
    GroupOut,
    GroupUpdate,
    MyScheduleOut,
    MySlotOut,
    PendingRequestOut,
    PlannedSlotCreate,
    PlannedSlotOut,
    RequestCreate,
    RequestDecide,
)
from app.schemas.user import UserOut

__all__ = [
    "AccessRequestCreate",
    "AccessRequestDecide",
    "AccessRequestOut",
    "VpsGrantCreate",
    "VpsGrantOut",
    "BlockBookingCreate",
    "BlockBookingOut",
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
    "ClassDeviceAssignmentOut",
    "SpecialAccessCreate",
    "SpecialAccessOut",
    "BookingCreate",
    "BookingOut",
    "ResetRequestCreate",
    "ResetRequestDecide",
    "ResetRequestOut",
    # M6 group scheduling
    "EnrollStudent",
    "EnrollmentRow",
    "GroupCreate",
    "GroupUpdate",
    "GroupOut",
    "GroupMemberRow",
    "GroupMemberAdd",
    "PlannedSlotCreate",
    "PlannedSlotOut",
    "MySlotOut",
    "MyScheduleOut",
    "RequestCreate",
    "RequestDecide",
    "PendingRequestOut",
]
