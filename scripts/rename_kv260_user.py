"""Rename a KV260 login user via a detached systemd-run script.

Usage:
    python scripts/rename_kv260_user.py <ip> <old_user> <new_user> [--pass NEWPASS]

Connects with the portal-admin key, drops a rename script via sftp, then fires
it through `sudo systemd-run` so it survives the SSH disconnect, kills the
old user's sessions, runs usermod/groupmod/chpasswd, and rewrites the
cloud-init sudoers drop-in. Home dir is moved with `usermod -m`, so the
portal-admin authorized_keys travels with it.

Verifies by reconnecting as the new user with the same portal-admin key.
"""
from __future__ import annotations

import argparse
import io
import socket
import sys
import time
from pathlib import Path

import paramiko

REPO = Path(__file__).resolve().parents[1]
PRIV = REPO / "infrastructure" / "sv14" / "secrets" / "portal_admin_ed25519"

RENAME_SCRIPT = r"""#!/bin/bash
set -e
OLD="$1"; NEW="$2"; NEWPASS="$3"
exec >/var/log/rename_user.log 2>&1
echo "[$(date -Iseconds)] rename $OLD -> $NEW starting"
sleep 10
loginctl terminate-user "$OLD" 2>/dev/null || true
pkill -KILL -u "$OLD" 2>/dev/null || true
sleep 3
usermod -l "$NEW" "$OLD"
usermod -d "/home/$NEW" -m "$NEW"
groupmod -n "$NEW" "$OLD" 2>/dev/null || true
echo "$NEW:$NEWPASS" | chpasswd
for f in /etc/sudoers.d/*; do
  [ -f "$f" ] || continue
  if grep -qE "(^|[[:space:]])$OLD([[:space:]]|$|,)" "$f" 2>/dev/null; then
    sed -i -E "s/(^|[[:space:]])$OLD([[:space:]]|\$|,)/\1$NEW\2/g" "$f"
    echo "  updated $f"
  fi
done
echo "[$(date -Iseconds)] rename $OLD -> $NEW DONE"
"""


def connect_password(ip: str, user: str, password: str) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(ip, username=user, password=password, timeout=15,
              allow_agent=False, look_for_keys=False)
    return c


def connect_key(ip: str, user: str) -> paramiko.SSHClient:
    k = paramiko.Ed25519Key.from_private_key(io.StringIO(PRIV.read_text()))
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(ip, username=user, pkey=k, timeout=15,
              allow_agent=False, look_for_keys=False)
    return c


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 30) -> tuple[int, str, str]:
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode(errors="replace")
    err = e.read().decode(errors="replace")
    rc = o.channel.recv_exit_status()
    return rc, out, err


def sudo_run(c: paramiko.SSHClient, cmd: str, password: str | None,
             timeout: int = 30) -> tuple[int, str, str]:
    """Run a command via sudo, trying NOPASSWD first then -S with password."""
    rc, out, err = run(c, f"sudo -n {cmd}", timeout=timeout)
    if rc == 0 or password is None:
        return rc, out, err
    # need a password
    i, o, e = c.exec_command(f"sudo -S -p '' {cmd}", timeout=timeout)
    i.write(password + "\n")
    i.flush()
    out = o.read().decode(errors="replace")
    err = e.read().decode(errors="replace")
    rc = o.channel.recv_exit_status()
    return rc, out, err


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ip")
    ap.add_argument("old_user")
    ap.add_argument("new_user")
    ap.add_argument("--pass", dest="password", default="abc135",
                    help="new password for the renamed user (default: abc135)")
    ap.add_argument("--sudo-pass", dest="sudo_password", default=None,
                    help="sudo password for the OLD user if NOPASSWD not configured (defaults to --pass)")
    ap.add_argument("--port", type=int, default=22)
    a = ap.parse_args()

    try:
        socket.create_connection((a.ip, a.port), timeout=6).close()
    except OSError as e:
        print(f"[rename] {a.ip}: unreachable ({e})")
        return 2

    print(f"[rename] {a.ip}: connecting as {a.old_user} with portal-admin key")
    try:
        c = connect_key(a.ip, a.old_user)
    except paramiko.AuthenticationException:
        print(f"[rename] {a.ip}: key-auth failed — run add_kv260.py first")
        return 3

    sudo_pw = a.sudo_password or a.password
    rc, _, err = sudo_run(c, "true", sudo_pw)
    if rc != 0:
        print(f"[rename] {a.ip}: sudo failed even with password — aborting")
        print(f"  stderr: {err.strip()}")
        c.close()
        return 4

    sftp = c.open_sftp()
    with sftp.open("/tmp/rename_user.sh", "w") as f:
        f.write(RENAME_SCRIPT)
    sftp.chmod("/tmp/rename_user.sh", 0o755)
    sftp.close()
    print(f"[rename] {a.ip}: script uploaded to /tmp/rename_user.sh")

    unit = f"rename-{a.old_user}-to-{a.new_user}"
    cmd = (
        f"systemd-run --unit={unit} --description='rename {a.old_user} to {a.new_user}' "
        f"/bin/bash /tmp/rename_user.sh {a.old_user} {a.new_user} {a.password}"
    )
    rc, out, err = sudo_run(c, cmd, sudo_pw)
    print(f"[rename] {a.ip}: systemd-run rc={rc}")
    if out.strip():
        print(f"  out: {out.strip()}")
    if err.strip():
        print(f"  err: {err.strip()}")
    c.close()

    print(f"[rename] {a.ip}: waiting 25s for rename to complete...")
    time.sleep(25)

    print(f"[rename] {a.ip}: verifying as {a.new_user}")
    try:
        v = connect_key(a.ip, a.new_user)
    except Exception as e:
        print(f"[rename] {a.ip}: VERIFY FAILED — cannot connect as {a.new_user}: {e}")
        print(f"  check log on device: sudo cat /var/log/rename_user.log")
        return 5

    rc, out, _ = run(v, "whoami; id; hostname; sudo -n true && echo SUDO_OK || echo SUDO_FAIL")
    v.close()
    print(f"[rename] {a.ip}: OK verified as {a.new_user}")
    for ln in out.strip().splitlines():
        print(f"  {ln}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
