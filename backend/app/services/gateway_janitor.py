"""Gateway session janitor — ADR-0013 (M5.8).

Runs in-process inside the backend container as a long-lived asyncio task
(started by `lifespan`). Every 30 seconds it does two things:

  1. **5-minute warning** — find unrevoked sessions whose `expires_at` is
     within the next 5 minutes and that haven't been warned yet. Try to
     write a banner into the user's TTY on the jump host (best effort).

  2. **Expiry sweep** — find unrevoked sessions whose `expires_at` has
     passed. Mark them revoked. If `active_pid` is set, ask the jump host
     to kill it so the held-open SSH session is reaped within the next tick.

Replaces M5.7's `session_lifecycle.periodic_sweep` (which dealt with the
old ed25519 + dynamic-user flow). The legacy `Session` rows are left alone.
"""
from __future__ import annotations

import asyncio
import shlex
from datetime import datetime, timedelta, timezone

import asyncssh
from loguru import logger
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import session_factory
from app.models import (
    AuditLog,
    Booking,
    BookingStatus,
    GatewaySession,
)


SWEEP_INTERVAL_SECONDS = 30
WARNING_LEAD_TIME = timedelta(minutes=5)


def _banner_text(minutes_left: int) -> str:
    # \r before each line because the user's terminal may be in raw mode.
    # English ASCII keeps the banner portable across MobaXterm / PuTTY /
    # PowerShell regardless of their default codepage.
    unit = "minute" if minutes_left == 1 else "minutes"
    return (
        "\r\n\r\n"
        f"*** [VJU Lab Portal] Your SSH session will end in "
        f"{minutes_left} {unit}. Please save your work. ***"
        "\r\n\r\n"
    )


async def _ssh_run_on_jump(cmd: str) -> bool:
    """Best-effort one-shot SSH to the jump host as the backend admin user."""
    settings = get_settings()
    import os

    if not os.path.exists(settings.BACKEND_SSH_KEY_PATH):
        logger.debug("janitor: backend admin key missing, skipping {}", cmd)
        return False
    try:
        async with asyncssh.connect(
            settings.SV14_HOST,
            port=settings.SV14_SSH_PORT,
            username=settings.SV14_SSH_USER,
            client_keys=[settings.BACKEND_SSH_KEY_PATH],
            known_hosts=None,
        ) as conn:
            r = await conn.run(cmd, check=False)
            return r.exit_status == 0
    except (asyncssh.Error, OSError) as e:
        logger.warning("janitor: ssh to jump host failed: {}", e)
        return False


async def _write_banner(session: GatewaySession, minutes_left: int) -> bool:
    # Only attempt when pty_path looks like a real device path. Older rows
    # (and MobaXterm sessions that don't request a pty) stored the literal
    # string "not a tty" — guard against shell-injecting that into the cmd.
    pty = session.pty_path or ""
    if not pty.startswith("/dev/"):
        return False
    safe_pty = shlex.quote(pty)
    safe_msg = shlex.quote(_banner_text(minutes_left))
    cmd = f"test -w {safe_pty} && printf %s {safe_msg} > {safe_pty}"
    return await _ssh_run_on_jump(cmd)


async def _kill_pid(session: GatewaySession) -> bool:
    """Drop the live SSH connection on the jump host.

    Preferred path: `active_pid` was recorded by session-start → kill that
    specific PID with SIGHUP then SIGKILL backstop.

    Fallback (active_pid NULL — session-start curl failed / timed out): use
    pkill -u vlab to reap any ssh-to-this-kit process the vlab user owns.
    This is a wider net but vlab can only own ssh processes spawned by
    ForceCommand, so blast radius is bounded.
    """
    if session.active_pid:
        pid = int(session.active_pid)
        cmd = f"kill -HUP {pid} 2>/dev/null; sleep 1; kill -KILL {pid} 2>/dev/null; true"
    else:
        # `session.target_host` is an INET column → str() includes "/32" which
        # never appears in the ssh process cmdline (gateway_credentials writes
        # bare IP). Strip it here so the pkill pattern still matches.
        target = shlex.quote(str(session.target_host).split("/", 1)[0])
        # pkill -f matches the full command line of /usr/bin/ssh, which contains
        # the kit IP as the last positional arg.
        cmd = (
            f"pkill -HUP -u vlab -f {target} 2>/dev/null; "
            f"sleep 1; "
            f"pkill -KILL -u vlab -f {target} 2>/dev/null; "
            f"true"
        )
    return await _ssh_run_on_jump(cmd)


async def _warn_expiring(db, now: datetime) -> int:
    """Send banner for sessions in the warning window. Returns count warned."""
    horizon = now + WARNING_LEAD_TIME
    rows = (
        await db.execute(
            select(GatewaySession).where(
                GatewaySession.revoked_at.is_(None),
                GatewaySession.warning_sent_at.is_(None),
                GatewaySession.expires_at > now,
                GatewaySession.expires_at <= horizon,
            )
        )
    ).scalars().all()

    count = 0
    for sess in rows:
        minutes_left = max(1, int((sess.expires_at - now).total_seconds() // 60))
        sent = await _write_banner(sess, minutes_left)
        # Mark sent regardless — we don't want to spam the same TTY every 30s
        # if the write keeps failing because the pty path is wrong.
        sess.warning_sent_at = now
        if sent:
            count += 1
            logger.info(
                "janitor: warned session {} ({} min left)", sess.id, minutes_left
            )
    return count


async def _reap_expired(db, now: datetime) -> int:
    """Revoke + kill expired or cancelled-booking sessions. Returns count."""
    rows = (
        await db.execute(
            select(GatewaySession, Booking)
            .join(Booking, Booking.id == GatewaySession.booking_id)
            .where(
                GatewaySession.revoked_at.is_(None),
                (
                    (GatewaySession.expires_at <= now)
                    | (Booking.status == BookingStatus.CANCELLED)
                ),
            )
        )
    ).all()
    count = 0
    for sess, booking in rows:
        reason = (
            "slot_expired"
            if sess.expires_at <= now
            else f"booking_status:{booking.status.value}"
        )
        sess.revoked_at = now
        sess.revoked_reason = reason[:64]

        if sess.active_pid:
            try:
                await _kill_pid(sess)
            except Exception as e:
                logger.warning(
                    "janitor: failed to kill pid {} for session {}: {}",
                    sess.active_pid,
                    sess.id,
                    e,
                )

        if booking.status == BookingStatus.ACTIVE:
            booking.status = BookingStatus.COMPLETED

        db.add(
            AuditLog(
                actor_id=None,
                action="gateway.session.auto_revoke",
                target_type="gateway_session",
                target_id=str(sess.id),
                details={
                    "booking_id": str(booking.id),
                    "reason": reason,
                    "killed_pid": sess.active_pid,
                },
            )
        )
        count += 1
    return count


async def revoke_expired_sessions() -> tuple[int, int]:
    """One pass — returns (warned_count, revoked_count)."""
    async with session_factory()() as db:
        now = datetime.now(timezone.utc)
        warned = await _warn_expiring(db, now)
        revoked = await _reap_expired(db, now)
        if warned or revoked:
            await db.commit()
    return warned, revoked


async def periodic_sweep() -> None:
    """Long-lived background task — runs forever every SWEEP_INTERVAL_SECONDS."""
    logger.info(
        "gateway janitor starting (interval={}s, warning_lead={}m)",
        SWEEP_INTERVAL_SECONDS,
        int(WARNING_LEAD_TIME.total_seconds() // 60),
    )
    while True:
        try:
            warned, revoked = await revoke_expired_sessions()
            if warned or revoked:
                logger.info(
                    "janitor: warned={} revoked={}", warned, revoked
                )
        except asyncio.CancelledError:
            logger.info("gateway janitor cancelled")
            return
        except Exception as e:
            logger.error("janitor iteration failed: {}", e)
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
