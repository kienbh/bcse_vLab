"""SSH session management — ephemeral ed25519 keys per session.

When a booking starts (RQ scheduled job picks up at start_time), the manager:
  1. Generates a fresh ed25519 keypair
  2. Connects to the device using backend's master admin key (from device_credentials)
  3. Appends the ephemeral pubkey to /home/<ssh_user>/.ssh/authorized_keys with expiry comment
  4. Returns (private_key_str, fingerprint, wetty_url) — private key is RETURNED ONCE, never stored

When the booking ends (or is cancelled / kicked):
  1. SSH back in
  2. Strip the line containing the session-tagged comment
  3. Update sessions.status

If `MOCK_SSH_DEVICES` env (default true when DEVICE_POOL_CIDR unreachable) is set, all
operations log the intent and return a synthetic key — useful for local dev / when WG tunnel
to Hòa Lạc lab isn't yet up (per ADR-0011/0012).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import secrets
import shlex
import string
from dataclasses import dataclass

import asyncssh

from app.core.config import get_settings


# Pilot: the lab KIT user `ubuntu` has the same password on every kit because
# they were imaged from the same SD card. We use it to drive `sudo -S` for
# `chpasswd`. In a multi-tenant prod world the sudoers file should have
# `ubuntu ALL=NOPASSWD: /usr/sbin/chpasswd` and we'd skip the env entirely.
_KIT_SUDO_PASS_ENV = "KIT_SUDO_PASS"


def _kit_sudo_pass() -> str | None:
    return os.environ.get(_KIT_SUDO_PASS_ENV) or None


def generate_session_password(length: int = 12) -> str:
    """Random alphanumeric password — easy to type/paste, no shell metachars."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


@dataclass
class ProvisionResult:
    private_key_pem: str
    public_key_line: str
    fingerprint: str
    expires_tag: str
    mocked: bool


def _is_mock_mode() -> bool:
    return os.environ.get("MOCK_SSH_DEVICES", "true").lower() in {"1", "true", "yes"}


def _ed25519_fingerprint(public_key_line: str) -> str:
    """SHA256:base64 fingerprint of an ed25519 public key (the RFC 4716 standard)."""
    parts = public_key_line.strip().split()
    if len(parts) < 2:
        return "SHA256:unknown"
    try:
        keydata = base64.b64decode(parts[1])
    except Exception:
        return "SHA256:unknown"
    digest = hashlib.sha256(keydata).digest()
    b64 = base64.b64encode(digest).decode().rstrip("=")
    return f"SHA256:{b64}"


def generate_ephemeral_keypair(comment: str) -> tuple[str, str, str]:
    """Returns (private_pem, public_key_line, fingerprint) for a fresh ed25519 keypair."""
    key = asyncssh.generate_private_key("ssh-ed25519", comment=comment)
    private_pem = key.export_private_key("openssh").decode()
    public_line = key.export_public_key("openssh").decode().strip()
    if comment and not public_line.endswith(comment):
        public_line = f"{public_line} {comment}"
    fp = _ed25519_fingerprint(public_line)
    return private_pem, public_line, fp


async def provision_session(
    *,
    device_internal_ip: str,
    device_ssh_port: int,
    device_ssh_user: str,
    backend_admin_key_path: str,
    session_tag: str,
    expires_at_iso: str,
) -> ProvisionResult:
    """Generate ephemeral keypair + push to device authorized_keys.

    `session_tag` is a unique label embedded in the public key comment so cleanup
    can find and strip the right line later.
    """
    settings = get_settings()
    comment = f"vju-lab-portal session={session_tag} expires={expires_at_iso}"
    private_pem, public_line, fp = generate_ephemeral_keypair(comment)

    if _is_mock_mode() or not os.path.exists(backend_admin_key_path):
        return ProvisionResult(
            private_key_pem=private_pem,
            public_key_line=public_line,
            fingerprint=fp,
            expires_tag=session_tag,
            mocked=True,
        )

    # Real path: SSH to device + append to authorized_keys
    cmd = (
        "mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
        f"echo {shlex.quote(public_line)} >> ~/.ssh/authorized_keys && "
        "chmod 600 ~/.ssh/authorized_keys"
    )
    async with asyncssh.connect(
        device_internal_ip,
        port=device_ssh_port,
        username=device_ssh_user,
        client_keys=[backend_admin_key_path],
        known_hosts=None,
    ) as conn:
        result = await conn.run(cmd, check=True)
    return ProvisionResult(
        private_key_pem=private_pem,
        public_key_line=public_line,
        fingerprint=fp,
        expires_tag=session_tag,
        mocked=False,
    )


async def set_user_password(
    *,
    device_internal_ip: str,
    device_ssh_port: int,
    device_ssh_user: str,
    backend_admin_key_path: str,
    new_password: str,
) -> bool:
    """SSH to the KIT with the admin key and `chpasswd` the target user's password.

    Uses sudo with `KIT_SUDO_PASS` env (pilot-mode) — falls back to expecting
    NOPASSWD sudo if env is unset. Returns True on success.
    """
    if not os.path.exists(backend_admin_key_path):
        return False
    sudo_pass = _kit_sudo_pass()
    payload = f"{device_ssh_user}:{new_password}"
    if sudo_pass:
        # sudo -S reads password from stdin
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
            # chpasswd outputs nothing on success; non-zero exit is failure
            return r.exit_status == 0
    except (asyncssh.Error, OSError):
        return False


async def lock_user_password(
    *,
    device_internal_ip: str,
    device_ssh_port: int,
    device_ssh_user: str,
    backend_admin_key_path: str,
) -> bool:
    """Set the user's password to a random unknown value — effectively locks
    password auth without disabling the account (so portal_admin key access
    still works for future sessions / sweeper cleanup).
    """
    return await set_user_password(
        device_internal_ip=device_internal_ip,
        device_ssh_port=device_ssh_port,
        device_ssh_user=device_ssh_user,
        backend_admin_key_path=backend_admin_key_path,
        new_password=generate_session_password(32),
    )


async def create_jump_user(
    *,
    sv14_host: str,
    sv14_ssh_port: int,
    sv14_ssh_user: str,
    backend_admin_key_path: str,
    session_tag: str,
    pubkey_line: str,
) -> bool:
    """Create a dynamic SSH jump user on SV14 + install the user's pubkey.

    The SV14 host must already have `setup-jump-host.sh` applied — that
    installs the constrained sudoers rules + sshd Match-Group block. This
    function relies on those constraints; without them sudo will reject
    or `Match Group vjujump` won't restrict to PermitOpen.

    On success the user can `ssh -J <session_tag>@sv14_public:port host:22`
    to any KIT in the Match Group's PermitOpen whitelist.

    Returns True only when every step succeeded.
    """
    if not os.path.exists(backend_admin_key_path):
        return False
    # session_tag must match `sess-<alnum>` because the sudoers rule
    # restricts the username pattern; reject anything else early.
    if not session_tag.startswith("sess-") or len(session_tag) > 30:
        return False

    home = f"/home/{session_tag}"
    cmds = [
        f"sudo /usr/sbin/useradd -m -s /usr/sbin/nologin -G vjujump {session_tag}",
        f"sudo /usr/bin/install -d -m 700 -o {session_tag} -g {session_tag} {home}/.ssh",
        f"echo {shlex.quote(pubkey_line)} | sudo /usr/bin/tee {home}/.ssh/authorized_keys > /dev/null",
        f"sudo /usr/bin/chmod 600 {home}/.ssh/authorized_keys",
        f"sudo /usr/bin/chown {session_tag}:{session_tag} {home}/.ssh/authorized_keys",
    ]
    try:
        async with asyncssh.connect(
            sv14_host,
            port=sv14_ssh_port,
            username=sv14_ssh_user,
            client_keys=[backend_admin_key_path],
            known_hosts=None,
        ) as conn:
            for c in cmds:
                r = await conn.run(c, check=False)
                if r.exit_status != 0:
                    # On failure, attempt to roll back so we don't leak users.
                    await conn.run(
                        f"sudo /usr/sbin/userdel -r {session_tag}", check=False
                    )
                    return False
        return True
    except (asyncssh.Error, OSError):
        return False


async def delete_jump_user(
    *,
    sv14_host: str,
    sv14_ssh_port: int,
    sv14_ssh_user: str,
    backend_admin_key_path: str,
    session_tag: str,
) -> bool:
    """Remove a jump user from SV14 — `userdel -r` drops home + keys atomically.

    Idempotent: returns True if the user is gone (either we deleted it or
    it didn't exist).
    """
    if not os.path.exists(backend_admin_key_path):
        return False
    if not session_tag.startswith("sess-") or len(session_tag) > 30:
        return False
    try:
        async with asyncssh.connect(
            sv14_host,
            port=sv14_ssh_port,
            username=sv14_ssh_user,
            client_keys=[backend_admin_key_path],
            known_hosts=None,
        ) as conn:
            r = await conn.run(
                f"sudo /usr/sbin/userdel -r {session_tag}", check=False
            )
            # `userdel` returns 6 if the user doesn't exist — that's fine.
            return r.exit_status in (0, 6)
    except (asyncssh.Error, OSError):
        return False


async def revoke_session(
    *,
    device_internal_ip: str,
    device_ssh_port: int,
    device_ssh_user: str,
    backend_admin_key_path: str,
    session_tag: str,
) -> bool:
    """Strip the line tagged with `session_tag` from authorized_keys. Returns True if removed."""
    if _is_mock_mode() or not os.path.exists(backend_admin_key_path):
        return True

    # Use sed -i to delete lines containing the unique tag
    safe_tag = session_tag.replace("/", r"\/").replace("'", r"\'")
    cmd = (
        "test -f ~/.ssh/authorized_keys && "
        f"sed -i.bak '/session={safe_tag}/d' ~/.ssh/authorized_keys"
    )
    try:
        async with asyncssh.connect(
            device_internal_ip,
            port=device_ssh_port,
            username=device_ssh_user,
            client_keys=[backend_admin_key_path],
            known_hosts=None,
        ) as conn:
            await conn.run(cmd, check=False)
        return True
    except (asyncssh.Error, OSError):
        return False
