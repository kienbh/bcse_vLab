"""Verify SV14 can reach the FPGA pool (192.168.20.0/24) + 3 specific test devices.

Pre-flight for the real test session. If ping fails, we need the Proxmox vmbr1
bridge + a second virtio NIC on the SV14 VM before we can flip MOCK_SSH_DEVICES
off.
"""
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
    o = out.read().decode(errors="replace").strip()
    e = err.read().decode(errors="replace").strip()
    return o + (("\n[err] " + e) if e else "")


for title, cmd in [
    ("# A. SV14 network interfaces",
     "ip -4 addr show | awk '/inet/{print $NF, $2}' | grep -v 127.0"),

    ("# B. SV14 routing table",
     "ip -4 route"),

    ("# C. Try to ping kv260-01 (192.168.20.101)",
     "ping -c 2 -W 2 192.168.20.101 2>&1 | tail -4 || echo 'unreachable'"),

    ("# D. Try ping kv260-02 + kv260-03",
     "for ip in 192.168.20.102 192.168.20.103; do "
     "echo \"--- $ip ---\"; ping -c 1 -W 2 $ip 2>&1 | tail -2; done"),

    ("# E. Check if device pool subnet 192.168.20.0/24 is in route table",
     "ip -4 route | grep 192.168.20 || echo 'NO ROUTE to 192.168.20.0/24'"),

    ("# F. Current MOCK_SSH_DEVICES env in backend container",
     "docker exec vju-lab-portal-backend-1 sh -c 'echo MOCK_SSH_DEVICES=${MOCK_SSH_DEVICES:-not_set} '"
     "&& echo '(grep .env.prod)' && sudo grep MOCK_SSH /opt/vju-lab-portal/infrastructure/sv14/.env.prod 2>&1 | head"),

    ("# G. Check backend admin SSH key file exists",
     "docker exec vju-lab-portal-backend-1 sh -c 'ls -la /app/ssh-keys/ 2>&1; "
     "test -f /app/ssh-keys/portal_admin_ed25519 && echo KEY_EXISTS || echo KEY_MISSING'"),

    ("# H. Devices in DB",
     "docker exec vju-lab-portal-postgres-1 psql -U labportal -d labportal -tA -c "
     "\"SELECT name, internal_ip, status FROM devices ORDER BY name;\""),
]:
    print(f"\n{title}")
    print(run(cmd))

c.close()
j.close()
