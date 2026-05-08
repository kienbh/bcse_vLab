"""Quick check — what's installed on SV14 after setup."""
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
    _, out, err = c.exec_command(cmd, timeout=30)
    o = out.read().decode(errors="replace").strip()
    e = err.read().decode(errors="replace").strip()
    return o + (("\n[err] " + e) if e else "")


for cmd in [
    "docker --version 2>&1 || echo NOT_INSTALLED",
    "docker compose version 2>&1 || echo NOT_INSTALLED",
    "docker ps --format '{{.Names}} {{.Status}}' 2>&1 | head",
    "ls -la /opt/vju-lab-portal 2>&1",
    "ls -la /opt/vju-lab-portal/infrastructure/sv14 2>&1 | head",
    "swapon --show",
    "sudo ufw status 2>&1 | head -20",
    "free -h",
    "df -h /",
]:
    print(f"\n$ {cmd}")
    print(run(cmd))

c.close()
j.close()
