"""Background probe — TCP-connect to each device's SSH port and reflect the
result into `devices.power_state`.

Pilot reality: Hoà Lạc smart plugs don't expose a programmable API, so the
admin toggle in /admin/devices was the only signal. This prober adds a
second signal that doesn't require human action — if the kit's sshd accepts
a TCP connection, we say `on`; if it times out, we say `off`.

Why TCP-connect, not actual SSH:
  - kit sshd accepting the SYN means the OS is running
  - we don't need to authenticate; saves a round trip + key handling
  - ICMP-ping would be lighter but many kits have iptables dropping ICMP

When NOT to override the stored power_state:
  - power_state == RESETTING — admin is mid-cycle by hand; let them keep
    control until they click "Đã reset xong (tay)"
  - device.status == MAINTENANCE — admin is taking the kit offline on
    purpose; reflect that without flipping power back on
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select

from app.core.db import session_factory
from app.models import (
    AuditLog,
    Device,
    DevicePowerState,
    DeviceStatus,
)


PROBE_INTERVAL_SECONDS = 60
PROBE_TIMEOUT_SECONDS = 3


async def probe_tcp(host: str, port: int) -> bool:
    """Returns True if TCP connection to host:port succeeds within timeout."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except (asyncio.TimeoutError, OSError, ConnectionError):
        return False


async def probe_all_devices() -> tuple[int, int]:
    """Probe every device once. Returns (count_updated, count_total)."""
    now = datetime.now(timezone.utc)
    updated = 0
    async with session_factory()() as db:
        devices = (await db.execute(select(Device))).scalars().all()
        if not devices:
            return 0, 0

        # Probe in parallel — 9 kits × 3s timeout would be 27s sequential;
        # asyncio.gather collapses that to ~3s wall.
        results = await asyncio.gather(
            *(probe_tcp(str(d.internal_ip), d.ssh_port) for d in devices),
            return_exceptions=False,
        )

        for d, reachable in zip(devices, results):
            # Don't touch state that the admin is actively managing.
            if d.power_state == DevicePowerState.RESETTING:
                continue
            if d.status == DeviceStatus.MAINTENANCE:
                continue

            new_state = DevicePowerState.ON if reachable else DevicePowerState.OFF
            if d.power_state == new_state:
                continue

            prev = d.power_state.value
            d.power_state = new_state
            d.power_state_changed_at = now
            d.power_state_changed_by = None  # system-detected
            db.add(
                AuditLog(
                    actor_id=None,
                    action="device.power_state.probe",
                    target_type="device",
                    target_id=str(d.id),
                    details={
                        "device_name": d.name,
                        "from": prev,
                        "to": new_state.value,
                        "internal_ip": str(d.internal_ip),
                        "ssh_port": d.ssh_port,
                    },
                )
            )
            updated += 1

        if updated:
            await db.commit()
        return updated, len(devices)


async def periodic_probe() -> None:
    logger.info(
        "device prober starting (interval={}s, timeout={}s)",
        PROBE_INTERVAL_SECONDS,
        PROBE_TIMEOUT_SECONDS,
    )
    while True:
        try:
            updated, total = await probe_all_devices()
            if updated:
                logger.info("prober: updated power_state for {}/{} devices", updated, total)
        except asyncio.CancelledError:
            logger.info("device prober cancelled")
            return
        except Exception as e:
            logger.error("prober iteration failed: {}", e)
        await asyncio.sleep(PROBE_INTERVAL_SECONDS)
