#!/bin/bash
# KV260 network recovery — run ON the device via console (monitor + keyboard).
#
# Fixes the fallout from migrate_kv260_ip.py disabling NetworkManager:
# restores DHCP networking so the board rejoins the LAN. After all 5 boards
# are back, pin their addresses with DHCP reservations on the router.
#
# Login locally as ubuntu00X / abc135, then:
#   sudo bash recover_kv260_network.sh
# (or just type the commands below by hand)

set -x

# 1. Re-enable the network manager that the migration disabled.
systemctl enable --now NetworkManager

# 2. Hand eth0 back to NetworkManager with DHCP via netplan.
cat > /etc/netplan/50-cloud-init.yaml <<'EOF'
network:
  version: 2
  renderer: NetworkManager
  ethernets:
    eth0:
      dhcp4: true
EOF
chmod 600 /etc/netplan/50-cloud-init.yaml

# 3. Remove the networkd eth0 drop-ins entirely — with renderer:NetworkManager
#    above, NM owns eth0 and any /etc/systemd/network/10-eth0.network* file
#    only causes a DHCP-vs-static fight.
rm -f /etc/systemd/network/10-eth0.network /etc/systemd/network/10-eth0.network.bcse-bak.*

# 4. Drop the cloud-init network-disable override so cloud-init behaves normally.
rm -f /etc/cloud/cloud.cfg.d/99-bcse-disable-net.cfg

# 5. Apply.
netplan apply
systemctl restart NetworkManager

sleep 5
echo "=== eth0 now ==="
ip -br addr show eth0
echo "=== MAC (give this to the router for the DHCP reservation) ==="
cat /sys/class/net/eth0/address
