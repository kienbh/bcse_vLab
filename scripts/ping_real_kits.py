"""Ping the 3 real lab KITs (192.168.2.93/100/121) from SV14."""
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


def run(cmd: str, timeout: int = 30) -> str:
    _, out, err = c.exec_command(cmd, timeout=timeout)
    return out.read().decode(errors="replace").strip()


for ip, name in [
    ("192.168.2.93", "kv260-lab01"),
    ("192.168.2.100", "kv260-lab02"),
    ("192.168.2.121", "kv260-lab03"),
]:
    print(f"\n# Ping {name} ({ip})")
    print(run(f"ping -c 2 -W 2 {ip} 2>&1 | tail -4"))
    print(f"# Try SSH port 22 reachability")
    print(run(f"timeout 3 bash -c 'cat < /dev/tcp/{ip}/22' 2>&1 | head -1 || echo 'closed/filtered'"))

c.close()
j.close()
