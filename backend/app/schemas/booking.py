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
    approved: bool | None = None
    decision_note: str | None = None
