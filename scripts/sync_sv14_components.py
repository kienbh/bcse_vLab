"""Pull updated frontend components from SV14 (FamilyDashboard tier scheme)."""
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
    "frontend/src/components/FamilyDashboard.tsx",
    "frontend/src/components/DeviceCard.tsx",
    "frontend/src/components/AuthGate.tsx",
    "frontend/src/components/CameraPanel.tsx",
    "frontend/src/components/Countdown.tsx",
    "frontend/src/components/AdminPageHeader.tsx",
    "frontend/src/components/Lightbox.tsx",
    "frontend/src/components/QuotaWidget.tsx",
    "frontend/src/components/ResetQueueBadge.tsx",
    "frontend/src/components/UserMenu.tsx",
    "frontend/src/components/BackendStatus.tsx",
]:
    try:
        dst = os.path.join(REPO, f.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        sftp.get(f"{REMOTE}/{f}", dst)
        print("ok:", f)
    except FileNotFoundError:
        print("skip:", f)
sftp.close(); c.close(); j.close()
