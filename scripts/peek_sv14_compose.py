"""Trace what compose is doing — networks, image pull, current state."""
import sys, paramiko
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

j = paramiko.SSHClient(); j.set_missing_host_key_policy(paramiko.AutoAddPolicy())
j.connect("123.16.53.250", port=2223, username="root", password="VJuOffice@2024", timeout=20)
sock = j.get_transport().open_channel("direct-tcpip", ("192.168.2.114", 22), ("127.0.0.1", 0))
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.2.114", username="student", password="Student@2024", sock=sock, timeout=20)


def run(cmd, t=60):
    _, out, err = c.exec_command(cmd, timeout=t)
    o = out.read().decode(errors="replace").strip()
    e = err.read().decode(errors="replace").strip()
    return o + (("\n[stderr] " + e) if e else "")


for cmd in [
    # Show network/image pull progress
    "echo Student@2024 | sudo -S docker network ls",
    "echo Student@2024 | sudo -S docker images | head -15",
    # ALL containers including transient
    "echo Student@2024 | sudo -S docker ps -a 2>&1 | head -20",
    # check if compose is still running
    "ps -ef | grep -E 'compose|pull|registry' | grep -v grep | head -10",
    # disk space
    "df -h /var/lib/docker /opt 2>&1",
    # check buildkit / containerd
    "echo Student@2024 | sudo -S docker system df 2>&1",
]:
    print(f"\n=== $ {cmd}")
    print(run(cmd))

c.close(); j.close()
