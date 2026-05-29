"""Peek at SV14 — what VPS-related config / code exists?"""
import sys, paramiko
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

j = paramiko.SSHClient(); j.set_missing_host_key_policy(paramiko.AutoAddPolicy())
j.connect("123.16.53.250", port=2223, username="root", password="VJuOffice@2024", timeout=20)
sock = j.get_transport().open_channel("direct-tcpip", ("192.168.2.114", 22), ("127.0.0.1", 0))
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.2.114", username="student", password="Student@2024", sock=sock, timeout=20)


def run(cmd):
    _, out, err = c.exec_command(cmd, timeout=60)
    o = out.read().decode(errors="replace").strip()
    e = err.read().decode(errors="replace").strip()
    return o + (f"\n[stderr] {e}" if e else "")


for cmd in [
    # 1. Code repo state on SV14
    "cd /opt/vju-lab-portal && git log --oneline -5 2>&1",
    "cd /opt/vju-lab-portal && git status --short 2>&1 | head -30",
    "cd /opt/vju-lab-portal && git branch --show-current 2>&1",
    # 2. Frontend VPS pages
    "ls /opt/vju-lab-portal/frontend/src/app/devices/ 2>&1",
    "find /opt/vju-lab-portal/frontend/src -iname '*vps*' 2>&1 | head -20",
    # 3. Backend VPS routes / models / migrations
    "ls /opt/vju-lab-portal/backend/app/api/routes/ 2>&1",
    "find /opt/vju-lab-portal/backend -iname '*vps*' 2>&1 | head -20",
    "ls /opt/vju-lab-portal/backend/alembic/versions/ 2>&1 | tail -10",
    # 4. Running containers + active code path
    "echo Student@2024 | sudo -S docker ps --format 'table {{.Names}}\\t{{.Status}}' 2>&1",
    # 5. DB tables — anything VPS-related?
    "echo Student@2024 | sudo -S docker exec -i $(sudo docker ps -q -f name=postgres) psql -U vjulab -d vjulab -c \"\\dt\" 2>&1 | head -40",
    "echo Student@2024 | sudo -S docker exec -i $(sudo docker ps -q -f name=postgres) psql -U vjulab -d vjulab -c \"SELECT enumlabel FROM pg_enum WHERE enumtypid = 'device_type'::regtype;\" 2>&1",
    # 6. Probe the live URL from inside SV14
    "curl -sS -o /dev/null -w 'HTTP %{http_code}\\n' http://localhost:3000/devices/vps 2>&1",
    "curl -sS -o /dev/null -w 'HTTP %{http_code}\\n' http://localhost:8000/api/devices 2>&1",
]:
    print(f"\n=== $ {cmd}")
    print(run(cmd))

c.close(); j.close()
