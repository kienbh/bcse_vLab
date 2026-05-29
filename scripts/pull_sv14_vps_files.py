"""Pull all VPS-related files from SV14 into the local repo.

Strategy: list files SV14 has that touch VPS / access_request / require_lecturer /
device_type enum (Migration 0009 too — referenced by 0010), tar them up, scp down,
extract into the local working tree. Then we commit the import as a single
'chore' commit before starting fast-lane work.
"""
import os, sys, posixpath, tarfile, io, paramiko
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

REPO_ROOT = r"c:\Users\Admin\Desktop\files\bcse vLab"
REMOTE_ROOT = "/opt/vju-lab-portal"

j = paramiko.SSHClient(); j.set_missing_host_key_policy(paramiko.AutoAddPolicy())
j.connect("123.16.53.250", port=2223, username="root", password="VJuOffice@2024", timeout=20)
sock = j.get_transport().open_channel("direct-tcpip", ("192.168.2.114", 22), ("127.0.0.1", 0))
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.2.114", username="student", password="Student@2024", sock=sock, timeout=20)


def run(cmd):
    _, out, err = c.exec_command(cmd, timeout=90)
    return out.read().decode(errors="replace"), err.read().decode(errors="replace").strip()


# --- 1. Discover files touched by the VPS work ---
discovery = [
    # All migrations >= 0008 (so we get 0009 too, referenced by 0010 down_revision)
    "ls /opt/vju-lab-portal/backend/migrations/versions/ | sort | awk '/000[89]|001[0-9]/'",
    # VPS-named files
    "find /opt/vju-lab-portal/backend -name '*vps*' -o -name '*access_request*' 2>/dev/null",
    "find /opt/vju-lab-portal/frontend/src -path '*vps*' -o -name '*vps*' 2>/dev/null",
    # Likely touched glue files — print them, we'll diff against local manually
    "ls /opt/vju-lab-portal/backend/app/models/",
    "ls /opt/vju-lab-portal/backend/app/schemas/",
    "ls /opt/vju-lab-portal/backend/app/api/routes/",
    "grep -l 'AccessRequest\\|vps_access\\|require_lecturer\\|VPS' "
    "/opt/vju-lab-portal/backend/app/models/__init__.py "
    "/opt/vju-lab-portal/backend/app/schemas/__init__.py "
    "/opt/vju-lab-portal/backend/app/api/__init__.py "
    "/opt/vju-lab-portal/backend/app/api/deps.py "
    "/opt/vju-lab-portal/backend/app/main.py 2>/dev/null",
]
for cmd in discovery:
    out, err = run(cmd)
    print(f"\n=== $ {cmd}")
    print(out.strip())
    if err: print(f"[stderr] {err}")

c.close(); j.close()
