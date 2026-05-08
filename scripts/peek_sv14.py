"""Peek at SV14 — what's docker doing now?"""
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
    return (out.read().decode(errors="replace").strip()
            + ("\n[stderr] " + err.read().decode(errors="replace").strip() if err else ""))


for cmd in [
    "echo Student@2024 | sudo -S docker ps -a --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}' 2>&1 | head -20",
    "echo Student@2024 | sudo -S docker images --format 'table {{.Repository}}\\t{{.Tag}}\\t{{.Size}}' 2>&1 | head -20",
    "ps -ef | grep -E 'docker|buildkit|npm|next|node|build' | grep -v grep | head -20",
    "echo Student@2024 | sudo -S journalctl -u docker --no-pager -n 30 --since '5 min ago' 2>&1 | tail -30",
    "free -h",
    "df -h /",
    "ls -la /opt/vju-lab-portal/build* 2>/dev/null || echo no build dir",
]:
    print(f"\n=== $ {cmd}")
    print(run(cmd))

c.close(); j.close()
