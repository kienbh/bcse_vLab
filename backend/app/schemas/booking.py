from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import BookingGrantedVia, BookingStatus


class BookingCreate(BaseModel):
    device_id: UUID
    start_time: datetime
    end_time: datetime
    notes: str | None = Field(None, max_length=500)


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    device_id: UUID
    granted_via: BookingGrantedVia
    class_id: UUID | None
    special_access_id: UUID | None
    start_time: datetime
    end_time: datetime
    status: BookingStatus
    notes: str | None
    # M6 — approval lifecycle (visible to the student so they see request state)
    request_reason: str | None = None
    decision_note: str | None = None
    decided_at: datetime | None = None
    planned_slot_id: UUID | None = None
