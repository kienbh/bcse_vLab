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

from sqlalchemy import select

from app.core.db import session_factory
from app.models import Device, DeviceStatus, DeviceType, PlugMapping, PlugType, User, UserRole
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
) -> Device:
    res = await db.execute(select(Device).where(Device.name == name))
    d = res.scalar_one_or_none()
    if d is None:
        d = Device(
            name=name,
            device_type=device_type,
            model=model,
            internal_ip=internal_ip,
            ssh_port=22,
            ssh_user="student",
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
        print(f"  + device {name:18s} {model}")
    else:
        print(f"  = device {name:18s}")
    return d


async def main() -> int:
    factory = session_factory()
    async with factory() as db:
        print(f"=== Whitelist users (default password: {DEFAULT_PASSWORD}) ===")
        for email, full_name, role, code, pw, force in WHITELIST:
            await upsert_user(
                db,
                email=email,
                full_name=full_name,
                role=role,
                code=code,
                password_override=pw,
                force_change=force,
            )

        print("\n=== Devices (mock pool — IPs 192.168.20.x not yet routable from SV14) ===")
        for i in range(1, 10):
            await upsert_device(
                db,
                name=f"kv260-{i:02d}",
                device_type=DeviceType.FPGA_KV260,
                model="Kria KV260 Vision AI Starter Kit",
                internal_ip=f"192.168.20.{100 + i}",
                plug_ip=f"192.168.30.{100 + i}",
                capabilities={"vivado": True, "vitis": True, "pynq": i <= 3},
            )
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

        await db.commit()
        print("\n=== Done ===")
        print(f"  Default password: {DEFAULT_PASSWORD} (MUST change on first login)")
        print("  Login at: https://sv14.bcse-vju.com/login")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
