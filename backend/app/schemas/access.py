"""VPS access — request + grant DTOs."""
from datetime import datetime, timedelta
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


_MAX_DAYS = 30


def _check_window(start: datetime, end: datetime) -> None:
    if end <= start:
        raise ValueError("end must be after start")
    if (end - start) > timedelta(days=_MAX_DAYS):
        raise ValueError(f"Khoảng truy cập tối đa {_MAX_DAYS} ngày")


class AccessRequestCreate(BaseModel):
    """Student creates a request for VPS access. `device_id` must be a VPS."""
    device_id: UUID
    requested_from: datetime
    requested_to: datetime
    reason: str = Field(..., min_length=10, max_length=500)

    @model_validator(mode="after")
    def _validate_window(self):
        _check_window(self.requested_from, self.requested_to)
        return self


class AccessRequestDecide(BaseModel):
    """Lecturer approves/rejects. If approved + override window provided,
    SpecialAccess uses those dates instead of the requested ones."""
    decision_note: str | None = Field(None, max_length=500)
    override_from: datetime | None = None
    override_to: datetime | None = None

    @model_validator(mode="after")
    def _validate_override(self):
        if self.override_from is not None or self.override_to is not None:
            if self.override_from is None or self.override_to is None:
                raise ValueError("override_from and override_to must both be set or both omitted")
            _check_window(self.override_from, self.override_to)
        return self


class AccessRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    student_id: UUID
    device_id: UUID
    requested_from: datetime
    requested_to: datetime
    reason: str
    status: str
    decided_by: UUID | None
    decided_at: datetime | None
    decision_note: str | None
    granted_access_id: UUID | None
    created_at: datetime
    # joined fields for the list/queue view
    student_email: str | None = None
    student_name: str | None = None
    device_name: str | None = None


class VpsGrantCreate(BaseModel):
    """Lecturer directly grants VPS access without a prior request."""
    user_email: EmailStr
    device_id: UUID
    valid_from: datetime
    valid_to: datetime
    reason: str = Field(..., min_length=10, max_length=500)

    @model_validator(mode="after")
    def _validate_window(self):
        _check_window(self.valid_from, self.valid_to)
        return self


class VpsGrantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    device_id: UUID
    valid_from: datetime
    valid_to: datetime
    reason: str
    granted_by: UUID
    granted_at: datetime
    revoked_at: datetime | None
    # joined
    student_email: str | None = None
    student_name: str | None = None
    device_name: str | None = None
