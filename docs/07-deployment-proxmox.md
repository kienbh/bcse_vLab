# 07 — Deployment trên Proxmox

## Tổng quan

Khác với deployment cloud truyền thống (1 VPS lớn cài hết), kiến trúc này chia thành **5 LXC containers** trên Proxmox host. Lý do:
- Mỗi service backup snapshot riêng được
- Restart 1 service không downtime cả hệ thống
- Resource isolation tốt hơn
- Migration giữa Proxmox node dễ (nếu có cluster)

## Yêu cầu Proxmox host

- Proxmox VE 8.x
- Storage pool đủ ~150GB (LXC + backup)
- 16GB+ RAM (cho 5 LXC + Proxmox overhead)
- 2 network bridge:
  - `vmbr0`: nối ra LAN chính (uplink Internet)
  - `vmbr1`: internal cho LXC nội bộ
- LXC template Ubuntu 22.04 đã download

```bash
# Trên Proxmox host, download template
pveam update
pveam available | grep ubuntu-22
pveam download local ubuntu-22.04-standard_22.04-1_amd64.tar.zst
```

## Cấu hình LXC chi tiết

### LXC 100: lab-proxy

```bash
pct create 100 local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst \
  --hostname lab-proxy \
  --cores 1 \
  --memory 1024 \
  --rootfs local-lvm:10 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp,firewall=1 \
  --net1 name=eth1,bridge=vmbr1,ip=10.10.10.10/24 \
  --features nesting=1 \
  --unprivileged 1 \
  --onboot 1 \
  --start 1 \
  --ssh-public-keys ~/.ssh/authorized_keys
```

### LXC 101: lab-app

```bash
pct create 101 local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst \
  --hostname lab-app \
  --cores 4 \
  --memory 4096 \
  --rootfs local-lvm:40 \
  --net0 name=eth0,bridge=vmbr1,ip=10.10.10.20/24,gw=10.10.10.1 \
  --features nesting=1 \
  --unprivileged 1 \
  --onboot 1 \
  --start 1 \
  --ssh-public-keys ~/.ssh/authorized_keys
```

> **Lưu ý**: Cần `--features nesting=1` để chạy Docker bên trong LXC.

### LXC 102: lab-db

```bash
pct create 102 local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst \
  --hostname lab-db \
  --cores 2 \
  --memory 4096 \
  --rootfs local-lvm:60 \
  --net0 name=eth0,bridge=vmbr1,ip=10.10.10.30/24,gw=10.10.10.1 \
  --features nesting=1 \
  --unprivileged 1 \
  --onboot 1 \
  --start 1 \
  --ssh-public-keys ~/.ssh/authorized_keys
```

### LXC 103: lab-auth

```bash
pct create 103 local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst \
  --hostname lab-auth \
  --cores 2 \
  --memory 2048 \
  --rootfs local-lvm:20 \
  --net0 name=eth0,bridge=vmbr1,ip=10.10.10.40/24,gw=10.10.10.1 \
  --features nesting=1 \
  --unprivileged 1 \
  --onboot 1 \
  --start 1 \
  --ssh-public-keys ~/.ssh/authorized_keys
```

### LXC 104: lab-monitor

```bash
pct create 104 local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst \
  --hostname lab-monitor \
  --cores 1 \
  --memory 1024 \
  --rootfs local-lvm:20 \
  --net0 name=eth0,bridge=vmbr1,ip=10.10.10.50/24,gw=10.10.10.1 \
  --features nesting=1 \
  --unprivileged 1 \
  --onboot 1 \
  --start 1 \
  --ssh-public-keys ~/.ssh/authorized_keys
```

## Script auto-provision

`infrastructure/proxmox/create-lxc.sh`:

```bash
#!/bin/bash
# Tự động tạo 5 LXC trên Proxmox host
# Chạy trên Proxmox host: bash create-lxc.sh
set -euo pipefail

TEMPLATE="local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst"
SSH_KEY_FILE="${1:-/root/.ssh/authorized_keys}"

declare -A LXCS=(
  ["100|lab-proxy|1|1024|10|10.10.10.10"]="vmbr0"
  ["101|lab-app|4|4096|40|10.10.10.20"]="vmbr1-only"
  ["102|lab-db|2|4096|60|10.10.10.30"]="vmbr1-only"
  ["103|lab-auth|2|2048|20|10.10.10.40"]="vmbr1-only"
  ["104|lab-monitor|1|1024|20|10.10.10.50"]="vmbr1-only"
)

for KEY in "${!LXCS[@]}"; do
  IFS='|' read -r ID NAME CORES MEM DISK IP <<< "$KEY"
  TYPE="${LXCS[$KEY]}"
  
  echo ">>> Creating LXC $ID ($NAME)..."
  
  if [ "$TYPE" = "vmbr0" ]; then
    pct create $ID $TEMPLATE \
      --hostname $NAME \
      --cores $CORES --memory $MEM \
      --rootfs local-lvm:$DISK \
      --net0 name=eth0,bridge=vmbr0,ip=dhcp,firewall=1 \
      --net1 name=eth1,bridge=vmbr1,ip=$IP/24 \
      --features nesting=1 \
      --unprivileged 1 \
      --onboot 1 \
      --start 1 \
      --ssh-public-keys $SSH_KEY_FILE
  else
    pct create $ID $TEMPLATE \
      --hostname $NAME \
      --cores $CORES --memory $MEM \
      --rootfs local-lvm:$DISK \
      --net0 name=eth0,bridge=vmbr1,ip=$IP/24,gw=10.10.10.1 \
      --features nesting=1 \
      --unprivileged 1 \
      --onboot 1 \
      --start 1 \
      --ssh-public-keys $SSH_KEY_FILE
  fi
  
  echo "    LXC $ID ($NAME) created at $IP"
  sleep 2
done

echo ""
echo "Done. Verify với: pct list"
echo "SSH vào: ssh root@<ip>"
```

## Network setup trên Proxmox host

### Cấu hình `vmbr1` internal bridge

`/etc/network/interfaces` thêm:

```ini
auto vmbr1
iface vmbr1 inet static
    address 10.10.10.1/24
    bridge-ports none
    bridge-stp off
    bridge-fd 0
    # NAT để LXC ra Internet được (qua proxmox host)
    post-up echo 1 > /proc/sys/net/ipv4/ip_forward
    post-up iptables -t nat -A POSTROUTING -s 10.10.10.0/24 -o vmbr0 -j MASQUERADE
    post-down iptables -t nat -D POSTROUTING -s 10.10.10.0/24 -o vmbr0 -j MASQUERADE
```

`systemctl restart networking`

### Port forward Internet → lab-proxy

```bash
# Forward 80/443 từ Proxmox public IP → lab-proxy (10.10.10.10)
iptables -t nat -A PREROUTING -i vmbr0 -p tcp --dport 80 -j DNAT --to 10.10.10.10:80
iptables -t nat -A PREROUTING -i vmbr0 -p tcp --dport 443 -j DNAT --to 10.10.10.10:443
iptables -A FORWARD -i vmbr0 -o vmbr1 -p tcp --dport 80 -d 10.10.10.10 -j ACCEPT
iptables -A FORWARD -i vmbr0 -o vmbr1 -p tcp --dport 443 -d 10.10.10.10 -j ACCEPT

# Persist
iptables-save > /etc/iptables/rules.v4
```

## Cài Docker trong từng LXC

Sau khi LXC up, SSH vào và chạy:

```bash
# Trong LXC lab-app, lab-db, lab-auth, lab-monitor, lab-proxy
ssh root@10.10.10.20  # hoặc 10/30/40/50

apt update && apt upgrade -y
apt install -y curl wget git ca-certificates

# Docker
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

# Verify
docker --version
docker compose version
```

## Ansible playbook (recommended)

Thay vì SSH vào từng LXC, dùng Ansible. Tạo `infrastructure/proxmox/ansible/inventory.yaml`:

```yaml
all:
  children:
    proxy:
      hosts:
        lab-proxy:
          ansible_host: 10.10.10.10
    app:
      hosts:
        lab-app:
          ansible_host: 10.10.10.20
    db:
      hosts:
        lab-db:
          ansible_host: 10.10.10.30
    auth:
      hosts:
        lab-auth:
          ansible_host: 10.10.10.40
    monitor:
      hosts:
        lab-monitor:
          ansible_host: 10.10.10.50
  vars:
    ansible_user: root
    ansible_ssh_private_key_file: ~/.ssh/id_ed25519
```

Playbook `setup-base.yaml`:

```yaml
- name: Base setup all LXC
  hosts: all
  tasks:
    - name: Update apt
      apt: update_cache=yes upgrade=dist
    
    - name: Install base packages
      apt:
        name:
          - curl
          - git
          - vim
          - htop
          - ufw
          - python3-pip
        state: present
    
    - name: Install Docker
      shell: curl -fsSL https://get.docker.com | sh
      args:
        creates: /usr/bin/docker
    
    - name: Enable Docker
      systemd:
        name: docker
        state: started
        enabled: yes
```

Chạy: `ansible-playbook -i inventory.yaml setup-base.yaml`

## Deploy app vào LXC

Mỗi LXC có cấu trúc `/opt/lab-portal/`:

### `lab-proxy`: chỉ cần Caddy

`/opt/lab-portal/docker-compose.yml`:

```yaml
services:
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy-data:/data

volumes:
  caddy-data:
```

`/opt/lab-portal/Caddyfile`:

```
{$DOMAIN} {
    encode gzip

    @api path /api/*
    handle @api {
        reverse_proxy 10.10.10.20:8000
    }

    @auth path /auth/*
    handle @auth {
        reverse_proxy 10.10.10.40:9000
    }

    @term path /term/*
    handle @term {
        reverse_proxy 10.10.10.20:3001
    }

    handle {
        reverse_proxy 10.10.10.20:3000
    }

    log {
        output file /data/access.log
    }
}
```

### `lab-app`: frontend + backend + wetty + worker

```yaml
services:
  frontend:
    image: ghcr.io/vju/lab-portal-frontend:${TAG:-latest}
    restart: unless-stopped
    environment:
      NEXT_PUBLIC_API_URL: https://${DOMAIN}/api
      NEXT_PUBLIC_AUTH_URL: https://${DOMAIN}/auth
    ports:
      - "10.10.10.20:3000:3000"

  backend:
    image: ghcr.io/vju/lab-portal-backend:${TAG:-latest}
    restart: unless-stopped
    env_file: .env
    ports:
      - "10.10.10.20:8000:8000"
    volumes:
      - ./ssh-keys:/app/ssh-keys:ro

  worker:
    image: ghcr.io/vju/lab-portal-backend:${TAG:-latest}
    restart: unless-stopped
    command: rq worker default
    env_file: .env

  wetty:
    image: wettyoss/wetty:latest
    restart: unless-stopped
    command: --base /term/ --port 3000
    ports:
      - "10.10.10.20:3001:3000"
```

### `lab-db`: postgres + redis

```yaml
services:
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - ./postgres-data:/var/lib/postgresql/data
    ports:
      - "10.10.10.30:5432:5432"

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --requirepass ${REDIS_PASSWORD}
    volumes:
      - ./redis-data:/data
    ports:
      - "10.10.10.30:6379:6379"
```

### `lab-auth`: authentik

(xem docs Authentik chính thức cho compose file đầy đủ)

```yaml
services:
  server:
    image: ghcr.io/goauthentik/server:2024.10
    restart: unless-stopped
    command: server
    environment:
      AUTHENTIK_REDIS__HOST: 10.10.10.30
      AUTHENTIK_REDIS__PASSWORD: ${REDIS_PASSWORD}
      AUTHENTIK_POSTGRESQL__HOST: 10.10.10.30
      AUTHENTIK_POSTGRESQL__USER: ${AUTHENTIK_DB_USER}
      AUTHENTIK_POSTGRESQL__NAME: ${AUTHENTIK_DB_NAME}
      AUTHENTIK_POSTGRESQL__PASSWORD: ${AUTHENTIK_DB_PASSWORD}
      AUTHENTIK_SECRET_KEY: ${AUTHENTIK_SECRET_KEY}
    ports:
      - "10.10.10.40:9000:9000"
    volumes:
      - ./authentik-data:/media

  worker:
    image: ghcr.io/goauthentik/server:2024.10
    restart: unless-stopped
    command: worker
    environment:
      # same as server
      AUTHENTIK_REDIS__HOST: 10.10.10.30
      AUTHENTIK_REDIS__PASSWORD: ${REDIS_PASSWORD}
      AUTHENTIK_POSTGRESQL__HOST: 10.10.10.30
      AUTHENTIK_POSTGRESQL__USER: ${AUTHENTIK_DB_USER}
      AUTHENTIK_POSTGRESQL__NAME: ${AUTHENTIK_DB_NAME}
      AUTHENTIK_POSTGRESQL__PASSWORD: ${AUTHENTIK_DB_PASSWORD}
      AUTHENTIK_SECRET_KEY: ${AUTHENTIK_SECRET_KEY}
    volumes:
      - ./authentik-data:/media
```

### `lab-monitor`: uptime kuma

```yaml
services:
  uptime-kuma:
    image: louislam/uptime-kuma:1
    restart: unless-stopped
    ports:
      - "10.10.10.50:3001:3001"
    volumes:
      - ./kuma-data:/app/data
```

## Deploy procedure

### Lần đầu

```bash
# 1. SSH vào Proxmox host, tạo 5 LXC
ssh root@<proxmox-public-ip>
cd /root
git clone <repo> vju-lab-portal
cd vju-lab-portal
bash infrastructure/proxmox/create-lxc.sh

# 2. Setup base trong các LXC (Ansible)
cd infrastructure/proxmox/ansible
ansible-playbook -i inventory.yaml setup-base.yaml

# 3. Deploy code vào các LXC
ansible-playbook -i inventory.yaml deploy-app.yaml

# 4. Run migrations
ssh root@10.10.10.20
cd /opt/lab-portal
docker compose exec backend alembic upgrade head

# 5. Seed admin
docker compose exec backend python -m app.scripts.seed_admin

# 6. Verify
curl https://lab.vju.edu.vn/health
```

### Update code

```bash
# Build + push images
git tag v1.0.1
git push --tags
# CI tự build images với tag

# Deploy
ssh root@10.10.10.20
cd /opt/lab-portal
TAG=v1.0.1 docker compose pull
docker compose run --rm backend alembic upgrade head
TAG=v1.0.1 docker compose up -d
```

## Backup chiến lược

### Backup Database
```bash
# Cron trên lab-db (3h sáng hàng ngày)
0 3 * * * /opt/lab-portal/scripts/backup-db.sh
```

`backup-db.sh`:
```bash
#!/bin/bash
DATE=$(date +%Y%m%d-%H%M%S)
docker compose exec -T postgres pg_dump -U $POSTGRES_USER $POSTGRES_DB | \
    gzip > /backups/labportal-$DATE.sql.gz
find /backups -name "labportal-*.sql.gz" -mtime +30 -delete
```

### Proxmox snapshot

```bash
# Snapshot weekly (chạy trên Proxmox host)
0 4 * * 0 vzdump 100 101 102 103 104 \
    --storage backup-storage \
    --mode snapshot \
    --compress zstd \
    --maxfiles 4
```

### Off-site backup (recommended)
- rsync `/var/lib/vz/dump/` → external storage
- Hoặc upload S3-compatible (minio, wasabi, b2)

## Monitoring

### Trên Proxmox host
- Built-in monitoring (CPU, RAM, disk per LXC)
- Email alert khi container down

### Trên `lab-monitor`
- Uptime Kuma monitor:
  - HTTPS check `https://lab.vju.edu.vn`
  - Mỗi LXC TCP check
  - Mỗi device pool ping
  - Mỗi smart plug HTTP check
  - PostgreSQL health qua backend `/api/health/db`

## Troubleshooting playbook

### Frontend trả 502
- `pct enter 100` → check Caddy log: `docker compose logs caddy`
- `pct enter 101` → check frontend: `docker compose ps`
- Restart: `docker compose restart frontend`

### Backend 500 errors
- `pct enter 101` → `docker compose logs backend --tail=100`
- Check DB: `pct enter 102` → `docker compose exec postgres psql -U labportal`

### LXC không start
- `pct status 100`
- `pct unlock 100` nếu bị lock
- Check disk: `pvesm status`

### SSH provision fails (M4)
- LXC `lab-app` ping được device không? `pct enter 101` → `ping 192.168.20.103`
- Network bridge config đúng? `ip addr` trong LXC
- Firewall rule? `iptables -L`

### DB chậm
- `pct enter 102` → `docker compose exec postgres psql -U labportal`
- `EXPLAIN ANALYZE` query nghi ngờ
- Vacuum: `VACUUM ANALYZE;`
- Tăng RAM cho LXC: `pct set 102 --memory 8192`
