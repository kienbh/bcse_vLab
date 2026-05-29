"""Find the VPS tier classification thầy set in a prior session."""
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


for cmd in [
    "grep -nE 'vps|tier|kind|tầm|standard|gpu' /opt/vju-lab-portal/frontend/src/components/FamilyDashboard.tsx | head -40",
    "grep -nE 'vps|tier|tầm' /opt/vju-lab-portal/frontend/src/components/DeviceCard.tsx | head -20",
    "grep -rnE 'tầm thấp|tầm trung|tầm cao' /opt/vju-lab-portal/frontend/src/ | head -30",
    "grep -rnE 'low|medium|high|low_tier|mid_tier' /opt/vju-lab-portal/frontend/src/app/devices/vps/ /opt/vju-lab-portal/frontend/src/app/vps-access/ /opt/vju-lab-portal/frontend/src/app/admin/vps-access/ 2>/dev/null | head -30",
    "cat /opt/vju-lab-portal/frontend/src/app/devices/vps/page.tsx",
    "grep -nrE 'tier|kind|tầm|low|medium' /opt/vju-lab-portal/backend/app/models/device.py /opt/vju-lab-portal/backend/app/schemas/device.py 2>&1 | head -30",
    # check capabilities JSON in DB
    "echo Student@2024 | sudo -S docker exec vju-lab-portal-postgres-1 psql -U vlab -d vlab -c \"SELECT name, device_type, capabilities FROM devices WHERE device_type='vps'\" 2>&1 | head -30",
]:
    print(f"\n=== $ {cmd}")
    print(run(cmd))

c.close(); j.close()
