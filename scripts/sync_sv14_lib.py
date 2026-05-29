"""Pull frontend/src/lib/{api,auth}.ts from SV14 — they were previously gitignored."""
import os, sys, paramiko
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

REPO = r"c:\Users\Admin\Desktop\files\bcse vLab"
REMOTE = "/opt/vju-lab-portal"

j = paramiko.SSHClient(); j.set_missing_host_key_policy(paramiko.AutoAddPolicy())
j.connect("123.16.53.250", port=2223, username="root", password="VJuOffice@2024", timeout=20)
sock = j.get_transport().open_channel("direct-tcpip", ("192.168.2.114", 22), ("127.0.0.1", 0))
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.2.114", username="student", password="Student@2024", sock=sock, timeout=20)

sftp = c.open_sftp()
for f in ["frontend/src/lib/auth.ts"]:
    sftp.get(f"{REMOTE}/{f}", os.path.join(REPO, f.replace("/", os.sep)))
    print("ok:", f)
sftp.close(); c.close(); j.close()
