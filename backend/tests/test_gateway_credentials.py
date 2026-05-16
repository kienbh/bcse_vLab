"""Tests for the gateway credential service — ADR-0013 / M5.8.

Each test owns a fresh booking + device fixture. We bypass the API layer to
exercise the service contract directly.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Booking,
    BookingGrantedVia,
    BookingStatus,
    Device,
    GatewayAuthLog,
    GatewaySession,
    User,
)
from app.services import gateway_credentials


PASSWORD_RE = re.compile(r"^[abcdefghkmnpqrstuvwxyz23456789]{4}-[abcdefghkmnpqrstuvwxyz23456789]{4}-[abcdefghkmnpqrstuvwxyz23456789]{4}$")


@pytest_asyncio.fixture
async def booking(
    db: AsyncSession,
    class_with_assignment,
    student: User,
    device: Device,
) -> Booking:
    cls, _enr, _cda = class_with_assignment
    now = datetime.now(timezone.utc)
    b = Booking(
        user_id=student.id,
        device_id=device.id,
        class_id=cls.id,
        granted_via=BookingGrantedVia.CLASS,
        start_time=now - timedelta(minutes=1),
        end_time=now + timedelta(hours=2),
        status=BookingStatus.SCHEDULED,
    )
    db.add(b)
    await db.commit()
    await db.refresh(b)
    return b


# ---------------------------------------------------------------------------
# 1. Password format
# ---------------------------------------------------------------------------
def test_generate_password_format():
    for _ in range(50):
        pw = gateway_credentials.generate_password()
        assert PASSWORD_RE.match(pw), f"bad password format: {pw}"
        # No ambiguous chars from the banned set
        assert not set(pw) & set("0o1lI"), pw


# ---------------------------------------------------------------------------
# 2. Issue mints a row with a bcrypt hash + returns plaintext once
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_issue_for_booking_creates_session(db, booking, device):
    result = await gateway_credentials.issue_for_booking(
        db, booking=booking, device=device
    )
    await db.commit()

    assert PASSWORD_RE.match(result.password)
    assert result.session.booking_id == booking.id
    assert result.session.expires_at == booking.end_time
    assert result.session.password_hash.startswith("$2b$")
    # plaintext NEVER stored
    assert result.password not in result.session.password_hash


# ---------------------------------------------------------------------------
# 3. Verify happy path — correct password returns ok + updates last_auth_at
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_verify_password_ok(db, booking, device):
    result = await gateway_credentials.issue_for_booking(
        db, booking=booking, device=device
    )
    await db.commit()
    plaintext = result.password
    session_id = result.session.id

    verify = await gateway_credentials.verify_password(
        db,
        attempted_password=plaintext,
        ssh_username="vlab",
        client_ip="10.0.0.5",
    )
    await db.commit()
    assert verify.outcome == "ok"
    assert verify.session is not None
    assert verify.session.id == session_id
    assert verify.session.last_auth_at is not None
    assert str(verify.session.client_ip) == "10.0.0.5"

    # audit row written
    logs = (
        await db.execute(
            select(GatewayAuthLog).where(GatewayAuthLog.session_id == session_id)
        )
    ).scalars().all()
    assert any(log.outcome == "ok" for log in logs)


# ---------------------------------------------------------------------------
# 4. Wrong password → outcome wrong_password + no session change
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_verify_password_wrong(db, booking, device):
    result = await gateway_credentials.issue_for_booking(
        db, booking=booking, device=device
    )
    await db.commit()
    verify = await gateway_credentials.verify_password(
        db,
        attempted_password="zzzz-zzzz-zzzz",
        ssh_username="vlab",
        client_ip="10.0.0.6",
    )
    await db.commit()
    assert verify.outcome == "wrong_password"
    assert verify.session is None

    # session row untouched
    sess = (
        await db.execute(
            select(GatewaySession).where(GatewaySession.id == result.session.id)
        )
    ).scalar_one()
    assert sess.last_auth_at is None


# ---------------------------------------------------------------------------
# 5. Expired booking → verify rejects even with correct password
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_verify_password_expired(db, booking, device):
    result = await gateway_credentials.issue_for_booking(
        db, booking=booking, device=device
    )
    await db.commit()
    # Fast-forward by mutating the row
    result.session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db.commit()

    verify = await gateway_credentials.verify_password(
        db,
        attempted_password=result.password,
        ssh_username="vlab",
        client_ip=None,
    )
    await db.commit()
    # Expired sessions are excluded from the candidate query before bcrypt —
    # so the outcome is `no_active_session`, not `expired`. This is fine:
    # the user sees a 401 either way, and the audit row tells us why.
    assert verify.outcome == "no_active_session"
    assert verify.session is None


# ---------------------------------------------------------------------------
# 6. Revoked → verify rejects
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_verify_password_revoked(db, booking, device):
    result = await gateway_credentials.issue_for_booking(
        db, booking=booking, device=device
    )
    await db.commit()
    await gateway_credentials.revoke(db, result.session, reason="test")
    await db.commit()

    verify = await gateway_credentials.verify_password(
        db,
        attempted_password=result.password,
        ssh_username="vlab",
        client_ip=None,
    )
    await db.commit()
    assert verify.outcome == "no_active_session"


# ---------------------------------------------------------------------------
# 7. Regenerate — same booking, new password, regenerate_count bumps, old pw dies
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_regenerate_rotates_password(db, booking, device):
    first = await gateway_credentials.issue_for_booking(
        db, booking=booking, device=device
    )
    await db.commit()
    old_password = first.password
    old_count = first.session.regenerate_count

    second = await gateway_credentials.issue_for_booking(
        db, booking=booking, device=device
    )
    await db.commit()

    # Same session row, rotated password
    assert second.session.id == first.session.id
    assert second.password != old_password
    assert second.session.regenerate_count == old_count + 1

    # Old password no longer verifies
    bad = await gateway_credentials.verify_password(
        db,
        attempted_password=old_password,
        ssh_username="vlab",
        client_ip=None,
    )
    await db.commit()
    assert bad.outcome == "wrong_password"

    # New password works
    good = await gateway_credentials.verify_password(
        db,
        attempted_password=second.password,
        ssh_username="vlab",
        client_ip=None,
    )
    await db.commit()
    assert good.outcome == "ok"


# ---------------------------------------------------------------------------
# 8. Username mismatch — verify must scope by ssh_username field
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_verify_username_scopes_lookup(db, booking, device):
    result = await gateway_credentials.issue_for_booking(
        db, booking=booking, device=device, ssh_username="vlab"
    )
    await db.commit()
    verify = await gateway_credentials.verify_password(
        db,
        attempted_password=result.password,
        ssh_username="root",  # wrong username — session is for vlab
        client_ip=None,
    )
    await db.commit()
    assert verify.outcome == "no_active_session"
