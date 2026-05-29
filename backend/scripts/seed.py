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
    # 2026-05-29: trimmed to ONLY this account per thầy's request — all test
    # accounts (backup admin, lecturers, sv01-10) removed so seed never
    # re-creates them. Add real authorised accounts via /admin/users.
    (
        "bh.kien@vju.ac.vn", "Bùi Huy Kiên", UserRole.ADMIN, None,
        ADMIN_BH_KIEN_PASSWORD, False if ADMIN_BH_KIEN_PASSWORD else None,
    ),
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
    status: DeviceStatus = DeviceStatus.AVAILABLE,
    reserved: bool = False,
    managed_by: str | None = None,
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
            ssh_user=ssh_user,
            status=status,
            capabilities=capabilities or {},
            reserved=reserved,
            managed_by=managed_by,
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

        print("\n=== VPS thật — node i7 Proxmox 192.168.2.210 (routable từ SV14) ===")
        for n, ip in ((21, 211), (22, 212), (23, 213)):
            await upsert_device(
                db,
                name=f"sv{n}",
                device_type=DeviceType.VPS,
                model="VPS Ubuntu 24.04 — 4GB RAM / 2 vCPU",
                internal_ip=f"192.168.2.{ip}",
                capabilities={
                    "os": "Ubuntu 24.04",
                    "ram_gb": 4,
                    "vcpu": 2,
                    "disk_gb": 20,
                    "tier": "trung",
                },
            )

        # ESAS-BCSE reserved cluster — pve3 node (192.168.2.230), sv31-33.
        # reserved=True → NOT self-bookable (no block calendar, no student
        # request). Access granted ONLY by an admin via SpecialAccess; the
        # existing SA→gateway flow then mints a session-spanning (stable)
        # password for the whole grant window. See migration 0013.
        print("\n=== VPS reserved — ESAS-BCSE, pve3 192.168.2.230 (admin-grant only) ===")
        for n, ip in ((31, 222), (32, 223), (33, 224)):
            await upsert_device(
                db,
                name=f"sv{n}",
                device_type=DeviceType.VPS,
                model="VPS Ubuntu 24.04 — 4GB RAM / 2 vCPU (ESAS-BCSE)",
                internal_ip=f"192.168.2.{ip}",
                reserved=True,
                managed_by="ESAS-BCSE",
                capabilities={
                    "os": "Ubuntu 24.04",
                    "ram_gb": 4,
                    "vcpu": 2,
                    "disk_gb": 20,
                    "tier": "reserved",
                },
            )

        # GPU-VPS — bcseserver1 (192.168.2.98) with 3× NVIDIA RTX 6000 Ada.
        # One Linux user per GPU on the same host (research0N → GPU N) with
        # cgroup limits (16 GB RAM, 100% CPU) — see [[bcse-ai-server]] memory
        # and bcseserver1's systemctl set-property per user-slice config.
        # status=available so cards appear in /devices/vps under "VPS-GPU"
        # tier; admins can already grant via /admin/vps-access. Real SSH will
        # work once backend admin pubkey is installed on the research0N users.
        print("\n=== GPU-VPS — bcseserver1 192.168.2.98, 3× RTX 6000 Ada (planned) ===")
        for n in (1, 2, 3):
            await upsert_device(
                db,
                name=f"ai{n:02d}",
                device_type=DeviceType.VPS,
                model="GPU-VPS Ubuntu — 1× RTX 6000 Ada 48GB",
                internal_ip="192.168.2.98",
                ssh_user=f"research0{n}",
                capabilities={
                    "os": "Ubuntu 24.04",
                    "vcpu": 8,
                    "ram_gb": 16,
                    "disk_gb": 100,
                    "gpu": "NVIDIA RTX 6000 Ada",
                    "vram_gb": 48,
                    "cuda": "12.4",
                    "tier": "gpu",
                    "gpu_index": n - 1,
                },
            )

        await db.commit()
        print("\n=== Done ===")
        print(f"  Default password: {DEFAULT_PASSWORD} (MUST change on first login)")
        print("  Login at: https://sv14.bcse-vju.com/login")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
