"""Sync VPS + schedule baseline from SV14 production into the local repo.

Lists modified/new files, tars them on the remote, SFTPs the tarball down,
extracts into the working tree. Run `git status` after to inspect.

Files included:
  - backend migrations 0008/0009/0010
  - backend models access_request.py + schedule.py + edited __init__ + enums
  - backend services vps_access.py
  - backend schemas __init__ + schedule.py
  - backend api routes vps_access.py + schedule.py + edited __init__
  - backend api deps.py (require_lecturer)
  - backend main.py (router include)
  - backend tests test_vps_access.py
  - frontend vps pages (3) + devices/page.tsx + nav glue
"""
from __future__ import annotations
import os, sys, posixpath, paramiko
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

REPO_ROOT = r"c:\Users\Admin\Desktop\files\bcse vLab"
REMOTE = "/opt/vju-lab-portal"

FILES = [
    # --- Backend migrations ---
    "backend/migrations/versions/20260522_1200_0008_device_type_vps.py",
    "backend/migrations/versions/20260522_1500_0009_group_scheduling.py",
    "backend/migrations/versions/20260525_1100_0010_vps_access_requests.py",
    # --- Backend models ---
    "backend/app/models/__init__.py",
    "backend/app/models/access_request.py",
    "backend/app/models/schedule.py",
    "backend/app/models/enums.py",
    # --- Backend schemas ---
    "backend/app/schemas/__init__.py",
    "backend/app/schemas/access.py",
    # --- Backend services ---
    "backend/app/services/vps_access.py",
    # --- Backend api ---
    "backend/app/api/deps.py",
    "backend/app/api/routes/__init__.py",
    "backend/app/api/routes/vps_access.py",
    "backend/app/api/routes/schedule.py",
    "backend/app/main.py",
    # --- Backend tests ---
    "backend/tests/test_vps_access.py",
    # --- Frontend ---
    "frontend/src/app/devices/page.tsx",
    "frontend/src/app/devices/vps/page.tsx",
    "frontend/src/app/vps-access/page.tsx",
    "frontend/src/app/admin/vps-access/page.tsx",
    # Glue — nav might link to vps
    "frontend/src/components/Nav.tsx",
    "frontend/src/components/LocaleText.tsx",
    "frontend/src/lib/i18n.ts",
]

j = paramiko.SSHClient(); j.set_missing_host_key_policy(paramiko.AutoAddPolicy())
j.connect("123.16.53.250", port=2223, username="root", password="VJuOffice@2024", timeout=20)
sock = j.get_transport().open_channel("direct-tcpip", ("192.168.2.114", 22), ("127.0.0.1", 0))
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.2.114", username="student", password="Student@2024", sock=sock, timeout=20)


def run(cmd, timeout=60):
    _, out, err = c.exec_command(cmd, timeout=timeout)
    o = out.read().decode(errors="replace")
    e = err.read().decode(errors="replace").strip()
    return o, e


# Check which files actually exist on SV14 (some may be new schemas/* files I guessed wrong)
existing = []
missing = []
for f in FILES:
    o, _ = run(f"test -f {REMOTE}/{f} && echo Y || echo N")
    if o.strip() == "Y":
        existing.append(f)
    else:
        missing.append(f)

print(f"Existing ({len(existing)}):")
for f in existing: print(f"  {f}")
print(f"\nMissing on SV14 ({len(missing)}):")
for f in missing: print(f"  {f}")

# SFTP fetch
sftp = c.open_sftp()
fetched = []
for f in existing:
    src = f"{REMOTE}/{f}"
    dst = os.path.join(REPO_ROOT, f.replace("/", os.sep))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    sftp.get(src, dst)
    fetched.append(f)
sftp.close()

print(f"\nFetched {len(fetched)} files into local repo.")
c.close(); j.close()
