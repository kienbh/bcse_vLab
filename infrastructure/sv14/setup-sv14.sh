#!/usr/bin/env bash
# Idempotent first-time setup for SV14 (Ubuntu 22.04 LTS LXC/VM).
# Run as root via: ssh root@192.168.2.114 'bash -s' < setup-sv14.sh
set -euo pipefail

log() { echo "[setup-sv14] $*"; }

log "1/6 — apt update + base packages"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    curl ca-certificates gnupg lsb-release \
    git build-essential ufw fail2ban \
    rsync postgresql-client tzdata jq

# Add 4 GB swap if missing — SV14 has only 4 GB RAM, builds will OOM otherwise
if ! swapon --show | grep -q '/swapfile'; then
    log "  + creating /swapfile (4 GB)"
    fallocate -l 4G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

log "2/6 — timezone Asia/Ho_Chi_Minh"
ln -sf /usr/share/zoneinfo/Asia/Ho_Chi_Minh /etc/localtime
echo "Asia/Ho_Chi_Minh" > /etc/timezone

log "3/6 — Docker engine + compose plugin"
if ! command -v docker >/dev/null 2>&1; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
fi
docker --version
docker compose version

log "4/6 — UFW firewall — allow SSH from LAN, frontend/backend/auth/wetty from SV08 only"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow from 192.168.2.0/24 to any port 22 proto tcp comment 'SSH (LAN only)'
ufw allow from 192.168.2.108 to any port 3000 proto tcp comment 'Frontend (SV08 ingress)'
ufw allow from 192.168.2.108 to any port 8000 proto tcp comment 'Backend API (SV08 ingress)'
ufw allow from 192.168.2.108 to any port 9000 proto tcp comment 'Authentik (SV08 ingress)'
ufw allow from 192.168.2.108 to any port 3001 proto tcp comment 'wetty (SV08 ingress)'
ufw --force enable

log "5/6 — fail2ban for SSH"
systemctl enable --now fail2ban

log "6/6 — app dirs + docker group"
mkdir -p /opt/vju-lab-portal/postgres-backup
chown -R student:student /opt/vju-lab-portal
# Allow student to use docker without sudo
usermod -aG docker student || true

log "DONE. Next steps:"
log "  1. Upload tar.gz of project to /opt/vju-lab-portal"
log "  2. cd /opt/vju-lab-portal/infrastructure/sv14 && cp .env.prod.example .env.prod && edit"
log "  3. docker compose -f docker-compose.prod.yml --env-file .env.prod up -d"
