# 03 — Tech Stack

## Tổng hợp công nghệ

| Lớp | Công nghệ | Version | Lý do chọn |
|---|---|---|---|
| Hypervisor | Proxmox VE | 8.x | Đã có sẵn của thầy |
| Container | LXC (Proxmox native) | - | Nhẹ hơn VM, share kernel |
| Frontend framework | Next.js | 14.x (App Router) | SSR + React, ecosystem lớn |
| UI library | shadcn/ui + Tailwind CSS | latest | Components đẹp sẵn, copy-paste |
| State management | TanStack Query | 5.x | Server state, cache, refetch |
| Forms | react-hook-form + zod | latest | Validation type-safe |
| Calendar UI | react-big-calendar | latest | Booking calendar |
| Backend framework | FastAPI | 0.110+ | Python, OpenAPI auto-gen, async |
| ORM | SQLAlchemy 2.0 | 2.x | Mature, hỗ trợ async |
| Migration | Alembic | latest | Đi kèm SQLAlchemy |
| DB | PostgreSQL | 16 | Stable, JSON support, full-text search |
| Cache | Redis | 7 | Pub/sub, queue (RQ) |
| Auth provider | Authentik | 2024.x | OIDC, self-hosted, modern UI |
| Web SSH | wetty | latest | SSH-in-browser, rất nhẹ |
| SSH lib (backend) | AsyncSSH | latest | Manage ephemeral keys, async |
| Container | Docker + Docker Compose | latest | Trong từng LXC |
| Reverse proxy | Caddy | 2.x | Auto HTTPS, syntax đơn giản |
| Smart plug firmware | Tasmota | 13.x | API HTTP local |
| Monitoring | Uptime Kuma | latest | Đơn giản hơn Grafana cho MVP |
| Email | SMTP (Mailgun/SendGrid) | - | Booking notification |
| Background job | RQ (Redis Queue) | latest | Đơn giản hơn Celery |
| Test (BE) | pytest + httpx | latest | Standard Python |
| Test (FE) | Vitest + Playwright | latest | Fast unit + E2E |
| CI/CD | GitHub Actions | - | Tự động deploy lên Proxmox |
| Logs | Loguru (BE) + structured JSON | - | Send tới Loki nếu cần |
| IaC (optional) | Ansible | latest | Provision LXC, deploy, config |

## Vì sao không chọn các option khác

**Tại sao LXC mà không phải Docker trực tiếp trên Proxmox host?**
- Proxmox không khuyến khích cài Docker trên host (PVE host nên minimal)
- LXC tương đương VM về isolation, có Proxmox UI quản lý, snapshot/backup builtin
- Bên trong LXC vẫn chạy Docker được (nested) cho các service container hóa

**Tại sao không VM thay vì LXC?**
- LXC nhẹ hơn nhiều: boot trong 2-3s, RAM overhead ~30MB
- VM cần thiết khi: kernel module riêng, GPU passthrough, Windows
- Cho project này LXC là đủ và tối ưu

**Tại sao không cài hết vào 1 LXC?**
- Có thể! Nếu thầy muốn đơn giản, merge thành 1-2 LXC được
- Tách 5 LXC: backup riêng được, restart không ảnh hưởng nhau, log dễ tách
- Trade-off: cấu hình phức tạp hơn

**Tại sao không Kubernetes (K3s)?**
- K3s overhead lớn, học curve cao
- Cho 1 Proxmox node + 5 service → Docker Compose trong từng LXC là tối ưu
- Có thể migrate sau nếu scale ngang

**Tại sao Authentik mà không phải Keycloak?**
- Authentik nhẹ hơn (~500MB RAM vs ~1GB), UI hiện đại hơn
- Cả hai đều OIDC compliant, swap được sau

## Yêu cầu môi trường

### Trên Proxmox host
- Proxmox VE 8.x đã cài sẵn
- Storage pool đủ ~150GB cho 5 LXC
- 2 network bridge:
  - `vmbr0`: nối ra LAN chính + Internet
  - `vmbr1`: internal cho LXC nói chuyện với nhau
- LXC template Ubuntu 22.04 đã download (`pveam download local ubuntu-22.04-...`)

### Bên trong từng LXC
- Ubuntu 22.04 LTS
- Docker Engine 24+ và Docker Compose v2
- SSH key của thầy để truy cập
- Ansible-ready (Python 3.10+ cài sẵn)

### Trên máy dev (laptop của thầy)
- VS Code + Claude Code extension
- Git
- Docker Desktop (để test local)
- Node.js 20+ (cho frontend dev)
- Python 3.11+ (cho backend dev)
- Ansible (optional, để deploy)

### Trên mỗi thiết bị (KV260, Jetson, RPi)
- OS có sẵn theo board (Ubuntu/PetaLinux/JetPack)
- SSH server bật, port 22 open trong LAN
- 1 user `student` với home dir `/home/student/work`
- `student` có sudo NOPASSWD cho lệnh power management cơ bản
- Disable password auth, only key auth
- 1 master SSH key của backend đã được install sẵn (để backend SSH vào quản lý)

## Repository structure (sau khi Claude Code init)

```
vju-lab-portal/
├── README.md
├── CLAUDE.md
├── QUICKSTART.md
├── .env.example
├── .gitignore
├── docs/                          # Tài liệu hiện tại
├── frontend/
│   ├── app/                       # Next.js App Router
│   │   ├── (auth)/login/
│   │   ├── (student)/dashboard/
│   │   ├── (student)/bookings/
│   │   ├── (student)/devices/
│   │   ├── (student)/terminal/[deviceId]/
│   │   ├── (teacher)/teacher/classes/
│   │   ├── (teacher)/teacher/sessions/
│   │   └── (admin)/admin/
│   ├── components/ui/             # shadcn components
│   ├── lib/
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── auth.py
│   │   │   ├── devices.py
│   │   │   ├── bookings.py
│   │   │   ├── sessions.py
│   │   │   ├── teacher.py         # Endpoints cho lecturer
│   │   │   └── admin.py
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   │   ├── ssh_manager.py
│   │   │   ├── plug_controller.py
│   │   │   ├── access_control.py  # Logic phân quyền
│   │   │   └── scheduler.py
│   │   └── core/
│   ├── alembic/
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── infrastructure/
│   ├── docker-compose.yml         # Cho dev local
│   ├── proxmox/
│   │   ├── create-lxc.sh          # Auto-provision LXC
│   │   ├── lxc-config.yaml
│   │   └── ansible/
│   │       ├── inventory.yaml
│   │       ├── playbooks/
│   │       └── roles/
│   └── caddy/Caddyfile
├── scripts/
│   ├── deploy.sh
│   ├── backup-db.sh
│   ├── restore-db.sh
│   └── seed-admin.py
├── tests/integration/
└── .github/workflows/ci.yml
```

## Dependencies cụ thể

### Backend (pyproject.toml)
```toml
[project]
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "sqlalchemy[asyncio]>=2.0",
    "alembic>=1.13",
    "asyncpg>=0.29",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    "python-jose[cryptography]>=3.3",
    "passlib[bcrypt]>=1.7",
    "asyncssh>=2.14",
    "redis>=5.0",
    "rq>=1.16",
    "httpx>=0.27",
    "loguru>=0.7",
    "authlib>=1.3",
    "python-multipart>=0.0.9",  # cho file upload
    "aiofiles>=23.0",
]

[tool.uv.dev-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.3",
    "mypy>=1.8",
    "pytest-cov>=5.0",
]
```

### Frontend (package.json key deps)
```json
{
  "dependencies": {
    "next": "^14.2.0",
    "react": "^18.3.0",
    "@tanstack/react-query": "^5.40.0",
    "react-hook-form": "^7.51.0",
    "zod": "^3.23.0",
    "axios": "^1.7.0",
    "next-auth": "^4.24.0",
    "tailwindcss": "^3.4.0",
    "@radix-ui/react-dialog": "^1.1.0",
    "@radix-ui/react-select": "^2.0.0",
    "@radix-ui/react-toast": "^1.2.0",
    "lucide-react": "^0.400.0",
    "date-fns": "^3.6.0",
    "react-big-calendar": "^1.13.0",
    "@xterm/xterm": "^5.5.0",
    "papaparse": "^5.4.0"
  }
}
```

## Versioning policy
- Pin major version, allow minor/patch
- Lockfile commit (poetry.lock, package-lock.json)
- Renovate bot hàng tuần check update (optional)
