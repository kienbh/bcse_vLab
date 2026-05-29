"""Round 2 — confirm exact M5.9 commit deployed, prober/janitor running, kienlab mystery."""
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


def run(cmd: str, timeout: int = 60) -> str:
    _, out, err = c.exec_command(cmd, timeout=timeout)
    o = out.read().decode(errors="replace").strip()
    e = err.read().decode(errors="replace").strip()
    return o + (("\n[stderr] " + e) if e else "")


CMDS = [
    # which alembic versions exist in the image?
    "echo Student@2024 | sudo -S docker exec vju-lab-portal-backend-1 find /app -name '*.py' -path '*alembic*' 2>&1 | head -30",
    # latest migration file content fingerprint
    "echo Student@2024 | sudo -S docker exec vju-lab-portal-backend-1 sh -c 'ls -la /app/backend/alembic/versions 2>/dev/null || ls -la /app/migrations/versions 2>/dev/null || find / -name 0009*.py 2>/dev/null | head' 2>&1",
    # tail of backend on a wider time window — looking for prober + janitor startup lines
    "echo Student@2024 | sudo -S docker logs vju-lab-portal-backend-1 --since 2d 2>&1 | grep -iE 'prober|janitor|startup|started|background' | head -30",
    # look at frontend page bundle to confirm 30s poll lives (ec323bf — UI auto-poll)
    "echo Student@2024 | sudo -S docker exec vju-lab-portal-frontend-1 sh -c 'grep -l 30000 .next/static/chunks/app/admin 2>/dev/null | head' 2>&1",
    # compose project name and uptime
    "echo Student@2024 | sudo -S docker compose -f /opt/vju-lab-portal/infrastructure/sv14/docker-compose.prod.yml -p vju-lab-portal ps 2>&1",
    # who is user kienlab? when created? where is HOME?
    "getent passwd kienlab 2>&1",
    "ls -la /home/kienlab 2>&1 | head -10",
    "echo Student@2024 | sudo -S pgrep -afu kienlab 2>&1 | head",
    # is that npm start related to project? trace cwd of PID 610499
    "echo Student@2024 | sudo -S readlink /proc/610499/cwd 2>&1",
    "echo Student@2024 | sudo -S cat /proc/610499/cmdline 2>&1 | tr '\\0' ' '; echo",
    # look at compose env for PROBE_INTERVAL
    "echo Student@2024 | sudo -S grep -iE 'probe|prober|interval|janitor|encryption' /opt/vju-lab-portal/infrastructure/sv14/.env.prod 2>&1 | sed 's/=.*KEY.*/=<redacted>/'",
    # count of reset_request rows + gateway_session rows + power_state distribution
    "echo Student@2024 | sudo -S docker exec vju-lab-portal-postgres-1 psql -U vlab -d vlab -c \"SELECT (SELECT COUNT(*) FROM reset_requests) AS resets, (SELECT COUNT(*) FROM gateway_sessions) AS gw_sessions, (SELECT COUNT(*) FROM devices) AS devices;\" 2>&1",
    "echo Student@2024 | sudo -S docker exec vju-lab-portal-postgres-1 psql -U vlab -d vlab -c \"SELECT power_state, COUNT(*) FROM devices GROUP BY power_state;\" 2>&1",
    # alembic head listing — any 0008/0009 description we can read?
    "echo Student@2024 | sudo -S docker exec vju-lab-portal-backend-1 alembic -c /app/alembic.ini history 2>&1 | tail -15",
    # disk hot spots
    "echo Student@2024 | sudo -S sh -c 'du -sh /var/lib/docker 2>/dev/null; du -sh /var/log 2>/dev/null; du -sh /var/cache 2>/dev/null'",
    "echo Student@2024 | sudo -S docker system df 2>&1",
    # CF tunnel rule for sv14 — is it pointed at SV08 192.168.2.108:80?
    "echo Student@2024 | sudo -S iptables -L INPUT -n -v 2>&1 | head",
]

for cmd in CMDS:
    print(f"\n=== $ {cmd[:140]}")
    print(run(cmd))

c.close()
j.close()
