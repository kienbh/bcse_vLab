"""SSH operations against the kit pool — backend-held admin key only.

ADR-0013 (M5.8) deprecated the ephemeral-keypair-for-user flow. What remains
here is the *backend → kit* leg: the jump host's ForceCommand wrapper uses
this key to SSH into the kit on the user's behalf, and we use it for any
backend-initiated kit administration (set password, future provisioning).

Specifically removed in M5.8:
  - generate_ephemeral_keypair / provision_session
  - create_jump_user / delete_jump_user

Those existed for the M5.7 "dynamic per-session Linux user on the jump host"
pattern. ADR-0013 replaced that with a static `vlab` user + per-booking
password, so those helpers have no callers.
"""
from __future__ import annotations

import os
import shlex

import asyncssh


_KIT_SUDO_PASS_ENV = "KIT_SUDO_PASS"


def _kit_sudo_pass() -> str | None:
    return os.environ.get(_KIT_SUDO_PASS_ENV) or None


def is_mock_mode() -> bool:
    return os.environ.get("MOCK_SSH_DEVICES", "true").lower() in {"1", "true", "yes"}


async def set_user_password(
    *,
    device_internal_ip: str,
    device_ssh_port: int,
    device_ssh_user: str,
    backend_admin_key_path: str,
    new_password: str,
) -> bool:
    """SSH to the KIT with the backend admin key and `chpasswd` the target.

    Uses `sudo -S` with `KIT_SUDO_PASS` env when set (pilot mode where the
    kit's sudoers still asks for a password), falls back to NOPASSWD sudo.
    """
    if not os.path.exists(backend_admin_key_path):
        return False
    sudo_pass = _kit_sudo_pass()
    payload = f"{device_ssh_user}:{new_password}"
    if sudo_pass:
        cmd = (
            f"echo {shlex.quote(sudo_pass)} | sudo -S sh -c "
            f"{shlex.quote(f'echo {shlex.quote(payload)} | chpasswd')}"
        )
    else:
        cmd = f"sudo -n sh -c {shlex.quote(f'echo {shlex.quote(payload)} | chpasswd')}"
    try:
        async with asyncssh.connect(
            device_internal_ip,
            port=device_ssh_port,
            username=device_ssh_user,
            client_keys=[backend_admin_key_path],
            known_hosts=None,
        ) as conn:
            r = await conn.run(cmd, check=False)
            return r.exit_status == 0
    except (asyncssh.Error, OSError):
        return False
