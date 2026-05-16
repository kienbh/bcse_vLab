"""Periodic sweeper — revoke ephemeral SSH keys when bookings expire.

Runs in-process inside the backend container as a long-lived asyncio task
(started by `lifespan`). Every 30 seconds it scans for active sessions
whose booking.end_time is in the past and:
  1. SSHes to the device with the backend admin key
  2. Strips the session-tagged line from ~/.ssh/authorized_keys
  3. Marks the session COMPLETED + booking COMPLETED
  4. Writes an audit_log row

This is the "gateway blocks the connection after the slot ends" enforcement
that thầy required 2026-05-16. Without this, an SSH session held open by
the user persists past the booking window because OpenSSH doesn't re-auth
mid-connection — but stripping the pubkey ensures the *next* connection
attempt fails, and combined with TCP keepalive timeouts on long-idle
sockets, even active sessions get reaped within a few minutes.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import session_factory
from app.models import (
    AuditLog,
    Booking,
    BookingStatus,
    Device,
    Session as DBSession,
    SessionStatus,
)
from app.services import ssh_manager


SWEEP_INTERVAL_SECONDS = 30


async def revoke_expired_sessions() -> int:
    """Returns the count of sessions revoked in this pass."""
    settings = get_settings()
    revoked_count = 0
    async with session_factory()() as db:
        now = datetime.now(timezone.utc)
        # Find active sessions whose booking has ended (or been cancelled)
        result = await db.execute(
            select(DBSession, Booking, Device)
            .join(Booking, Booking.id == DBSession.booking_id)
            .join(Device, Device.id == Booking.device_id)
            .where(
                DBSession.status == SessionStatus.ACTIVE,
                # end_time passed OR booking cancelled (kicked by admin via cancel)
                (
                    (Booking.end_time <= now)
                    | (Booking.status == BookingStatus.CANCELLED)
                ),
            )
        )
        rows = list(result.all())
        if not rows:
            return 0

        for sess, booking, device in rows:
            # Extract the session tag embedded in the pubkey comment
            old_tag = ""
            if sess.ssh_pubkey and "session=" in sess.ssh_pubkey:
                old_tag = sess.ssh_pubkey.split("session=")[-1].split(" ")[0]

            if old_tag:
                try:
                    await ssh_manager.revoke_session(
                        device_internal_ip=str(device.internal_ip),
                        device_ssh_port=device.ssh_port,
                        device_ssh_user=device.ssh_user,
                        backend_admin_key_path=settings.BACKEND_SSH_KEY_PATH,
                        session_tag=old_tag,
                    )
                except Exception as e:
                    logger.warning(
                        f"sweep: revoke ssh on {device.name} failed (will mark "
                        f"session ended anyway): {e}"
                    )

            sess.status = SessionStatus.COMPLETED
            sess.ended_at = now
            if booking.status == BookingStatus.ACTIVE:
                booking.status = BookingStatus.COMPLETED
            db.add(
                AuditLog(
                    actor_id=None,
                    action="session.auto_revoke",
                    target_type="session",
                    target_id=str(sess.id),
                    details={
                        "booking_id": str(booking.id),
                        "device_name": device.name,
                        "reason": "slot_expired_or_cancelled",
                        "session_tag": old_tag,
                    },
                )
            )
            revoked_count += 1

        await db.commit()
    return revoked_count


async def periodic_sweep() -> None:
    """Long-lived background task — runs forever every SWEEP_INTERVAL_SECONDS."""
    logger.info(
        f"session lifecycle sweeper starting (interval={SWEEP_INTERVAL_SECONDS}s)"
    )
    while True:
        try:
            count = await revoke_expired_sessions()
            if count:
                logger.info(f"sweep: revoked {count} expired session(s)")
        except asyncio.CancelledError:
            logger.info("session lifecycle sweeper cancelled")
            return
        except Exception as e:
            logger.error(f"sweep iteration failed: {e}")
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
