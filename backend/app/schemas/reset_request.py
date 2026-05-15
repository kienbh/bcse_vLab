"""Pydantic schemas for reset request queue."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ResetRequestStatus


class ResetRequestCreate(BaseModel):
    device_id: UUID
    reason: str = Field(..., min_length=3, max_length=500)


class ResetRequestDecide(BaseModel):
    decision_note: str | None = Field(None, max_length=500)


class ResetRequestOut(BaseModel):
    id: UUID
    requester_id: UUID
    requester_display: str  # student_code or full_name (admin/lecturer view)
    device_id: UUID
    device_name: str
    booking_id: UUID | None
    reason: str
    status: ResetRequestStatus
    requested_at: datetime
    decided_by: UUID | None
    decided_at: datetime | None
    decision_note: str | None
    completed_at: datetime | None
    auto_approved: bool = False  # convenience flag (decided_by IS NULL AND status != pending)
