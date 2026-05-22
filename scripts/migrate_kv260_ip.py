"""DEPRECATED / DANGEROUS — do not use without fixing first.

Migrate a KV260's IP from DHCP to a static address via netplan.

!!! 2026-05-22: This script broke networking on all 5 KV260s after a reboot.
It runs `systemctl disable --now NetworkManager`; on the Kria image that
left eth0 with no working network manager once the boards power-cycled, so
they came back with no IP at all. The static `netplan apply` works LIVE but
does not survive a cold boot on this image.

Preferred approach now: keep the devices on DHCP and pin their addresses
with DHCP reservations on the router (MAC -> IP). No device-side change,
nothing to break on reboot.

If you ever do need device-side static IP, this script must first:
  * NOT disable NetworkManager unless systemd-networkd is explicitly
    `systemctl enable`d for boot, and
  * be tested across a full reboot on ONE device before touching the fleet.

Usage (only after the above is fixed):
    python scripts/migrate_kv260_ip.py <old_ip> <user> <new_ip> [--sudo-pass abc135]
"""
from __future__ import annotations

import argparse
import io
import socket
import sys
import time
from pathlib import Path

import paramiko

REPO = Path(__file__).resolve().parents[1]
PRIV = REPO / "infrastructure" / "sv14" / "secrets" / "portal_admin_ed25519"

NETPLAN_TEMPLATE = """network:
  version: 2
  ethernets:
    eth0:
      dhcp4: no
      addresses: [{ip}/{cidr}]
      routes:
        - to: default
          via: {gateway}
      nameservers:
        addresses: [{dns}]
"""

APPLY_SCRIPT = r"""#!/bin/bash
set -e
exec >/var/log/ip_migrate.log 2>&1
echo "[$(date -Iseconds)] migrate -> {NEW_IP}"
sleep 5
# Backup current cloud-init netplan
if [ -f /etc/netplan/50-cloud-init.yaml ]; then
  cp /etc/netplan/50-cloud-init.yaml /tmp/50-cloud-init.yaml.bak.$(date +%s)
fi
# Disable cloud-init network regen (otherwise next reboot may revert)
echo "network: {{config: disabled}}" > /etc/cloud/cloud.cfg.d/99-bcse-disable-net.cfg
# Install new static config (replaces cloud-init's file)
cp /tmp/bcse-netplan.yaml /etc/netplan/50-cloud-init.yaml
chmod 600 /etc/netplan/50-cloud-init.yaml
# Kria image ships a hand-rolled /etc/systemd/network/10-eth0.network with
# DHCP=yes — that file lives in /etc/ which beats netplan's /run/ output.
# Move it aside so our static config in /etc/netplan/ actually takes effect.
if [ -f /etc/systemd/network/10-eth0.network ]; then
  mv /etc/systemd/network/10-eth0.network /etc/systemd/network/10-eth0.network.bcse-bak.$(date +%s)
fi
# Stop NetworkManager so it does not fight systemd-networkd over eth0.
systemctl disable --now NetworkManager 2>&1 || true
echo "[$(date -Iseconds)] applying"
netplan apply
echo "[$(date -Iseconds)] DONE"
"""


def connect_key(ip: str, user: str) -> paramiko.SSHClient:
    k = paramiko.Ed25519Key.from_private_key(io.StringIO(PRIV.read_text()))
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(ip, username=user, pkey=k, timeout=15,
              allow_agent=False, look_for_keys=False)
    return c


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("old_ip")
    ap.add_argument("user")
    ap.add_argument("new_ip")
    ap.add_argument("--cidr", type=int, default=24)
    ap.add_argument("--gateway", default="192.168.2.1")
    ap.add_argument("--dns", default="8.8.8.8")
    ap.add_argument("--sudo-pass", dest="sudo_password", default="abc135")
    a = ap.parse_args()

    try:
        socket.create_connection((a.old_ip, 22), timeout=6).close()
    except OSError as e:
        print(f"[mig] {a.old_ip}: unreachable ({e})")
        return 2

    print(f"[mig] {a.old_ip} -> {a.new_ip} as {a.user}")
    c = connect_key(a.old_ip, a.user)

    netplan = NETPLAN_TEMPLATE.format(ip=a.new_ip, cidr=a.cidr, gateway=a.gateway, dns=a.dns)
    apply = APPLY_SCRIPT.replace("{NEW_IP}", a.new_ip)

    sftp = c.open_sftp()
    with sftp.open("/tmp/bcse-netplan.yaml", "w") as f:
        f.write(netplan)
    with sftp.open("/tmp/ip_migrate.sh", "w") as f:
        f.write(apply)
    sftp.chmod("/tmp/ip_migrate.sh", 0o755)
    sftp.close()
    print(f"[mig] {a.old_ip}: netplan + apply script uploaded")

    unit = f"ip-migrate-{a.old_ip.replace('.','-')}"
    cmd = f"systemd-run --unit={unit} /bin/bash /tmp/ip_migrate.sh"
    full = f"sudo -S -p '' {cmd}"
    i, o, e = c.exec_command(full, timeout=15)
    i.write(a.sudo_password + "\n")
    i.flush()
    try:
        out = o.read().decode(errors="replace")
        err = e.read().decode(errors="replace")
        rc = o.channel.recv_exit_status()
        print(f"[mig] {a.old_ip}: systemd-run rc={rc}")
        if out.strip(): print(f"  out: {out.strip()}")
        if err.strip(): print(f"  err: {err.strip()}")
    except Exception as ex:
        print(f"[mig] {a.old_ip}: read after systemd-run failed (expected if SSH dropped): {ex}")
    try:
        c.close()
    except Exception:
        pass

    print(f"[mig] {a.old_ip}: waiting 20s for netplan apply + new IP to come up...")
    time.sleep(20)

    print(f"[mig] {a.new_ip}: verifying key-auth")
    try:
        v = connect_key(a.new_ip, a.user)
    except Exception as ex:
        print(f"[mig] VERIFY FAILED at {a.new_ip}: {ex}")
        print(f"  on device: sudo cat /var/log/ip_migrate.log")
        return 5
    _, o, _ = v.exec_command("hostname; ip -br addr show eth0; ip route show default")
    out = o.read().decode().strip()
    v.close()
    print(f"[mig] OK at {a.new_ip}:")
    for ln in out.splitlines():
        print(f"  {ln}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
