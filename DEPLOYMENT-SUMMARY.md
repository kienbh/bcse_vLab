# Deployment summary — VJU Hardware Lab Portal

**Date:** 2026-05-08
**Live at:**
- App portal: <https://sv14.bcse-vju.com>
- Auth (Authentik): <https://lab-auth.bcse-vju.com> · admin UI: <https://lab-auth.bcse-vju.com/if/admin/>
**Status:** M0 bootstrap + UI shell ✅ · M1.A auth subdomain ✅ · M1.D DB models + migration 0001 ✅ · M1.B OIDC client setup pending (manual)
**Deploy variant:** ADR-0011 (SV14 + SV08 ingress, không phải Proxmox-LAN gốc của ADR-0004)

## Trạng thái

| Endpoint | Status | Note |
|---|---|---|
| `https://sv14.bcse-vju.com/` | ✅ 200 | Next.js 14, title "VJU Hardware Lab Portal" |
| `https://sv14.bcse-vju.com/api/health` | ✅ 200 | FastAPI 0.110, env=production, version=0.1.0 |
| `https://sv14.bcse-vju.com/api/ready` | ✅ 200 | |
| `https://sv14.bcse-vju.com/auth/` | ⚠️ 404 — M1 work | Authentik chạy OK trên `:9000` nội bộ, nhưng 2024.x không hỗ trợ subpath. Cần dời sang subdomain `auth.sv14.bcse-vju.com` ở M1 |
| `https://sv14.bcse-vju.com/term/` | ⏳ chưa test | wetty container Up, route OK, chưa có session để test |
| `https://sv14.bcse-vju.com/api/docs` | 🔒 404 cố tình | Swagger disabled trong prod (security) |

### Internal verification (SSH vào SV14)
| Endpoint | Status |
|---|---|
| `http://localhost:9000/` (Authentik) | 302 → login flow ✓ |
| `http://localhost:9000/if/flow/initial-setup/` | 200 OK ✓ |
| `http://localhost:8000/api/health` | 200 OK ✓ |
| `http://localhost:3000/api/health` | 200 OK ✓ |

### Frontend pages (M0 UI shell — mock data, chưa nối backend)
| Path | Mô tả |
|---|---|
| `/` | Landing — hero + 3 step workflow + 3 device feature cards |
| `/login` | Login (placeholder Authentik OIDC button) |
| `/dashboard` | Bảng điều khiển — bookings sắp tới + quick actions + devices |
| `/devices` | Danh sách thiết bị — filter theo type + status, mock 10 thiết bị |
| `/bookings` | Lịch đặt — list view (calendar component sẽ vào M3) |

UI hỗ trợ:
- **Vietnamese ↔ English** toggle (icon Globe trên nav, lưu localStorage)
- **Light ↔ Dark** theme toggle (auto detect prefers-color-scheme, lưu localStorage)
- Responsive (mobile hamburger menu)
- Backend status indicator real-time (poll `/api/health` mỗi 30s)

## Resource limits (sau khi `kiểm soát limit`)

### SV14 budget (4 GB RAM + 4 GB swap, 19 GB disk)
| Container | mem_limit | mem_reservation | Đang dùng |
|---|---|---|---|
| postgres | 512M | 256M | ~22M |
| authentik-db | 256M | 128M | ~20M |
| redis | 128M (maxmem 96M LRU) | 64M | ~3M |
| authentik | 512M | 384M | ~38M |
| authentik-worker | 384M | 256M | ~38M |
| backend | 512M | 256M | ~108M |
| worker | 384M | 192M | ~32M |
| frontend | 512M | 256M | ~50M |
| wetty | 128M | 64M | ~60M |
| **Tổng commit** | **~3.3 GB** | ~1.9 GB | **~370 MB** |

Disk: 12 GB / 19 GB (63%) — đủ cho M1-M5. Cần resize trước M6 (file upload `.bit` 100 MB).

### Network rate limits (SV08 nginx)
| Zone | Path | Rate | Burst |
|---|---|---|---|
| `sv14_auth` | `/auth/*` | 10 req/min/IP | 5 |
| `sv14_api` | `/api/*` | 100 req/min/IP | 50 |
| `sv14_term` | `/term/*` | 30 req/min/IP | 10 |
| `sv14_conn` | toàn server | max 50 connections / IP | — |

Per-IP `429 Too Many Requests` khi vượt — bảo vệ Authentik login khỏi brute force.

### Firewall (SV14 UFW)
- 22/tcp ← 192.168.2.0/24 (SSH chỉ từ LAN)
- 3000/8000/9000/3001 ← 192.168.2.108 (chỉ SV08 ingress được phép)
- Mọi port khác: deny.

### Application-level limits (xác định trong `.env.prod`)
- `RATE_LIMIT_LOGIN_PER_MINUTE=5`
- `RATE_LIMIT_API_PER_MINUTE=100`
- `RATE_LIMIT_RESET_PER_MINUTE=3` (smart-plug power cycle)
- `RATE_LIMIT_UPLOAD_PER_HOUR=10`
- `BOOKING_MAX_DURATION_HOURS=8`
- `BOOKING_DEFAULT_QUOTA_HOURS_PER_WEEK=10`
- `BOOKING_DEFAULT_MAX_CONCURRENT=2`

## Hạ tầng đã dựng

### Cloudflare
- ✅ DNS CNAME `sv14.bcse-vju.com` → `425ec6ea-f9f6-4c5f-908a-451ea2703223.cfargotunnel.com` (proxied)
- ✅ Tunnel ingress rule: `sv14.bcse-vju.com` → `http://192.168.2.108:80` (SV08 nginx)

### SV08 (192.168.2.108) — reverse proxy
- ✅ nginx vhost `/etc/nginx/sites-enabled/sv14-lab-portal` → SV14 ports 3000/8000/9000/3001
- ✅ `/etc/nginx/conf.d/connection-upgrade.conf` (WebSocket map cho wetty)
- ✅ Coexists với bcse-intro + bcse-id sites đang chạy

### SV14 (192.168.2.114) — app stack
- ✅ Ubuntu 24.04, Docker 29.4.3, Compose v5.1.3
- ✅ 4 GB swap (build Next.js OOM-safe)
- ✅ UFW: cho phép SV08 only trên app ports
- ✅ Daily `pg_dump` backup script (cron chưa cài, file ở `/opt/vju-lab-portal/infrastructure/sv14/backup.sh`)

**9 containers up (`docker ps`):**
```
NAMES                               STATUS
vju-lab-portal-frontend-1           Up X min (healthy)
vju-lab-portal-backend-1            Up X min (healthy)
vju-lab-portal-worker-1             Up X min (RQ scheduler running)
vju-lab-portal-postgres-1           Up X min (healthy)
vju-lab-portal-redis-1              Up X min
vju-lab-portal-authentik-1          Up X min (booting)
vju-lab-portal-authentik-worker-1   Up X min
vju-lab-portal-authentik-db-1       Up X min
vju-lab-portal-wetty-1              Up X min
```

## File added/changed

```
bcse vLab/
├── README.md                             (updated — M0 status + run book)
├── DEPLOYMENT-SUMMARY.md                 (this file)
├── .pre-commit-config.yaml
├── .github/workflows/ci.yml              (lint + test + secret scan)
├── docs/
│   ├── 11-sv14-sv08-deployment.md        (NEW — runbook for ADR-0011 variant)
│   └── decisions.md                      (appended ADR-0011)
├── backend/                              (FastAPI skeleton)
│   ├── pyproject.toml + requirements*.txt
│   ├── Dockerfile + .dockerignore
│   ├── alembic.ini + migrations/
│   ├── app/
│   │   ├── main.py + __init__.py
│   │   ├── core/{config.py, logging.py}
│   │   └── api/routes/health.py
│   └── tests/{conftest.py, test_health.py}
├── frontend/                             (Next.js 14 skeleton)
│   ├── package.json + tsconfig.json + next.config.mjs
│   ├── tailwind.config.ts + postcss.config.mjs
│   ├── Dockerfile + .dockerignore
│   ├── src/app/{layout.tsx, page.tsx, globals.css, api/health/route.ts}
│   └── src/lib/api.ts
├── infrastructure/
│   ├── docker-compose.yml                (dev: postgres + redis + adminer)
│   ├── docker-compose.full.yml           (dev full-stack)
│   ├── postgres/init-extensions.sql      (uuid-ossp + btree_gist)
│   ├── sv14/
│   │   ├── docker-compose.prod.yml       (9 services)
│   │   ├── .env.prod.example
│   │   ├── postgres/init-extensions.sql
│   │   ├── setup-sv14.sh                 (Docker, UFW, swap, dirs)
│   │   └── backup.sh                     (daily pg_dump)
│   └── sv08-ingress/
│       ├── nginx-sv14-vhost.conf         (reverse proxy vhost)
│       └── nginx-upgrade-map.conf        (WS upgrade map)
└── scripts/
    ├── deploy_lab_portal.py              (main orchestrator)
    ├── cf_dns_sv14.py                    (CF DNS upsert)
    ├── smoke_test_sv14.py                (HTTPS smoke)
    ├── probe_sv14_sv08.py                (initial probe)
    ├── verify_sv14.py                    (state check)
    ├── peek_sv14.py + peek_sv14_compose.py (mid-deploy diagnostic)
    └── README.md
```

## Tiếp theo (M1)

Trước khi merge `feat/M0-bootstrap` → `main`, thầy review:

1. ✅ M0 DoD passed: docker compose up healthy, /api/health = 200, frontend serves qua HTTPS
2. 🔲 Init git repo (chưa init) + commit + tạo branch
3. 🔲 Confirm domain `sv14.bcse-vju.com` đúng — hay dùng `lab.vju.edu.vn`?
4. 🔲 **Authentik subdomain** — tạo `auth.sv14.bcse-vju.com` (CNAME + Tunnel rule + nginx vhost), thay cho path-based `/auth/`. Authentik 2024.x deprecated subpath.
5. 🔲 Setup OIDC client trong Authentik UI (cần `AUTHENTIK_BOOTSTRAP_PASSWORD` từ `.env.prod` để login lần đầu)
6. 🔲 Update `OIDC_REDIRECT_URI` trong backend `.env.prod` về URL mới
7. 🔲 Database migration 0001 — full schema từ `04-database-schema.md`
8. 🔲 ADR-0012: WireGuard tunnel SV14 ↔ Hòa Lạc gateway (cần trước M4 SSH access)

## Issue nhỏ đã fix
- ✅ `chown -R root:root` trong setup-sv14.sh → đổi thành `student:student` (gây tar fail lần đầu)
- ✅ Worker command `python -m rq` → `rq worker` (rq là package, không có `__main__`)
- ✅ Build cache 3.9 GB chiếm dung lượng → `docker builder prune -af` sau mỗi deploy
- ✅ Authentik DB password mismatch sau khi auto-rotate secret: wiped `vju-lab-portal_authentik_db` volume + recreated (Authentik chưa có data nên không mất gì)

## Gọi nhanh

```bash
# Code-only redeploy
python scripts/deploy_lab_portal.py --skip-cf --skip-setup --skip-sv08

# Smoke test
python scripts/smoke_test_sv14.py
```
