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
import shlex
from dataclasses import dataclass

import asyncssh

from app.core.config import get_settings


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
