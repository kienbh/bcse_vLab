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

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import bcrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Booking, Device, GatewayAuthLog, GatewaySession


PASSWORD_ALPHABET = "abcdefghkmnpqrstuvwxyz23456789"
PASSWORD_LENGTH = 12


def generate_password() -> str:
    """Sinh password 12 ký tự liền — unambiguous alphabet (bỏ 0/o/1/l/i/j).

    Không dùng dấu phân cách (em-dash hazard khi paste qua một số terminal /
    rich-text clipboard). 12 chars * log2(30) ≈ 59 bits — đủ cho session ≤ 8h.
    """
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(PASSWORD_LENGTH))


def _hash(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def _check(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


# AES-256-GCM encryption for the persisted plaintext password. We derive the
# 32-byte key from DEVICE_KEY_ENCRYPTION_KEY via SHA-256 so any 32+ char value
# the operator pins is acceptable (no strict-length headache for ops).
def _aes_key() -> bytes:
    raw = get_settings().DEVICE_KEY_ENCRYPTION_KEY.get_secret_value().encode("utf-8")
    return hashlib.sha256(raw).digest()


def _encrypt_password(plain: str) -> bytes:
    """Returns `nonce(12) || ciphertext || tag(16)`."""
    nonce = secrets.token_bytes(12)
    ct = AESGCM(_aes_key()).encrypt(nonce, plain.encode("utf-8"), None)
    return nonce + ct


def _decrypt_password(blob: bytes) -> str | None:
    if not blob or len(blob) < 12 + 16:
        return None
    try:
        nonce, ct = blob[:12], blob[12:]
        return AESGCM(_aes_key()).decrypt(nonce, ct, None).decode("utf-8")
    except Exception:
        return None


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
    force_rotate: bool = False,
) -> IssueResult:
    """Mint (or return) the gateway session for `booking`.

    Per thầy's M5.8 requirement: one password per slot. Behaviour:
      - First call → mint, encrypt-at-rest, return plaintext.
      - Subsequent calls on the same booking, while the session is unrevoked
        and within its expires_at → return the SAME password (decrypted from
        ciphertext). No rotation, no audit churn.
      - Subsequent calls on a revoked/expired session, OR `force_rotate=True`
        → mint a new password, bump regenerate_count, clear revoked_at.

    The caller owns the access-control + booking-state check (e.g. booking
    belongs to user, booking window is open). This service trusts what it's
    handed.
    """
    existing = await _existing_session(db, booking.id)
    now = datetime.now(timezone.utc)

    if (
        existing is not None
        and not force_rotate
        and existing.revoked_at is None
        and existing.expires_at > now
        and existing.password_ciphertext is not None
    ):
        plaintext = _decrypt_password(existing.password_ciphertext)
        if plaintext is not None:
            # idempotent refresh of routing info (kit IP/user might have
            # been edited by admin since the session was minted) but NOT
            # the password — it stays constant for the whole slot.
            existing.target_host = str(device.internal_ip)
            existing.target_port = device.ssh_port
            existing.target_user = device.ssh_user
            existing.ssh_username = ssh_username
            await db.flush()
            return IssueResult(password=plaintext, session=existing)

    plaintext = generate_password()
    pw_hash = _hash(plaintext)
    pw_blob = _encrypt_password(plaintext)

    if existing is not None:
        existing.password_hash = pw_hash
        existing.password_ciphertext = pw_blob
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
        password_ciphertext=pw_blob,
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
