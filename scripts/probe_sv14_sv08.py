"""Read-only probe — verify SV14 exists and SV08 ingress slot is free."""
from __future__ import annotations

import sys

import paramiko

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

JUMP_HOST = "123.16.53.250"
JUMP_PORT = 2223
JUMP_USER = "root"
JUMP_PASS = "VJuOffice@2024"

VPS_USER = "student"
VPS_PASS = "Student@2024"

SV14_IP = "192.168.2.114"
SV08_IP = "192.168.2.108"


def jump_client() -> paramiko.SSHClient:
    j = paramiko.SSHClient()
    j.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    j.connect(JUMP_HOST, port=JUMP_PORT, username=JUMP_USER, password=JUMP_PASS, timeout=20)
    return j


def vps_client(jump: paramiko.SSHClient, ip: str) -> paramiko.SSHClient | None:
    creds = [
        ("student", "OLH67LDg8B9yH9co2bXsIt4ZfIWoybea"),  # bcse-intro password (SV08)
        ("student", "Student@2024"),
        ("root", "VJuOffice@2024"),
    ]
    for user, pw in creds:
        try:
            sock = jump.get_transport().open_channel("direct-tcpip", (ip, 22), ("127.0.0.1", 0))
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c.connect(ip, username=user, password=pw, sock=sock, timeout=15)
            print(f"  [auth-ok] {user}@{ip}")
            return c
        except paramiko.AuthenticationException:
            continue
        except Exception as e:
            print(f"  [!] {user}@{ip}: {type(e).__name__}: {e}")
            return None
    print(f"  [!] no creds matched for {ip}")
    return None


def run(c: paramiko.SSHClient, cmd: str) -> str:
    _, out, err = c.exec_command(cmd, timeout=30)
    text = out.read().decode(errors="replace").strip()
    e = err.read().decode(errors="replace").strip()
    if e:
        text += f"\n[stderr] {e}"
    return text


def probe_sv14(jump: paramiko.SSHClient) -> dict:
    print("=" * 60)
    print(f"PROBING SV14 ({SV14_IP})")
    print("=" * 60)
    print("  Trying to reach SV14 from jump host first...")

    # Test reachability from jump host
    j_run = lambda c: jump.exec_command(c, timeout=15)
    _, out, _ = j_run(f"ping -c 2 -W 3 {SV14_IP} 2>&1; echo --; arp -n {SV14_IP} 2>/dev/null")
    print(out.read().decode(errors="replace"))

    _, out, _ = j_run(f"nc -z -w 5 {SV14_IP} 22 && echo SSH_OPEN || echo SSH_CLOSED")
    ssh_status = out.read().decode().strip()
    print(f"  SSH status: {ssh_status}")

    if "SSH_CLOSED" in ssh_status:
        print("  [!] SV14 SSH unreachable — VM likely doesn't exist yet")
        return {"reachable": False}

    c = vps_client(jump, SV14_IP)
    if not c:
        return {"reachable": False}

    facts = {
        "reachable": True,
        "hostname": run(c, "hostname"),
        "os": run(c, "lsb_release -d 2>/dev/null || cat /etc/os-release | head -2"),
        "kernel": run(c, "uname -r"),
        "memory_mb": run(c, "free -m | awk '/Mem:/ {print $2}'"),
        "disk": run(c, "df -h / | tail -1"),
        "ip_addrs": run(c, "ip -4 addr show | awk '/inet / {print $2}'"),
        "docker": run(c, "docker --version 2>&1 || echo NOT_INSTALLED"),
        "compose": run(c, "docker compose version 2>&1 || echo NOT_INSTALLED"),
        "running_containers": run(c, "docker ps --format '{{.Names}} {{.Image}} {{.Ports}}' 2>/dev/null || echo NO_DOCKER"),
        "listening_ports": run(c, "ss -tlnp 2>/dev/null | head -30"),
        "what_uses_port_80": run(c, "ss -tlnp 'sport = :80' 2>/dev/null; sudo lsof -i :80 2>/dev/null | head"),
        "device_pool_ping": run(c, "ping -c 1 -W 3 192.168.20.1 2>&1 | tail -2"),
        "plug_pool_ping": run(c, "ping -c 1 -W 3 192.168.30.1 2>&1 | tail -2"),
        "ip_route": run(c, "ip route show"),
        "opt_dirs": run(c, "ls -la /opt/ 2>/dev/null"),
        "active_services": run(c, "systemctl list-units --state=running --type=service --no-pager 2>/dev/null | head -25"),
    }
    c.close()
    return facts


def probe_sv08(jump: paramiko.SSHClient) -> dict:
    print()
    print("=" * 60)
    print(f"PROBING SV08 ({SV08_IP}) — currently running bcse-intro")
    print("=" * 60)

    c = vps_client(jump, SV08_IP)
    if not c:
        return {"reachable": False}

    facts = {
        "reachable": True,
        "hostname": run(c, "hostname"),
        "running_containers": run(c, "docker ps --format '{{.Names}} {{.Image}} {{.Ports}}' 2>/dev/null"),
        "nginx_running": run(c, "systemctl is-active nginx 2>/dev/null || echo NOT_RUNNING"),
        "nginx_sites": run(c, "ls /etc/nginx/sites-enabled/ 2>/dev/null"),
        "listening_80": run(c, "ss -tlnp | grep ':80 ' || echo PORT_80_FREE"),
        "listening_443": run(c, "ss -tlnp | grep ':443 ' || echo PORT_443_FREE"),
        "pm2_list": run(c, "pm2 list 2>/dev/null || echo NO_PM2"),
        "opt_dirs": run(c, "ls /opt/ 2>/dev/null"),
        "cloudflared": run(c, "systemctl is-active cloudflared 2>/dev/null || echo NOT_LOCAL"),
    }
    c.close()
    return facts


def main() -> int:
    j = jump_client()
    try:
        sv14 = probe_sv14(j)
        print()
        for k, v in sv14.items():
            print(f"  {k}: {v}")

        sv08 = probe_sv08(j)
        print()
        for k, v in sv08.items():
            print(f"  {k}: {v}")
    finally:
        j.close()

    print()
    print("=" * 60)
    print("DIAGNOSIS")
    print("=" * 60)
    if not sv14.get("reachable"):
        print("  [BLOCKER] SV14 not reachable — must create VM114 on Proxmox first.")
    else:
        print("  [OK] SV14 reachable. Ready for deploy.")

    if sv08.get("reachable"):
        listening = sv08.get("listening_80", "")
        if "PORT_80_FREE" not in listening:
            print(f"  [WARN] SV08 port 80 in use: {listening}")
            print("         → need to merge Caddyfile with existing bcse-intro routing,")
            print("           or use a different port (e.g., 8080) and update CF Tunnel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
