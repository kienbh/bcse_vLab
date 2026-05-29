"""DTOs for VPS block-booking (self-service 4h slots)."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class BlockBookingCreate(BaseModel):
    start_time: datetime
    end_time: datetime


class BlockBookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    device_id: UUID
    start_time: datetime
    end_time: datetime
    status: str
    granted_via: str
    # joined-in for the calendar view — None when fanout isn't worth it
    student_email: str | None = None
    student_name: str | None = None
    is_mine: bool = False
