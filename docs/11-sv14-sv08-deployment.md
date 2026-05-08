# Triển khai SV14 + SV08 (deployment variant — ADR-0011)

Tài liệu này tóm tắt cách deploy VJU Hardware Lab Portal **trên hệ sinh thái BCSE-VJU**
(Proxmox VPS pool + Cloudflare Tunnel) thay vì kịch bản gốc trong `07-deployment-proxmox.md`
(Proxmox host duy nhất + DNAT public IP).

> Đọc trước: `decisions.md` — ADR-0011, ADR-0004 (gốc).

## Topology

```
Internet
  │
  ▼
Cloudflare DNS (sv14.bcse-vju.com → tunnel <tunnel-id>.cfargotunnel.com)
  │
  ▼
Cloudflare Tunnel `proxmox-vms-v2` (chạy trên jump host 123.16.53.250)
  │  rule: sv14.bcse-vju.com → http://192.168.2.108:80
  ▼
SV08 (192.168.2.108) — nginx (đã có, host bcse-intro/bcse-id, thêm 1 vhost mới)
  │  /etc/nginx/sites-enabled/sv14-lab-portal
  │  proxy_pass → 192.168.2.114:{3000,8000,9000,3001}
  ▼
SV14 (192.168.2.114) — Docker Compose stack
  ├── frontend (Next.js 14)             :3000
  ├── backend  (FastAPI 0.110)          :8000
  ├── worker   (RQ scheduler)           internal
  ├── wetty    (web SSH terminal)       :3001
  ├── postgres (16-alpine)              internal
  ├── redis    (7-alpine, passworded)   internal
  ├── authentik-db                      internal
  ├── authentik (OIDC server)           :9000
  └── authentik-worker                  internal
  │
  ▼
Device pool 192.168.20.0/24 + Plug pool 192.168.30.0/24
  (chưa có route từ SV14 → cần WireGuard back-haul khi devices online — ADR-0012 sẽ raise)
```

## Components & roles

| Component | Host | Purpose |
|---|---|---|
| CF DNS CNAME `sv14` | Cloudflare zone bcse-vju.com | Resolve sv14.bcse-vju.com to tunnel |
| CF Tunnel `proxmox-vms-v2` | Jump host 123.16.53.250 | Public ingress (TLS terminated) |
| SV08 nginx vhost | 192.168.2.108 :80 | Reverse proxy, header injection, SSE/WS |
| SV14 Docker stack | 192.168.2.114 | Frontend + Backend + DB + Auth + worker |
| UFW on SV14 | 192.168.2.114 | Allow SV08 (192.168.2.108) only on app ports |
| Backups | SV14 cron `pg_dump` 03:00 daily | 30-day retention |

## Files

```
infrastructure/
├── sv14/
│   ├── docker-compose.prod.yml      # 8 services
│   ├── .env.prod.example            # placeholders, secrets generated on first deploy
│   ├── postgres/init-extensions.sql # uuid-ossp, btree_gist
│   ├── setup-sv14.sh                # idempotent: docker, ufw, swap, dirs
│   └── backup.sh                    # daily pg_dump cron
└── sv08-ingress/
    ├── nginx-sv14-vhost.conf        # /etc/nginx/sites-available/sv14-lab-portal
    └── nginx-upgrade-map.conf       # WS connection_upgrade map (one-time)
scripts/
├── deploy_lab_portal.py             # main deploy orchestrator (paramiko)
├── cf_dns_sv14.py                   # standalone CF DNS upsert
├── verify_sv14.py                   # state check on SV14
├── peek_sv14.py                     # mid-deploy diagnostic
├── probe_sv14_sv08.py               # initial reachability probe
└── smoke_test_sv14.py               # final HTTPS smoke test
```

## Run book

### Prerequisites
- Python 3.11+ + `pip install paramiko` on dev machine
- Access to BCSE jump host (creds baked in scripts; `.gitignore` keeps them out of git on commit)
- SV14 VPS exists (verify with `python scripts/probe_sv14_sv08.py`)

### First-time deploy

```bash
# 1. Update DNS + Tunnel (idempotent)
python scripts/deploy_lab_portal.py --skip-sv08 --skip-sv14 --skip-build

# 2. Setup SV14 base (Docker, UFW, swap)
python scripts/deploy_lab_portal.py --skip-cf --skip-sv08 --skip-build

# 3. Build + deploy app stack on SV14 (~10-15 min first time)
python scripts/deploy_lab_portal.py --skip-cf --skip-sv08 --skip-setup

# 4. Install nginx vhost on SV08
python scripts/deploy_lab_portal.py --skip-cf --skip-sv14

# 5. Smoke test
python scripts/deploy_lab_portal.py --smoke-only
```

### Subsequent deploys (code changes only)

```bash
python scripts/deploy_lab_portal.py --skip-cf --skip-setup --skip-sv08
# add --skip-build to only restart containers without rebuild
```

### Just CF Tunnel rule

```bash
python scripts/deploy_lab_portal.py --skip-sv14 --skip-sv08 --skip-build
```

## Differences from gốc design (07-deployment-proxmox.md)

| Original (ADR-0004) | This deployment (ADR-0011) |
|---|---|
| 5 LXC trên 1 Proxmox host | 1 VPS chạy Docker Compose tất cả |
| Proxmox public IP DNAT | Cloudflare Tunnel + SV08 nginx |
| Caddy auto-LE TLS | Cloudflare edge TLS |
| Internal subnet 10.10.10.0/24 | Existing 192.168.2.0/24 LAN |
| `pct create`, `vzdump` | Docker compose + VPS snapshot |
| Backend → device pool same-LAN | TODO: WireGuard tunnel (M4) |

## Open issues / follow-ups

1. **Device pool reachability**: SV14 ip-route chỉ có `192.168.2.0/24` + default gateway. Không thấy `192.168.20.x` / `192.168.30.x`. Khi pilot devices physical online (M4), cần WireGuard tunnel SV14 ↔ Hòa Lạc gateway. Raise ADR-0012.
2. **Authentik bootstrap**: `.env.prod` được auto-generate password lần đầu, nhưng OIDC client setup trong Authentik UI vẫn cần làm thủ công ở M1.
3. **Disk space**: SV14 chỉ 19GB. Sau khi build images còn ~5GB. Khi user bắt đầu upload `.bit` files (M6) cần resize VM hoặc gắn block storage.
4. **OIDC redirect URI** trong Authentik phải set chính xác `https://sv14.bcse-vju.com/api/auth/callback`.
5. **wetty TLS**: wetty chạy HTTP, TLS terminate ở CF edge. Đảm bảo CF "Full (strict)" KHÔNG bật cho subdomain này nếu không có cert nội bộ — dùng "Flexible" hoặc "Full" thường.

## Rollback

Cấp 1 — code rollback (an toàn nhất):
```bash
ssh student@192.168.2.114
cd /opt/vju-lab-portal
git ... # nếu có git, hoặc manually re-upload tar trước
docker compose -f infrastructure/sv14/docker-compose.prod.yml up -d
```

Cấp 2 — gỡ ingress:
```bash
# Tạm bỏ vhost SV08
ssh student@192.168.2.108
sudo rm /etc/nginx/sites-enabled/sv14-lab-portal
sudo systemctl reload nginx
```

Cấp 3 — gỡ DNS:
```bash
python scripts/cf_dns_sv14.py --delete
```

Cấp 4 — gỡ Tunnel rule: edit Cloudflare Zero Trust → Tunnel `proxmox-vms-v2` → ingress → remove `sv14.bcse-vju.com`.
