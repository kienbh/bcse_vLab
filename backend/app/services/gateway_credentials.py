"""Gateway credential service — ADR-0013 (M5.8).

Mints, verifies, and revokes per-booking SSH passwords. The password is
ever-only returned to the booking owner exactly once (on `/access` POST).
The hash sits in `gateway_sessions.password_hash`; PAM on the jump host
POSTs `/api/gateway/auth`, which calls `verify_password` here.

Password format: 12 chars in 3 dash-separated groups of 4, drawn from an
unambiguous alphabet (`abcdefghkmnpqrstuvwxyz23456789` — no 0/o/1/l/i).
That's ~62 bits of entropy, plenty for short-lived (≤8h) credentials.

Performance note: linear bcrypt scan is fine for the pilot (<100 active
sessions). If it ever exceeds that, switch to a prefix lookup column
(first 4 chars of plaintext stored alongside the hash) to narrow before
the bcrypt walk.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, Device, GatewayAuthLog, GatewaySession


PASSWORD_ALPHABET = "abcdefghkmnpqrstuvwxyz23456789"
PASSWORD_GROUP_LEN = 4
PASSWORD_GROUPS = 3


def generate_password() -> str:
    """Sinh password 12 ký tự dạng xxxx-xxxx-xxxx — unambiguous alphabet."""
    groups = [
        "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(PASSWORD_GROUP_LEN))
        for _ in range(PASSWORD_GROUPS)
    ]
    return "-".join(groups)


def _hash(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def _check(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


@dataclass(slots=True)
class IssueResult:
    """Return tuple from `issue_for_booking`. `password` is only ever live in this object."""

    password: str
    session: GatewaySession


@dataclass(slots=True)
class VerifyResult:
    session: GatewaySession | None
    outcome: str  # ok | wrong_password | expired | revoked | no_active_session
    reason: str | None = None


async def _existing_session(db: AsyncSession, booking_id: UUID) -> GatewaySession | None:
    row = await db.execute(
        select(GatewaySession).where(GatewaySession.booking_id == booking_id)
    )
    return row.scalar_one_or_none()


async def issue_for_booking(
    db: AsyncSession,
    *,
    booking: Booking,
    device: Device,
    ssh_username: str = "vlab",
) -> IssueResult:
    """Mint or rotate the gateway session for `booking`.

    - If a session already exists, the row is reused: password rotated,
      revoked_at cleared, regenerate_count bumped. This is what
      `/access/regenerate` calls.
    - Otherwise a fresh row is inserted.

    The caller is responsible for any access-control + booking-state check
    (e.g. booking belongs to user, booking window is open). This service
    trusts what it's handed.
    """
    plaintext = generate_password()
    pw_hash = _hash(plaintext)

    existing = await _existing_session(db, booking.id)
    if existing is not None:
        existing.password_hash = pw_hash
        existing.expires_at = booking.end_time
        existing.revoked_at = None
        existing.revoked_reason = None
        existing.warning_sent_at = None
        existing.regenerate_count = (existing.regenerate_count or 0) + 1
        existing.target_host = str(device.internal_ip)
        existing.target_port = device.ssh_port
        existing.target_user = device.ssh_user
        existing.ssh_username = ssh_username
        await db.flush()
        return IssueResult(password=plaintext, session=existing)

    session = GatewaySession(
        booking_id=booking.id,
        user_id=booking.user_id,
        device_id=booking.device_id,
        ssh_username=ssh_username,
        password_hash=pw_hash,
        expires_at=booking.end_time,
        target_host=str(device.internal_ip),
        target_port=device.ssh_port,
        target_user=device.ssh_user,
    )
    db.add(session)
    await db.flush()
    return IssueResult(password=plaintext, session=session)


async def revoke(
    db: AsyncSession,
    session: GatewaySession,
    *,
    reason: str,
) -> None:
    """Mark the session revoked. Idempotent — second call is a no-op."""
    if session.revoked_at is not None:
        return
    session.revoked_at = datetime.now(timezone.utc)
    session.revoked_reason = reason[:64]
    await db.flush()


async def verify_password(
    db: AsyncSession,
    *,
    attempted_password: str,
    ssh_username: str,
    client_ip: str | None,
) -> VerifyResult:
    """Find the active GatewaySession whose password matches.

    Called by `/api/gateway/auth` (PAM on jump host). The username check is
    coarse — PAM passes whatever the user typed at `ssh -J`. We accept any
    username matching `gateway_sessions.ssh_username` (default `vlab`); the
    target host is decided by which session matched, not by username.
    """
    now = datetime.now(timezone.utc)
    q = select(GatewaySession).where(
        GatewaySession.revoked_at.is_(None),
        GatewaySession.expires_at > now,
        GatewaySession.ssh_username == ssh_username,
    )
    rows = (await db.execute(q)).scalars().all()

    if not rows:
        await _log(
            db,
            session_id=None,
            booking_id=None,
            user_id=None,
            client_ip=client_ip,
            ssh_username=ssh_username,
            outcome="no_active_session",
            reason=None,
        )
        return VerifyResult(session=None, outcome="no_active_session")

    for sess in rows:
        if _check(attempted_password, sess.password_hash):
            sess.last_auth_at = now
            sess.client_ip = client_ip
            await _log(
                db,
                session_id=sess.id,
                booking_id=sess.booking_id,
                user_id=sess.user_id,
                client_ip=client_ip,
                ssh_username=ssh_username,
                outcome="ok",
                reason=None,
            )
            return VerifyResult(session=sess, outcome="ok")

    await _log(
        db,
        session_id=None,
        booking_id=None,
        user_id=None,
        client_ip=client_ip,
        ssh_username=ssh_username,
        outcome="wrong_password",
        reason=None,
    )
    return VerifyResult(session=None, outcome="wrong_password")


async def _log(
    db: AsyncSession,
    *,
    session_id: UUID | None,
    booking_id: UUID | None,
    user_id: UUID | None,
    client_ip: str | None,
    ssh_username: str | None,
    outcome: str,
    reason: str | None,
) -> None:
    db.add(
        GatewayAuthLog(
            session_id=session_id,
            booking_id=booking_id,
            user_id=user_id,
            client_ip=client_ip,
            ssh_username=ssh_username,
            outcome=outcome,
            reason=reason,
        )
    )


async def log_attempt(
    db: AsyncSession,
    *,
    client_ip: str | None,
    ssh_username: str | None,
    outcome: str,
    reason: str | None = None,
) -> None:
    """Public wrapper for callers that need to log without going through verify
    (e.g. shared-secret mismatch from PAM before we even consult the DB)."""
    await _log(
        db,
        session_id=None,
        booking_id=None,
        user_id=None,
        client_ip=client_ip,
        ssh_username=ssh_username,
        outcome=outcome,
        reason=reason,
    )
