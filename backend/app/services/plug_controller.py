"""Smart-plug controllers — Tasmota / Shelly / mock fallback.

All three implement the same `PlugAdapter` interface so device reset code is plug-agnostic.
"""
from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.models import PlugType


@dataclass
class PlugState:
    on: bool
    raw: dict


class PlugAdapter(ABC):
    @abstractmethod
    async def power_off(self) -> PlugState: ...
    @abstractmethod
    async def power_on(self) -> PlugState: ...
    @abstractmethod
    async def get_state(self) -> PlugState: ...

    async def power_cycle(self, off_seconds: int = 5) -> PlugState:
        await self.power_off()
        await asyncio.sleep(off_seconds)
        return await self.power_on()


def _mock_mode() -> bool:
    return os.environ.get("MOCK_PLUGS", "true").lower() in {"1", "true", "yes"}


class MockAdapter(PlugAdapter):
    """No-op adapter used when MOCK_PLUGS=true or plug pool unreachable."""

    def __init__(self, label: str):
        self.label = label
        self._state = PlugState(on=True, raw={"mock": True})

    async def power_off(self) -> PlugState:
        self._state = PlugState(on=False, raw={"mock": True, "label": self.label})
        return self._state

    async def power_on(self) -> PlugState:
        self._state = PlugState(on=True, raw={"mock": True, "label": self.label})
        return self._state

    async def get_state(self) -> PlugState:
        return self._state


class TasmotaAdapter(PlugAdapter):
    def __init__(self, ip: str, relay: int = 1, token: str | None = None):
        self.base = f"http://{ip}/cm"
        self.relay = relay
        self.token = token

    async def _cmd(self, cmnd: str) -> dict:
        params = {"cmnd": cmnd}
        if self.token:
            params["password"] = self.token
        s = get_settings()
        async with httpx.AsyncClient(timeout=s.PLUG_API_TIMEOUT_SECONDS) as client:
            r = await client.get(self.base, params=params)
            r.raise_for_status()
            return r.json()

    async def power_off(self) -> PlugState:
        d = await self._cmd(f"Power{self.relay} Off")
        return PlugState(on=str(d.get(f"POWER{self.relay}", "")).upper() == "ON", raw=d)

    async def power_on(self) -> PlugState:
        d = await self._cmd(f"Power{self.relay} On")
        return PlugState(on=str(d.get(f"POWER{self.relay}", "")).upper() == "ON", raw=d)

    async def get_state(self) -> PlugState:
        d = await self._cmd(f"Power{self.relay}")
        return PlugState(on=str(d.get(f"POWER{self.relay}", "")).upper() == "ON", raw=d)


class ShellyAdapter(PlugAdapter):
    def __init__(self, ip: str, relay: int = 0, token: str | None = None):
        self.base = f"http://{ip}/relay/{relay}"
        self.token = token

    async def _action(self, action: str | None) -> dict:
        s = get_settings()
        params: dict[str, str] = {}
        if action:
            params["turn"] = action
        async with httpx.AsyncClient(timeout=s.PLUG_API_TIMEOUT_SECONDS) as client:
            r = await client.get(self.base, params=params)
            r.raise_for_status()
            return r.json()

    async def power_off(self) -> PlugState:
        d = await self._action("off")
        return PlugState(on=bool(d.get("ison", False)), raw=d)

    async def power_on(self) -> PlugState:
        d = await self._action("on")
        return PlugState(on=bool(d.get("ison", False)), raw=d)

    async def get_state(self) -> PlugState:
        d = await self._action(None)
        return PlugState(on=bool(d.get("ison", False)), raw=d)


def make_adapter(*, plug_type: PlugType | str, plug_ip: str, relay: int = 1, token: str | None = None) -> PlugAdapter:
    if _mock_mode():
        return MockAdapter(label=f"{plug_type}@{plug_ip}")
    pt = plug_type.value if isinstance(plug_type, PlugType) else plug_type
    if pt == "tasmota":
        return TasmotaAdapter(plug_ip, relay=relay, token=token)
    if pt == "shelly":
        return ShellyAdapter(plug_ip, relay=relay - 1, token=token)
    raise ValueError(f"unknown plug type: {pt}")
