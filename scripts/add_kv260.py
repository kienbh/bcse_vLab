"""Install the portal-admin pubkey on a KV260 and verify key-auth.

Run once the kit is powered on and on the lab LAN. Convention is
FPGA 00X ↔ user ubuntu00X on the device:

    python scripts/add_kv260.py 192.168.2.93  --user ubuntu001
    python scripts/add_kv260.py 192.168.2.100 --user ubuntu002
    python scripts/add_kv260.py 192.168.2.121 --user ubuntu003
    python scripts/add_kv260.py 192.168.2.145 --user ubuntu004
    python scripts/add_kv260.py 192.168.2.146 --user ubuntu005

For a freshly-flashed Kria image the user is still 'ubuntu'; bootstrap
with --user ubuntu then run scripts/rename_kv260_user.py to standardise.

After this, re-seed so the portal picks the device up:

    python scripts/seed_only.py
"""
from __future__ import annotations

import argparse
import io
import socket
import sys
from pathlib import Path

import paramiko

REPO = Path(__file__).resolve().parents[1]
SECRET = REPO / "infrastructure" / "sv14" / "secrets"
PRIV = SECRET / "portal_admin_ed25519"
PUB = SECRET / "portal_admin_ed25519.pub"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ip")
    ap.add_argument("--user", required=True,
                    help="SSH login user on the device (e.g. ubuntu001, or 'ubuntu' for a fresh Kria image)")
    ap.add_argument("--password", "--pass", dest="password", default="abc135")
    ap.add_argument("--port", type=int, default=22)
    a = ap.parse_args()

    # reachability first
    try:
        socket.create_connection((a.ip, a.port), timeout=6).close()
    except OSError as e:
        print(f"[add] {a.ip}:{a.port} unreachable — kit powered on + on LAN? ({e})")
        return 2

    pub = PUB.read_text().strip()
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(a.ip, port=a.port, username=a.user, password=a.password,
              timeout=15, allow_agent=False, look_for_keys=False)
    sftp = c.open_sftp()
    try:
        sftp.mkdir(".ssh")
    except OSError:
        pass
    sftp.chmod(".ssh", 0o700)
    ak = ".ssh/authorized_keys"
    existing = ""
    try:
        with sftp.open(ak, "r") as f:
            existing = f.read().decode()
    except IOError:
        pass
    if "portal-admin@vju-lab" in existing:
        print(f"[add] {a.ip}: pubkey already present — skip")
    else:
        with sftp.open(ak, "a") as f:
            f.write(pub + "\n")
        print(f"[add] {a.ip}: pubkey appended")
    sftp.chmod(ak, 0o600)
    sftp.close()
    c.close()

    k = paramiko.Ed25519Key.from_private_key(io.StringIO(PRIV.read_text()))
    v = paramiko.SSHClient()
    v.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    v.connect(a.ip, port=a.port, username=a.user, pkey=k,
              timeout=15, allow_agent=False, look_for_keys=False)
    _, o, _ = v.exec_command("hostname; cat /proc/device-tree/model; echo KEYAUTH_OK")
    txt = o.read().decode()
    v.close()
    if "KEYAUTH_OK" not in txt:
        print(f"[add] {a.ip}: KEY-AUTH VERIFY FAILED")
        return 1
    print(f"[add] {a.ip}: key-auth OK — {txt.replace(chr(10), ' ').strip()}")
    print("[add] next: python scripts/seed_only.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
