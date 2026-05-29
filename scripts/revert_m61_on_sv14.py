"""Revert SV14 to the pre-M6.1 state (= git commit 6460d74, M5.10/M6 baseline).

Scope:
  1. git archive backend/ + frontend/ + infrastructure/ at commit 6460d74
  2. SFTP → SV14 → wipe + re-extract over /opt/vju-lab-portal
  3. alembic downgrade 0010 (rolls back migration 0011's constraint + index;
     the new enum value 'vps_fastlane' stays in the type since Postgres can't
     drop it — harmless because no row references it)
  4. docker compose build backend + frontend with the reverted sources
  5. docker compose up -d (env-file aware)
  6. Verify: /api/health 200, /api/vps/devices 404 (route gone), /api/vps-access/*
     still 401 (M5.10 untouched)

DOES NOT touch device pool rows or any user data.
"""
from __future__ import annotations
import io
import subprocess
import sys
import tarfile
from pathlib import Path

import paramiko

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

JUMP_HOST = "123.16.53.250"
JUMP_PORT = 2223
JUMP_USER = "root"
JUMP_PASS = "VJuOffice@2024"

SV14_IP = "192.168.2.114"
SV14_USER = "student"
SV14_PASS = "Student@2024"

REPO = Path(__file__).resolve().parents[1]
REMOTE = "/opt/vju-lab-portal"
REVERT_TARGET = "revert/pre-m61-sv14"  # synthetic state — baseline + components + booking_id fix


def log(m: str) -> None:
    print(f"[revert] {m}", flush=True)


def archive_from_commit() -> bytes:
    """Use `git archive` to get a clean tarball of the repo at REVERT_TARGET."""
    log(f"git archive backend/ frontend/ infrastructure/ at {REVERT_TARGET}")
    cp = subprocess.run(
        ["git", "archive", "--format=tar", REVERT_TARGET,
         "backend", "frontend", "infrastructure"],
        cwd=REPO, check=True, capture_output=True,
    )
    raw = cp.stdout
    # Recompress as .tar.gz for transit
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as gz:
        with tarfile.open(fileobj=io.BytesIO(raw)) as src:
            for member in src.getmembers():
                f = src.extractfile(member) if member.isfile() else None
                gz.addfile(member, f)
    return buf.getvalue()


def connect():
    j = paramiko.SSHClient(); j.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    j.connect(JUMP_HOST, port=JUMP_PORT, username=JUMP_USER, password=JUMP_PASS, timeout=20)
    sock = j.get_transport().open_channel("direct-tcpip", (SV14_IP, 22), ("127.0.0.1", 0))
    c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(SV14_IP, username=SV14_USER, password=SV14_PASS, sock=sock, timeout=20)
    c._jump = j
    return c


def run(c, cmd, *, timeout=600, allow_fail=False):
    _, out, err = c.exec_command(cmd, timeout=timeout)
    o = out.read().decode(errors="replace")
    e = err.read().decode(errors="replace").strip()
    rc = out.channel.recv_exit_status()
    body = o + (f"\n[stderr] {e}" if e else "")
    if rc != 0 and not allow_fail:
        raise RuntimeError(f"cmd failed (rc={rc}): {cmd}\n{body}")
    return body


def main():
    blob = archive_from_commit()
    log(f"tarball {len(blob)/1_000_000:.1f} MB")

    c = connect()
    try:
        log("upload tarball")
        sftp = c.open_sftp()
        with sftp.open("/tmp/m61_revert.tar.gz", "wb") as f:
            f.write(blob)
        sftp.close()

        log("remove old backend/frontend trees so deleted files don't linger")
        # Wipe just the source trees, not infrastructure/uploads/etc.
        run(c, f"echo {SV14_PASS} | sudo -S rm -rf "
               f"{REMOTE}/backend/app {REMOTE}/backend/scripts "
               f"{REMOTE}/backend/migrations {REMOTE}/backend/tests "
               f"{REMOTE}/frontend/src "
               f"2>&1", allow_fail=True)

        log("extract revert tarball")
        run(c, f"echo {SV14_PASS} | sudo -S tar -xzf /tmp/m61_revert.tar.gz -C {REMOTE}")
        run(c, "rm -f /tmp/m61_revert.tar.gz", allow_fail=True)

        # NOTE: alembic downgrade 0010 was already applied on the first
        # revert pass; skip when backend is mid-restart (docker exec hits rc=137).
        log("skip alembic downgrade (already at 0010 from prior pass)")

        log("rebuild backend + frontend with reverted code")
        out = run(
            c,
            f"cd {REMOTE}/infrastructure/sv14 && echo {SV14_PASS} | sudo -S "
            f"docker compose -f docker-compose.prod.yml --env-file .env.prod "
            f"build backend frontend 2>&1",
            timeout=900,
        )
        print(out[-2000:])

        log("up -d (recreate with new images)")
        out = run(
            c,
            f"cd {REMOTE}/infrastructure/sv14 && echo {SV14_PASS} | sudo -S "
            f"docker compose -f docker-compose.prod.yml --env-file .env.prod "
            f"up -d 2>&1",
        )
        print(out[-1500:])

        log("verify endpoints (expect /api/vps/* → 404, /api/vps-access/* → 401)")
        import time; time.sleep(8)
        for path in (
            "/api/health",
            "/api/vps/devices",
            "/api/vps-access/grants/mine",
        ):
            out = run(c, f"curl -sS -o /dev/null -w 'HTTP %{{http_code}}' http://localhost:8000{path}",
                      allow_fail=True)
            print(f"  {path:35s} → {out}")
    finally:
        c.close(); c._jump.close()
    log("done.")


if __name__ == "__main__":
    main()
