#!/usr/bin/env bash
# One-time SV14 setup for the SSH ProxyJump gateway pattern.
#
# After this script runs, the backend container can create per-session
# Linux users (`sess-<id>`) on SV14 via constrained sudo. Those users are
# locked to ForceCommand=/usr/sbin/nologin and can only TCP-forward to the
# explicitly-permitted KIT IPs (PermitOpen below).
#
# Run as root on SV14:
#     sudo bash setup-jump-host.sh
#
# Idempotent — safe to re-run if PermitOpen list changes.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Must run as root" >&2
    exit 1
fi

log() { echo "[setup-jump-host] $*"; }

# 1. Group used by sshd Match block ----------------------------------------
log "1/4 — ensure vjujump group exists"
getent group vjujump >/dev/null 2>&1 || groupadd vjujump

# 2. Constrained sudoers for the `student` user --------------------------
# The backend container ssh-es to SV14 as `student` using portal_admin
# key and needs to create/delete dynamic users. Restrict sudo to ONLY
# the exact commands we need — no shell-escape, no arbitrary uid.
log "2/4 — install /etc/sudoers.d/vju-jump"
cat > /etc/sudoers.d/vju-jump.tmp <<'EOF'
# Backend (student) — create/delete per-session jump users.
# Constrained: name must match sess-* and the exact arg-list shape.
student ALL=(root) NOPASSWD: /usr/sbin/useradd -m -s /usr/sbin/nologin -G vjujump sess-*
student ALL=(root) NOPASSWD: /usr/sbin/userdel -r sess-*
student ALL=(root) NOPASSWD: /usr/bin/install -d -m 700 -o sess-* -g sess-* /home/sess-*/.ssh
student ALL=(root) NOPASSWD: /usr/bin/tee /home/sess-*/.ssh/authorized_keys
student ALL=(root) NOPASSWD: /usr/bin/chmod 600 /home/sess-*/.ssh/authorized_keys
student ALL=(root) NOPASSWD: /usr/bin/chown sess-*\:sess-* /home/sess-*/.ssh/authorized_keys
EOF
# Validate before installing
visudo -cf /etc/sudoers.d/vju-jump.tmp
chmod 440 /etc/sudoers.d/vju-jump.tmp
mv /etc/sudoers.d/vju-jump.tmp /etc/sudoers.d/vju-jump

# 3. sshd Match block — restrict all sess-* group members to TCP-forward only
log "3/4 — install /etc/ssh/sshd_config.d/99-vju-jump.conf"
cat > /etc/ssh/sshd_config.d/99-vju-jump.conf <<'EOF'
# VJU Lab Portal — dynamic per-session jump users.
# Every user in `vjujump` group is restricted to TCP forwarding only.
# Hard-coded PermitOpen for current KIT pool — will be templated from DB
# in M5.7+ when the pool grows beyond 3 boards.
Match Group vjujump
    AllowTcpForwarding yes
    GatewayPorts no
    X11Forwarding no
    AllowAgentForwarding no
    PermitTTY no
    ForceCommand /usr/sbin/nologin
    PermitOpen 192.168.2.93:22 192.168.2.100:22 192.168.2.121:22
EOF

# 4. Validate + reload sshd ------------------------------------------------
# Ubuntu 24.04 calls the unit `ssh.service` (older releases used `sshd`).
log "4/4 — sshd -t && reload ssh"
sshd -t
if systemctl reload ssh 2>/dev/null; then
    log "  reloaded ssh.service"
elif systemctl reload sshd 2>/dev/null; then
    log "  reloaded sshd.service"
else
    log "  WARNING — couldn't reload via systemctl; check the unit name manually"
fi

log "DONE."
log ""
log "Next: backend container will ssh student@192.168.2.114 and run:"
log "  sudo useradd -m -s /usr/sbin/nologin -G vjujump sess-<id>"
log "  sudo install -d -m 700 -o sess-<id> -g sess-<id> /home/sess-<id>/.ssh"
log "  echo <pubkey> | sudo tee /home/sess-<id>/.ssh/authorized_keys"
log "  ..."
log ""
log "Verify with:"
log "  getent group vjujump"
log "  sudo sshd -T -C user=fakeuser,host=,addr= | grep -i permitopen"
