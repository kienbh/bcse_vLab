"""Audit what's actually deployed on SV14 — Alembic head, M5.9 files, container env."""
import sys
import paramiko

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

j = paramiko.SSHClient()
j.set_missing_host_key_policy(paramiko.AutoAddPolicy())
j.connect("123.16.53.250", port=2223, username="root", password="VJuOffice@2024", timeout=20)
sock = j.get_transport().open_channel("direct-tcpip", ("192.168.2.114", 22), ("127.0.0.1", 0))
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.2.114", username="student", password="Student@2024", sock=sock, timeout=20)


def run(cmd: str) -> str:
    _, out, err = c.exec_command(cmd, timeout=60)
    o = out.read().decode(errors="replace").strip()
    e = err.read().decode(errors="replace").strip()
    return o + (("\n[stderr] " + e) if e else "")


CMDS = [
    # current Alembic head in DB
    "echo Student@2024 | sudo -S docker exec vju-lab-portal-backend-1 alembic -c /app/alembic.ini current 2>&1",
    # what migration files exist in the image
    "echo Student@2024 | sudo -S docker exec vju-lab-portal-backend-1 ls -1 /app/alembic/versions 2>&1",
    # does the prober module exist in the backend image?
    "echo Student@2024 | sudo -S docker exec vju-lab-portal-backend-1 ls -1 /app/app/services 2>&1",
    # does the reset-requests route exist?
    "echo Student@2024 | sudo -S docker exec vju-lab-portal-backend-1 ls -1 /app/app/api/routes 2>&1",
    # does the device model have power_state column?
    "echo Student@2024 | sudo -S docker exec vju-lab-portal-backend-1 grep -n 'power_state' /app/app/models/device.py 2>&1",
    # frontend pages — admin/reset-queue and admin/audit?
    "echo Student@2024 | sudo -S docker exec vju-lab-portal-frontend-1 ls -1 .next/server/app/admin 2>&1",
    # what version label do images carry (created date)?
    "echo Student@2024 | sudo -S docker inspect vju-lab-portal-backend:latest --format '{{.Created}} {{.Id}}' 2>&1",
    "echo Student@2024 | sudo -S docker inspect vju-lab-portal-frontend:latest --format '{{.Created}} {{.Id}}' 2>&1",
    # disk breakdown — what's eating space?
    "echo Student@2024 | sudo -S du -sh /var/lib/docker/* 2>/dev/null | sort -h | tail -10",
    "echo Student@2024 | sudo -S du -sh /opt/vju-lab-portal/* 2>/dev/null",
    # any container restarts in last 24h?
    "echo Student@2024 | sudo -S docker events --since 24h --until 0s --filter event=restart --filter event=die --format '{{.Time}} {{.Type}} {{.Action}} {{.Actor.Attributes.name}}' 2>&1 | head -30",
    # backend recent log lines — prober running?
    "echo Student@2024 | sudo -S docker logs --tail 40 vju-lab-portal-backend-1 2>&1 | tail -40",
    # janitor (gateway) running?
    "echo Student@2024 | sudo -S docker logs --tail 20 vju-lab-portal-worker-1 2>&1 | tail -20",
    # which kienlab npm-start process? (mystery from peek_sv14)
    "ps -fp 610499 2>&1",
]

for cmd in CMDS:
    print(f"\n=== $ {cmd[:120]}")
    print(run(cmd))

c.close()
j.close()
