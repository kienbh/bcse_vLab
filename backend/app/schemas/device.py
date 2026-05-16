from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress, field_validator

from app.models import DevicePowerState, DeviceStatus, DeviceType, PlugType


class PlugMappingIn(BaseModel):
    plug_ip: IPvAnyAddress
    plug_type: PlugType = PlugType.TASMOTA
    plug_relay_index: int = Field(1, ge=1, le=8)


class DeviceCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z0-9-]+$")
    device_type: DeviceType
    model: str = Field(..., max_length=128)
    internal_ip: IPvAnyAddress
    ssh_port: int = Field(22, ge=1, le=65535)
    ssh_user: str = Field("student", max_length=32)
    capabilities: dict = Field(default_factory=dict)
    notes: str | None = Field(None, max_length=500)
    plug: PlugMappingIn | None = None


class DeviceUpdate(BaseModel):
    model: str | None = None
    internal_ip: IPvAnyAddress | None = None
    status: DeviceStatus | None = None
    capabilities: dict | None = None
    notes: str | None = None


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    device_type: DeviceType
    model: str
    internal_ip: str
    ssh_port: int
    ssh_user: str
    status: DeviceStatus
    power_state: DevicePowerState
    power_state_changed_at: datetime
    capabilities: dict
    notes: str | None

    @field_validator("internal_ip", mode="before")
    @classmethod
    def _ip_to_str(cls, v):
        return str(v) if v is not None else v
