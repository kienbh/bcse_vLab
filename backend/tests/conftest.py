"""Pytest fixtures — shared DB session + factory helpers."""
from __future__ import annotations

import os
import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

# Test-only env defaults — set BEFORE settings cache initialises.
os.environ.setdefault("ENV", "development")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://labportal:test@localhost:5432/labportal_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault(
    "JWT_SECRET_KEY",
    "test_only_jwt_secret_with_more_than_64_characters_to_pass_validation_xx",
)

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import (
    Base,
    Class,
    ClassDeviceAssignment,
    Device,
    DeviceStatus,
    DeviceType,
    Enrollment,
    SpecialAccess,
    User,
    UserRole,
)
from app.models.quota import UserQuota


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def _engine():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.execute(__import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\""))
        await conn.execute(__import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        # GIST EXCLUDE — recreate manually since SQLAlchemy doesn't model EXCLUDE.
        # The `AND NOT shared_resource` clause matches migration 0010 — VPS
        # bookings (shared_resource=true) bypass the no-overlap rule.
        await conn.execute(__import__("sqlalchemy").text(
            """
            ALTER TABLE bookings ADD CONSTRAINT no_overlap EXCLUDE USING gist (
                device_id WITH =,
                tstzrange(start_time, end_time, '[)') WITH &&
            ) WHERE (status IN ('scheduled','active') AND NOT shared_resource)
            """
        ))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db(_engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()
        # Per-test cleanup — TRUNCATE all data tables (keeps schema)
        from sqlalchemy import text
        async with _engine.begin() as conn:
            await conn.execute(text(
                "TRUNCATE access_requests, gateway_auth_log, gateway_sessions, "
                "bookings, sessions, special_access, class_device_assignments, "
                "enrollments, classes, plug_mappings, device_credentials, devices, "
                "user_quotas, audit_logs, users RESTART IDENTITY CASCADE"
            ))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def admin(db: AsyncSession) -> User:
    u = User(
        email=f"admin-{uuid4().hex[:6]}@vju.ac.vn",
        full_name="Admin",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(u)
    await db.flush()
    db.add(UserQuota(user_id=u.id))
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def lecturer(db: AsyncSession) -> User:
    u = User(
        email=f"lec-{uuid4().hex[:6]}@vju.ac.vn",
        full_name="Lecturer",
        role=UserRole.LECTURER,
        is_active=True,
    )
    db.add(u)
    await db.flush()
    db.add(UserQuota(user_id=u.id))
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def student(db: AsyncSession) -> User:
    u = User(
        email=f"sv-{uuid4().hex[:6]}@st.vju.ac.vn",
        full_name="Student",
        role=UserRole.STUDENT,
        is_active=True,
    )
    db.add(u)
    await db.flush()
    db.add(UserQuota(user_id=u.id))
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def device(db: AsyncSession) -> Device:
    d = Device(
        name=f"kv260-{uuid4().hex[:4]}",
        device_type=DeviceType.FPGA_KV260,
        model="Kria KV260",
        internal_ip=f"192.168.20.{50 + (uuid4().int % 50)}",
        ssh_port=22,
        ssh_user="student",
        status=DeviceStatus.AVAILABLE,
    )
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return d


@pytest_asyncio.fixture
async def class_with_assignment(
    db: AsyncSession, lecturer: User, student: User, device: Device
) -> tuple[Class, Enrollment, ClassDeviceAssignment]:
    """Create a class, enroll the student, and assign the device. 24/7 + 5h/week + 1 concurrent."""
    cls = Class(
        code=f"TEST-{uuid4().hex[:4]}",
        name="Test class",
        semester="2026-1",
        lecturer_id=lecturer.id,
        starts_at=_utcnow() - timedelta(days=1),
        ends_at=_utcnow() + timedelta(days=120),
    )
    db.add(cls)
    await db.flush()
    enr = Enrollment(class_id=cls.id, user_id=student.id, enrolled_by=lecturer.id)
    db.add(enr)
    cda = ClassDeviceAssignment(
        class_id=cls.id,
        device_id=device.id,
        valid_from=_utcnow() - timedelta(days=1),
        valid_to=_utcnow() + timedelta(days=120),
        allowed_time_windows=[],  # 24/7
        per_student_weekly_hours=5,
        per_student_max_concurrent=1,
        per_student_max_advance_days=7,
        granted_by=lecturer.id,
    )
    db.add(cda)
    await db.commit()
    await db.refresh(cls)
    await db.refresh(enr)
    await db.refresh(cda)
    return cls, enr, cda
