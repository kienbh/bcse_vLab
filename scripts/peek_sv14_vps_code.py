"""Pull VPS-related code from SV14 so we can understand current schema/flow."""
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
    o = out.read().decode(errors="replace")
    e = err.read().decode(errors="replace").strip()
    return o + (f"\n[stderr] {e}" if e else "")


FILES = [
    "/opt/vju-lab-portal/backend/migrations/versions/20260522_1200_0008_device_type_vps.py",
    "/opt/vju-lab-portal/backend/migrations/versions/20260525_1100_0010_vps_access_requests.py",
    "/opt/vju-lab-portal/backend/app/api/routes/vps_access.py",
    "/opt/vju-lab-portal/backend/app/services/vps_access.py",
    "/opt/vju-lab-portal/frontend/src/app/devices/vps/page.tsx",
    "/opt/vju-lab-portal/frontend/src/app/vps-access/page.tsx",
    "/opt/vju-lab-portal/frontend/src/app/admin/vps-access/page.tsx",
]

for path in FILES:
    print(f"\n\n========= FILE: {path} =========")
    print(run(f"cat {path}"))

# Also peek the actual DB schema via the right env
print("\n\n========= DB ENV =========")
print(run("cat /opt/vju-lab-portal/infrastructure/sv14/.env.prod 2>/dev/null | grep -E '^(POSTGRES_|DATABASE_)' | head -10"))

c.close(); j.close()
