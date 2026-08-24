"""Pull updated booking-related files from SV14 (added columns since 0009/0010)."""
import os, sys, paramiko
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

REPO = r"D:\files\bcse vLab"
REMOTE = "/opt/vju-lab-portal"

j = paramiko.SSHClient(); j.set_missing_host_key_policy(paramiko.AutoAddPolicy())
j.connect("123.16.53.250", port=2223, username="root", password="VJuOffice@2024", timeout=20)
sock = j.get_transport().open_channel("direct-tcpip", ("192.168.2.114", 22), ("127.0.0.1", 0))
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.2.114", username="student", password="Student@2024", sock=sock, timeout=20)

sftp = c.open_sftp()
for f in [
    "backend/app/models/booking.py",
    "backend/app/models/class_.py",        # Group + Enrollment.group_id
    "backend/app/api/routes/bookings.py",
    "backend/app/api/routes/devices.py",
    "backend/app/api/routes/gateway.py",
    "backend/app/services/access_control.py",
    "backend/app/services/janitor.py",
    "backend/app/services/event_bus.py",
    "backend/app/services/__init__.py",
    "backend/app/schemas/booking.py",
    "backend/app/schemas/schedule.py",
    "backend/app/core/config.py",
]:
    try:
        dst = os.path.join(REPO, f.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        sftp.get(f"{REMOTE}/{f}", dst)
        print("ok:", f)
    except FileNotFoundError:
        print("skip (not on SV14):", f)
sftp.close(); c.close(); j.close()
