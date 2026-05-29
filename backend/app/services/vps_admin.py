"""Admin maintenance ops on VPS — light cleanup over SSH via portal admin key.

Why a separate service:
  - Lives outside the per-booking gateway flow; admin-only.
  - Refuses if anyone has an active gateway session on the VPS so we never
    blow data from under a working student.
  - Reuses the same backend admin key the M5.8 gateway uses for its second
    hop (must already be in target user's authorized_keys — see
    scripts/install_backend_key_on_vps.py).

Scope (per thầy's spec 2026-05-27): LIGHT cleanup only.
  1. Wipe target user's HOME except `.ssh/` (preserve gateway access).
  2. Wipe /tmp.
  3. apt-get clean.
  4. Restart docker if it's running (kills lingering containers).

NO snapshot, NO backup — students are warned upfront that "Reset = mất hết".
"""
from __future__ import annotations

import os
import shlex
from datetime import datetime, timezone
from uuid import UUID

import asyncssh
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, DeviceType, GatewaySession


class VpsAdminError(Exception):
    def __init__(self, code: str, message: str = "", **details):
        super().__init__(message or code)
        self.code = code
        self.details = details


# The cleanup runs as the target SSH user. They have NOPASSWD sudo per
# bcseserver1/proxmox-cloud-init convention. Carefully scoped to /home/<user>,
# /tmp, apt cache, docker — nothing else.
#
# IMPORTANT: `find ... ! -name '.ssh'` keeps the authorized_keys file so the
# next admin connect (and any in-flight gateway session) still works.
def _cleanup_script(target_user: str) -> str:
    home = shlex.quote(f"/home/{target_user}")
    return f"""set +e

echo '=== Disk before ==='
df -h / | tail -1

echo '=== 1. Wipe $USER home (keep .ssh) ==='
find {home} -mindepth 1 -maxdepth 1 ! -name '.ssh' -exec rm -rf {{}} + 2>/dev/null
echo "  home now: $(du -sh {home} 2>/dev/null | cut -f1)"

echo '=== 2. Wipe /tmp ==='
find /tmp -mindepth 1 -maxdepth 1 -exec rm -rf {{}} + 2>/dev/null
echo "  /tmp now: $(du -sh /tmp 2>/dev/null | cut -f1)"

echo '=== 3. apt-get clean ==='
sudo -n apt-get clean 2>&1 | tail -3 || echo '  (no sudo / apt — skip)'

echo '=== 4. Restart docker if running ==='
if systemctl is-active --quiet docker; then
  sudo -n systemctl restart docker 2>&1 | tail -3 && echo '  docker restarted'
else
  echo '  docker not active — skip'
fi

echo '=== Disk after ==='
df -h / | tail -1
echo '=== DONE ==='
"""


async def _has_active_session(db: AsyncSession, device_id: UUID) -> bool:
    """Refuse cleanup if anyone is currently SSHing this VPS."""
    now = datetime.now(timezone.utc)
    row = await db.execute(
        select(GatewaySession.id)
        .where(
            GatewaySession.device_id == device_id,
            GatewaySession.revoked_at.is_(None),
            GatewaySession.expires_at > now,
        )
        .limit(1)
    )
    return row.scalar_one_or_none() is not None


async def cleanup_vps(
    db: AsyncSession, *, device_id: UUID, force: bool = False
) -> dict:
    """SSH to VPS as device.ssh_user with portal admin key and run cleanup.

    Returns: {status, output, started_at, ended_at, device_name, ssh_user}.

    `force=True` skips the no-active-session safety. Only set for explicit
    "I know what I'm doing" admin actions — the API exposes it as a query
    parameter the front-end requires double-confirm to send.
    """
    device = (
        await db.execute(select(Device).where(Device.id == device_id))
    ).scalar_one_or_none()
    if device is None:
        raise VpsAdminError("DEVICE_NOT_FOUND")
    if device.device_type != DeviceType.VPS:
        raise VpsAdminError("NOT_A_VPS", device_type=device.device_type.value)

    if not force and await _has_active_session(db, device_id):
        raise VpsAdminError(
            "ACTIVE_SESSION",
            "Có SV đang dùng VPS này — đợi block kết thúc hoặc force=true",
        )

    key_path = os.environ.get(
        "BACKEND_SSH_KEY_PATH", "/app/ssh-keys/portal_admin_ed25519"
    )
    if not os.path.exists(key_path):
        raise VpsAdminError(
            "MISSING_BACKEND_KEY",
            f"Portal admin key not found at {key_path}",
        )

    script = _cleanup_script(device.ssh_user)
    started_at = datetime.now(timezone.utc)
    output_lines: list[str] = []
    status = "ok"
    error_msg: str | None = None

    try:
        async with asyncssh.connect(
            str(device.internal_ip),
            port=device.ssh_port,
            username=device.ssh_user,
            client_keys=[key_path],
            known_hosts=None,
            connect_timeout=15,
        ) as conn:
            # bash -s reads script from stdin — avoids quoting nightmare
            r = await conn.run("bash -s", input=script, check=False, timeout=120)
            output_lines.append(r.stdout or "")
            if r.stderr:
                output_lines.append(f"[stderr]\n{r.stderr}")
            if r.exit_status != 0:
                status = "partial"
    except asyncssh.Error as e:
        status = "ssh_failed"
        error_msg = str(e)
    except OSError as e:
        status = "ssh_failed"
        error_msg = f"network: {e}"
    except Exception as e:
        status = "error"
        error_msg = str(e)

    ended_at = datetime.now(timezone.utc)
    duration_s = (ended_at - started_at).total_seconds()
    return {
        "status": status,
        "device_name": device.name,
        "ssh_user": device.ssh_user,
        "internal_ip": str(device.internal_ip),
        "output": "\n".join(output_lines).strip(),
        "error": error_msg,
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "duration_seconds": round(duration_s, 2),
    }
