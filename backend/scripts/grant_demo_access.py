"""Pilot demo helper — grant 30-day special_access to a user on the 3 lab KITs.

Used during M5.5-M5.6 pilot when the admin UI doesn't yet expose a SpecialAccess
form. Cleaner alternative to raw SQL inserts because it goes through the same
ORM models + validation as the real API.

Usage (inside backend container):
    docker exec vju-lab-portal-backend-1 \\
        python -m scripts.grant_demo_access <email>

Or with a custom device-name list:
    docker exec vju-lab-portal-backend-1 \\
        python -m scripts.grant_demo_access <email> kv260-lab01 kv260-lab02

Idempotent — re-runs skip existing active special_access for the same user/device.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.db import async_session_maker
from app.models import Device, SpecialAccess, User


DEFAULT_DEVICE_NAMES = ["kv260-lab01", "kv260-lab02", "kv260-lab03"]
DEMO_VALIDITY_DAYS = 30
DEMO_WEEKLY_HOURS_LIMIT = 40
DEMO_MAX_CONCURRENT = 2
DEMO_REASON = "Pilot demo — admin test access (M5.5-M5.6)"


async def grant(email: str, device_names: list[str]) -> int:
    """Returns number of newly-created special_access rows."""
    created = 0
    async with async_session_maker() as db:
        user = (
            await db.execute(select(User).where(User.email == email.lower()))
        ).scalar_one_or_none()
        if user is None:
            print(f"[grant_demo] user not found: {email}")
            return 0

        now = datetime.now(timezone.utc) - timedelta(hours=1)  # back-date slightly
        until = now + timedelta(days=DEMO_VALIDITY_DAYS + 1)

        for name in device_names:
            device = (
                await db.execute(select(Device).where(Device.name == name))
            ).scalar_one_or_none()
            if device is None:
                print(f"[grant_demo] device not found: {name}")
                continue

            existing = (
                await db.execute(
                    select(SpecialAccess).where(
                        SpecialAccess.user_id == user.id,
                        SpecialAccess.device_id == device.id,
                        SpecialAccess.revoked_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                print(f"[grant_demo] already has active grant on {name} — skip")
                continue

            sa = SpecialAccess(
                user_id=user.id,
                device_id=device.id,
                valid_from=now,
                valid_to=until,
                allowed_time_windows=[],
                weekly_hours_limit=DEMO_WEEKLY_HOURS_LIMIT,
                max_concurrent_bookings=DEMO_MAX_CONCURRENT,
                reason=DEMO_REASON,
                granted_by=user.id,
            )
            db.add(sa)
            try:
                await db.flush()
                created += 1
                print(f"[grant_demo] granted {email} → {name} until {until.date()}")
            except IntegrityError as e:
                await db.rollback()
                print(f"[grant_demo] IntegrityError on {name}: {e.orig}")

        await db.commit()
    return created


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.grant_demo_access <email> [device_name ...]")
        return 1
    email = sys.argv[1].strip().lower()
    device_names = sys.argv[2:] if len(sys.argv) > 2 else DEFAULT_DEVICE_NAMES
    created = asyncio.run(grant(email, device_names))
    print(f"[grant_demo] DONE — created {created} new grant(s) for {email}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
