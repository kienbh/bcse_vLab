#!/usr/bin/env bash
# Set up the Proxmox host as the SSH ProxyJump gateway for the VJU Lab Portal.
#
# The Proxmox hypervisor already has a public SSH endpoint on port 2223
# (via existing router DNAT used for admin access). We re-use that as the
# user-facing gateway — no Cloudflare tunnel, no new port forward, no
# extra client tool on the user's machine.
#
# Run as root on the Proxmox host:
#     sudo bash setup-jump-host-pve.sh
#
# Idempotent.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Must run as root" >&2
    exit 1
fi
log() { echo "[setup-jump-pve] $*"; }

# 1. Group used by sshd Match block --------------------------------------
log "1/3 — ensure vjujump group exists"
getent group vjujump >/dev/null 2>&1 || groupadd vjujump

# 2. sshd Match block — restrict sess-* users to TCP forwarding only -----
log "2/3 — install /etc/ssh/sshd_config.d/99-vju-jump.conf"
cat > /etc/ssh/sshd_config.d/99-vju-jump.conf <<'EOF'
# VJU Lab Portal — dynamic per-session jump users.
# Members of group `vjujump` can only TCP-forward to the explicit KIT pool.
Match Group vjujump
    AllowTcpForwarding yes
    GatewayPorts no
    X11Forwarding no
    AllowAgentForwarding no
    PermitTTY no
    ForceCommand /usr/sbin/nologin
    PermitOpen 192.168.2.93:22 192.168.2.100:22 192.168.2.121:22
EOF

# 3. Validate + reload sshd ----------------------------------------------
log "3/3 — sshd -t && reload"
sshd -t
if systemctl reload ssh 2>/dev/null; then
    log "  reloaded ssh.service"
elif systemctl reload sshd 2>/dev/null; then
    log "  reloaded sshd.service"
else
    log "  WARNING — couldn't reload via systemctl; check unit name manually"
fi

log "DONE."
log ""
log "Verify:"
log "  getent group vjujump"
log "  sudo useradd -m -s /usr/sbin/nologin -G vjujump sess-test"
log "  sudo sshd -T -C user=sess-test,host=,addr= | grep -i permitopen"
log "  sudo userdel -r sess-test"
