"""Seed VJU Lab Portal — local-password whitelist (no OIDC).

Pre-creates admin + lecturers + students with default password VJU@2026.
All seeded accounts have must_change_password=True so first login forces change.

Run inside backend container:
    docker exec vju-lab-portal-backend-1 python /app/seed.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.db import session_factory
from app.models import (
    Class,
    ClassDeviceAssignment,
    Device,
    DeviceStatus,
    DeviceType,
    Enrollment,
    PlugMapping,
    PlugType,
    User,
    UserRole,
)
from app.models.quota import UserQuota
from app.services.auth import DEFAULT_PASSWORD, hash_password

# Primary admin password — đọc từ env ADMIN_BH_KIEN_PASSWORD nếu có (không leak vào git).
# Nếu env không set → account vẫn được tạo nhưng dùng DEFAULT_PASSWORD và bị ép
# đổi mật khẩu khi đăng nhập lần đầu.
ADMIN_BH_KIEN_PASSWORD = os.environ.get("ADMIN_BH_KIEN_PASSWORD")

# ----- Whitelist -------------------------------------------------------------
# Tuple: (email, full_name, role, student_code|None, password_override|None, force_change|None)
#   - password_override = None ⇒ use DEFAULT_PASSWORD ("VJU@2026")
#   - force_change      = None ⇒ True if password_override is None, else False
# Edit this list as cohort changes.

WHITELIST: list[
    tuple[str, str, UserRole, str | None, str | None, bool | None]
] = [
    # Primary admin — thầy Kiên. Set ADMIN_BH_KIEN_PASSWORD env trước khi seed.
    (
        "bh.kien@vju.ac.vn", "Bùi Huy Kiên", UserRole.ADMIN, None,
        ADMIN_BH_KIEN_PASSWORD, False if ADMIN_BH_KIEN_PASSWORD else None,
    ),

    # Backup admin (default password, must change on first login)
    ("admin@vju.ac.vn", "Lab Admin", UserRole.ADMIN, None, None, None),

    # Lecturers
    ("hung.le@vju.ac.vn", "Lê Việt Hưng", UserRole.LECTURER, None, None, None),
    ("anh.nguyen@vju.ac.vn", "Nguyễn Tuấn Anh", UserRole.LECTURER, None, None, None),

    # Pilot students (BCSE 2024 cohort)
    ("sv01@st.vju.ac.vn", "Sinh viên 01", UserRole.STUDENT, "BCSE2024001", None, None),
    ("sv02@st.vju.ac.vn", "Sinh viên 02", UserRole.STUDENT, "BCSE2024002", None, None),
    ("sv03@st.vju.ac.vn", "Sinh viên 03", UserRole.STUDENT, "BCSE2024003", None, None),
    ("sv04@st.vju.ac.vn", "Sinh viên 04", UserRole.STUDENT, "BCSE2024004", None, None),
    ("sv05@st.vju.ac.vn", "Sinh viên 05", UserRole.STUDENT, "BCSE2024005", None, None),
    ("sv06@st.vju.ac.vn", "Sinh viên 06", UserRole.STUDENT, "BCSE2024006", None, None),
    ("sv07@st.vju.ac.vn", "Sinh viên 07", UserRole.STUDENT, "BCSE2024007", None, None),
    ("sv08@st.vju.ac.vn", "Sinh viên 08", UserRole.STUDENT, "BCSE2024008", None, None),
    ("sv09@st.vju.ac.vn", "Sinh viên 09", UserRole.STUDENT, "BCSE2024009", None, None),
    ("sv10@st.vju.ac.vn", "Sinh viên 10", UserRole.STUDENT, "BCSE2024010", None, None),
]


async def upsert_user(
    db,
    *,
    email: str,
    full_name: str,
    role: UserRole,
    code: str | None,
    password_override: str | None = None,
    force_change: bool | None = None,
) -> User:
    """Idempotent user upsert.

    - On insert: set password (override or default), set must_change_password.
    - On existing: only fill `password_hash` if currently NULL; never overwrite a
      password the user has already changed via /change-password.
    """
    initial = password_override or DEFAULT_PASSWORD
    must_change = force_change if force_change is not None else (password_override is None)
    pw_label = "(custom)" if password_override else "(default)"

    res = await db.execute(select(User).where(User.email == email))
    u = res.scalar_one_or_none()
    if u is None:
        u = User(
            email=email,
            full_name=full_name,
            role=role,
            student_code=code,
            password_hash=hash_password(initial),
            must_change_password=must_change,
            is_active=True,
        )
        db.add(u)
        await db.flush()
        db.add(UserQuota(user_id=u.id))
        print(f"  + {role.value:8s} {email:32s} {pw_label}")
    else:
        if u.password_hash is None:
            u.password_hash = hash_password(initial)
            u.must_change_password = must_change
            print(f"  ↻ {role.value:8s} {email:32s} {pw_label} (was missing)")
        else:
            print(f"  = {role.value:8s} {email:32s} (kept existing)")
    return u


async def upsert_device(
    db,
    *,
    name: str,
    device_type: DeviceType,
    model: str,
    internal_ip: str,
    plug_ip: str | None = None,
    capabilities: dict | None = None,
    ssh_user: str = "student",
    ssh_port: int = 22,
) -> Device:
    res = await db.execute(select(Device).where(Device.name == name))
    d = res.scalar_one_or_none()
    if d is None:
        d = Device(
            name=name,
            device_type=device_type,
            model=model,
            internal_ip=internal_ip,
            ssh_port=ssh_port,
            ssh_user=ssh_user,
            status=DeviceStatus.AVAILABLE,
            capabilities=capabilities or {},
        )
        db.add(d)
        await db.flush()
        if plug_ip:
            db.add(
                PlugMapping(
                    device_id=d.id,
                    plug_ip=plug_ip,
                    plug_type=PlugType.TASMOTA,
                    plug_relay_index=1,
                )
            )
        print(f"  + device {name:18s} {model} ({internal_ip}, ssh:{ssh_user})")
    else:
        print(f"  = device {name:18s}")
    return d


async def upsert_class(
    db,
    *,
    code: str,
    name: str,
    semester: str,
    lecturer_id,
) -> Class:
    res = await db.execute(select(Class).where(Class.code == code))
    c = res.scalar_one_or_none()
    if c is None:
        now = datetime.now(timezone.utc)
        c = Class(
            code=code,
            name=name,
            semester=semester,
            lecturer_id=lecturer_id,
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=180),
            is_active=True,
        )
        db.add(c)
        await db.flush()
        print(f"  + class  {code:18s} {name}")
    else:
        print(f"  = class  {code:18s}")
    return c


async def upsert_enrollment(db, *, class_id, user_id, enrolled_by) -> None:
    res = await db.execute(
        select(Enrollment).where(
            Enrollment.class_id == class_id, Enrollment.user_id == user_id
        )
    )
    e = res.scalar_one_or_none()
    if e is None:
        db.add(
            Enrollment(
                class_id=class_id, user_id=user_id, enrolled_by=enrolled_by, is_active=True
            )
        )


async def upsert_assignment(
    db,
    *,
    class_id,
    device_id,
    granted_by,
    weekly_hours: int = 20,
    max_concurrent: int = 1,
    advance_days: int = 14,
) -> ClassDeviceAssignment:
    res = await db.execute(
        select(ClassDeviceAssignment).where(
            ClassDeviceAssignment.class_id == class_id,
            ClassDeviceAssignment.device_id == device_id,
            ClassDeviceAssignment.revoked_at.is_(None),
        )
    )
    a = res.scalar_one_or_none()
    if a is None:
        now = datetime.now(timezone.utc)
        a = ClassDeviceAssignment(
            class_id=class_id,
            device_id=device_id,
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=180),
            allowed_time_windows=[],  # empty = 24/7 (demo-friendly)
            per_student_weekly_hours=weekly_hours,
            per_student_max_concurrent=max_concurrent,
            per_student_max_advance_days=advance_days,
            granted_by=granted_by,
        )
        db.add(a)
        await db.flush()
        print(f"  + assign device → class (24/7, {weekly_hours}h/week)")
    else:
        print("  = assign already exists")
    return a


async def main() -> int:
    factory = session_factory()
    async with factory() as db:
        print(f"=== Whitelist users (default password: {DEFAULT_PASSWORD}) ===")
        users_by_email: dict[str, User] = {}
        for email, full_name, role, code, pw, force in WHITELIST:
            u = await upsert_user(
                db,
                email=email,
                full_name=full_name,
                role=role,
                code=code,
                password_override=pw,
                force_change=force,
            )
            users_by_email[email] = u

        # Make sure all users have an ID after flush
        await db.flush()

        print("\n=== Real lab devices (same-LAN, 192.168.2.x — directly reachable from SV14) ===")
        # Convention: FPGA 00X ↔ user ubuntu00X. IPs are the router's DHCP
        # leases (kept as-is — the sequential .141-.145 plan was dropped after
        # a static-IP migration caused conflicts; see bcse-vlab-fleet-naming).
        _kv260_capabilities = {
            "vivado": True,
            "vitis": True,
            "xmutil": True,
            "k26_starter_kits": True,
        }
        kv260_real = await upsert_device(
            db,
            name="fpga-kv260-001",
            device_type=DeviceType.FPGA_KV260,
            model="AMD Kria KV260 (lab unit, revB)",
            internal_ip="192.168.2.93",
            ssh_user="ubuntu001",
            capabilities=_kv260_capabilities,
        )
        kv260_real2 = await upsert_device(
            db,
            name="fpga-kv260-002",
            device_type=DeviceType.FPGA_KV260,
            model="AMD Kria KV260 (lab unit, revB)",
            internal_ip="192.168.2.100",
            ssh_user="ubuntu002",
            capabilities=_kv260_capabilities,
        )
        # fpga-kv260-003 stays on .121 (router-assigned) — .143 had a
        # persistent IP conflict with another lab machine.
        kv260_real3 = await upsert_device(
            db,
            name="fpga-kv260-003",
            device_type=DeviceType.FPGA_KV260,
            model="AMD Kria KV260 (lab unit, revB)",
            internal_ip="192.168.2.121",
            ssh_user="ubuntu003",
            capabilities=_kv260_capabilities,
        )
        kv260_real4 = await upsert_device(
            db,
            name="fpga-kv260-004",
            device_type=DeviceType.FPGA_KV260,
            model="AMD Kria KV260 (lab unit, revB)",
            internal_ip="192.168.2.146",
            ssh_user="ubuntu004",
            capabilities=_kv260_capabilities,
        )
        kv260_real5 = await upsert_device(
            db,
            name="fpga-kv260-005",
            device_type=DeviceType.FPGA_KV260,
            model="AMD Kria KV260 (lab unit, revB)",
            internal_ip="192.168.2.147",
            ssh_user="ubuntu005",
            capabilities=_kv260_capabilities,
        )

        # Other-device-type placeholders (IPs 192.168.20.x — not routable yet,
        # wait for ADR-0012 WG tunnel). The kv260-NN mock pool was dropped on
        # 2026-05-22 — the real fleet is fpga-kv260-001..005 above plus the
        # fpga-kv260-006..009 placeholder rows managed via the admin UI.
        print("\n=== Other device placeholders (192.168.20.x — await WG tunnel) ===")
        await upsert_device(
            db,
            name="jetson-orin-01",
            device_type=DeviceType.JETSON_ORIN,
            model="Jetson Orin Nano 8GB",
            internal_ip="192.168.20.111",
            plug_ip="192.168.30.111",
            capabilities={"jetpack": "6.0", "cuda": "12.2", "tensorrt": True},
        )
        await upsert_device(
            db,
            name="rpi5-01",
            device_type=DeviceType.RPI5,
            model="Raspberry Pi 5 8GB",
            internal_ip="192.168.20.121",
            plug_ip="192.168.30.121",
            capabilities={"gpio": True, "i2c": True, "pcie": True},
        )

        # ---- Demo class wiring so the seed SV's actually have access ---------
        print("\n=== Demo class + enrollments ===")
        lecturer = users_by_email["hung.le@vju.ac.vn"]
        admin_kien = users_by_email["bh.kien@vju.ac.vn"]
        demo_class = await upsert_class(
            db,
            code="BCSE-LAB-DEMO-2026",
            name="VHDL/FPGA Lab — Demo cohort",
            semester="2026-Spring",
            lecturer_id=lecturer.id,
        )
        await db.flush()
        # Enroll all sv01..sv10
        sv_emails = [f"sv{i:02d}@st.vju.ac.vn" for i in range(1, 11)]
        for email in sv_emails:
            sv = users_by_email.get(email)
            if sv is None:
                continue
            await upsert_enrollment(
                db, class_id=demo_class.id, user_id=sv.id, enrolled_by=lecturer.id
            )

        # Assign all real KV260s to the demo class so SV's can book them
        for real_dev in (kv260_real, kv260_real2, kv260_real3, kv260_real4, kv260_real5):
            await upsert_assignment(
                db,
                class_id=demo_class.id,
                device_id=real_dev.id,
                granted_by=lecturer.id,
                weekly_hours=20,
                max_concurrent=1,
                advance_days=14,
            )
        _ = admin_kien  # reserved for future seeding

        await db.commit()
        print("\n=== Done ===")
        print(f"  Default password: {DEFAULT_PASSWORD} (MUST change on first login)")
        print("  Login at: https://sv14.bcse-vju.com/login")
        print("  Demo lab kits:")
        print("    fpga-kv260-001 @ .93  (ubuntu001)")
        print("    fpga-kv260-002 @ .100 (ubuntu002)")
        print("    fpga-kv260-003 @ .121 (ubuntu003)")
        print("    fpga-kv260-004 @ .146 (ubuntu004)")
        print("    fpga-kv260-005 @ .147 (ubuntu005)")
        print("  Demo class:   BCSE-LAB-DEMO-2026 (10 sv enrolled, 24/7 access)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
