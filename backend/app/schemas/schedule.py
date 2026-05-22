"""M6 group-scheduling DTOs — single-student enrollment, groups, weekly plan."""
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import TimeSlot


# --- enrollment: single-student add (replaces CSV import) --------------------

class EnrollStudent(BaseModel):
    email: EmailStr
    full_name: str | None = Field(None, max_length=255)
    student_code: str | None = Field(None, max_length=64)


class EnrollmentRow(BaseModel):
    """An enrollment enriched with the student's identity + group — table row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    email: str
    full_name: str
    student_code: str | None = None
    group_id: UUID | None = None
    group_name: str | None = None
    is_active: bool


# --- groups (nhóm) ----------------------------------------------------------

class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)


class GroupUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=64)
    leader_id: UUID | None = None  # must be an active member of the group


class GroupMemberRow(BaseModel):
    user_id: UUID
    email: str
    full_name: str
    is_leader: bool


class GroupOut(BaseModel):
    id: UUID
    class_id: UUID
    name: str
    leader_id: UUID | None = None
    members: list[GroupMemberRow] = Field(default_factory=list)


class GroupMemberAdd(BaseModel):
    user_id: UUID


# --- weekly planned slots ---------------------------------------------------

class PlannedSlotCreate(BaseModel):
    device_id: UUID
    group_id: UUID
    day_of_week: int = Field(..., ge=1, le=7)  # 1=Mon .. 7=Sun
    time_slot: TimeSlot


class PlannedSlotOut(BaseModel):
    id: UUID
    class_id: UUID
    device_id: UUID
    device_name: str
    group_id: UUID
    group_name: str
    day_of_week: int
    time_slot: TimeSlot
