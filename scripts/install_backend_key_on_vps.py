"""Install the canonical backend admin pubkey on the 3 VPS (sv21/22/23).

This is the "optional follow-up" from docs/14-vps-integration.md that lets
the PVE jump host's ForceCommand wrapper SSH into the VPS as `student` using
`/etc/vlab/backend_ed25519`. Without it, gateway auth succeeds but the
second hop fails — student sees what looks like "wrong password".

Idempotent: skips a VPS if the key is already in authorized_keys.
"""
from __future__ import annotations

import sys

import paramiko

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


VPS_IPS = [
    ("sv21", "192.168.2.211"),
    ("sv22", "192.168.2.212"),
    ("sv23", "192.168.2.213"),
    # pve3 ESAS-BCSE reserved cluster — gateway hop-2 for the external dev team
    ("sv31", "192.168.2.222"),
    ("sv32", "192.168.2.223"),
    ("sv33", "192.168.2.224"),
]
VPS_USER = "student"
VPS_PASS = "Student@2024"

# Canonical backend admin pubkey — read live from SV14 backend container in
# main() so we never drift from what the gateway actually uses.


def _open_jump() -> paramiko.SSHClient:
    j = paramiko.SSHClient()
    j.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    j.connect(
        "123.16.53.250",
        port=2223,
        username="root",
        password="VJuOffice@2024",
        timeout=20,
    )
    return j


def _open_via_jump(jump: paramiko.SSHClient, host: str, user: str, pw: str) -> paramiko.SSHClient:
    sock = jump.get_transport().open_channel("direct-tcpip", (host, 22), ("127.0.0.1", 0))
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(host, username=user, password=pw, sock=sock, timeout=20)
    return c


def _fetch_pubkey(jump: paramiko.SSHClient) -> str:
    """Derive the pubkey from the LIVE private key inside the backend container.

    Don't trust the `.pub` file on disk — `/opt/.../secrets/portal_admin_ed25519.pub`
    was found to be stale (orphan from an old key) and does NOT match
    `portal_admin_ed25519`. The container's private key is the source of truth
    because that's what the gateway actually uses.
    """
    sv14 = _open_via_jump(jump, "192.168.2.114", "student", "Student@2024")
    try:
        cmd = (
            "echo Student@2024 | sudo -S docker exec vju-lab-portal-backend-1 "
            "ssh-keygen -y -f /app/ssh-keys/portal_admin_ed25519"
        )
        _, out, _ = sv14.exec_command(cmd, timeout=20)
        line = out.read().decode().strip().splitlines()[-1] if out else ""
        # ssh-keygen -y output has no comment — add one so it's auditable.
        if line.startswith("ssh-") and len(line.split()) == 2:
            line = f"{line} portal_admin@sv14"
        return line
    finally:
        sv14.close()


def _install_on_vps(jump: paramiko.SSHClient, name: str, ip: str, pubkey: str) -> None:
    print(f"\n=== {name} ({ip}) ===")
    try:
        c = _open_via_jump(jump, ip, VPS_USER, VPS_PASS)
    except Exception as e:
        print(f"  ✗ SSH failed: {e}")
        return
    try:
        # Read current authorized_keys
        _, out, _ = c.exec_command("mkdir -p ~/.ssh && touch ~/.ssh/authorized_keys && cat ~/.ssh/authorized_keys", timeout=10)
        existing = out.read().decode()
        # Match by key body, not by comment — safe against label drift.
        key_body = pubkey.split()[1] if len(pubkey.split()) >= 2 else pubkey
        if key_body in existing:
            print(f"  ✓ already installed — skip")
            return
        # Append + tighten perms (single command so partial failures are visible).
        safe_key = pubkey.replace("'", "'\\''")
        cmd = (
            f"printf '%s\\n' '{safe_key}' >> ~/.ssh/authorized_keys && "
            "chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys && "
            "echo INSTALLED"
        )
        _, out, err = c.exec_command(cmd, timeout=10)
        result = out.read().decode().strip()
        err_text = err.read().decode().strip()
        if result == "INSTALLED":
            print(f"  ✓ installed")
        else:
            print(f"  ✗ unexpected: out={result!r} err={err_text!r}")
    finally:
        c.close()


def _verify_keyauth(jump: paramiko.SSHClient, name: str, ip: str, pubkey: str) -> None:
    """Use the SV14 backend container (which has the matching private key) to
    test a passwordless ssh to student@<vps>. If this passes, the PVE gateway
    using the same key will pass too."""
    sv14 = _open_via_jump(jump, "192.168.2.114", "student", "Student@2024")
    try:
        cmd = (
            "echo Student@2024 | sudo -S docker exec vju-lab-portal-backend-1 "
            f"ssh -o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=8 "
            f"-i /app/ssh-keys/portal_admin_ed25519 student@{ip} 'echo OK_$(hostname)'"
        )
        _, out, err = sv14.exec_command(cmd, timeout=30)
        result = out.read().decode().strip()
        err_text = err.read().decode().strip()
        if result.startswith("OK_"):
            print(f"  ✓ key-auth verified: {result}")
        else:
            print(f"  ✗ key-auth failed: out={result!r} err={err_text!r}")
    finally:
        sv14.close()


def main() -> None:
    print("Opening PVE jump...")
    jump = _open_jump()
    try:
        print("Fetching backend admin pubkey from SV14 ...")
        pubkey = _fetch_pubkey(jump)
        if not pubkey.startswith("ssh-"):
            print(f"ABORT: bad pubkey: {pubkey!r}")
            sys.exit(1)
        print(f"Pubkey: {pubkey}")
        for name, ip in VPS_IPS:
            _install_on_vps(jump, name, ip, pubkey)
        print("\n=== Verifying key-auth from SV14 backend container ===")
        for name, ip in VPS_IPS:
            print(f"\n--- {name} ({ip}) ---")
            _verify_keyauth(jump, name, ip, pubkey)
    finally:
        jump.close()


if __name__ == "__main__":
    main()
