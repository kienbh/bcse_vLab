from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class TimeWindow(BaseModel):
    day_of_week: int = Field(..., ge=1, le=7)
    start: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end: str = Field(..., pattern=r"^\d{2}:\d{2}$")


class ClassCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=32)
    name: str = Field(..., max_length=255)
    semester: str = Field(..., max_length=32)
    starts_at: datetime
    ends_at: datetime
    lecturer_id: UUID | None = None  # admin can override; lecturer creating gets self

    @field_validator("ends_at")
    @classmethod
    def _ends_after_starts(cls, v: datetime, info) -> datetime:
        starts = info.data.get("starts_at")
        if starts and v <= starts:
            raise ValueError("ends_at must be after starts_at")
        return v


class ClassOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    semester: str
    lecturer_id: UUID
    starts_at: datetime
    ends_at: datetime
    is_active: bool


class EnrollmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    class_id: UUID
    user_id: UUID
    is_active: bool


class EnrollmentBulkResult(BaseModel):
    enrolled: int
    created_users: int
    skipped: list[str] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)


class AssignmentCreate(BaseModel):
    device_id: UUID
    valid_from: datetime
    valid_to: datetime
    allowed_time_windows: list[TimeWindow] = Field(default_factory=list)
    per_student_weekly_hours: int = Field(5, ge=1, le=168)
    per_student_max_concurrent: int = Field(1, ge=1, le=5)
    per_student_max_advance_days: int = Field(7, ge=1, le=90)


class ClassDeviceAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    class_id: UUID
    device_id: UUID
    valid_from: datetime
    valid_to: datetime
    allowed_time_windows: list
    per_student_weekly_hours: int
    per_student_max_concurrent: int
    per_student_max_advance_days: int
    revoked_at: datetime | None


class SpecialAccessCreate(BaseModel):
    user_email: EmailStr
    device_id: UUID
    valid_from: datetime
    valid_to: datetime
    allowed_time_windows: list[TimeWindow] = Field(default_factory=list)
    weekly_hours_limit: int | None = Field(None, ge=1, le=168)
    reason: str = Field(..., min_length=10, max_length=500)


class SpecialAccessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    device_id: UUID
    valid_from: datetime
    valid_to: datetime
    allowed_time_windows: list
    weekly_hours_limit: int | None
    reason: str
    revoked_at: datetime | None
