# VJU Hardware Lab Portal

Cổng truy cập thiết bị phần cứng từ xa cho sinh viên VJU. Cho phép sinh viên đăng nhập qua web, đặt lịch sử dụng, và truy cập SSH tới các bộ kit FPGA Kria KV260, Jetson Nano/Orin, Raspberry Pi 4/5 đặt tại lab Hòa Lạc.

**Đặc điểm chính của hệ thống:**
- Phân quyền 3 cấp: SV thuộc lớp → giảng viên gán kit cho lớp → admin quản lý toàn bộ
- Triển khai trên Proxmox LXC tại Hòa Lạc (cùng LAN với pool thiết bị)
- Không cần VPN/bastion — tận dụng same-LAN advantage

## Đối tượng đọc

Tài liệu này được thiết kế để **Claude Code** đọc và triển khai dự án từ đầu đến cuối. Khi mở project trong VS Code, hãy nói với Claude Code:

> "Đọc toàn bộ thư mục `docs/` theo thứ tự đánh số, sau đó bắt đầu implement theo `docs/05-implementation-plan.md`. Hỏi tôi trước khi tạo bất kỳ commit nào và trước khi deploy lên Proxmox."

> 💡 **Đi nhanh nhất**: mở `QUICKSTART.md` ở thư mục gốc — có sẵn checklist hạ tầng + bootstrap prompt copy-paste cho Claude Code.

## Thứ tự đọc tài liệu

| File | Nội dung | Đọc khi |
|---|---|---|
| `01-overview.md` | Bối cảnh, mục tiêu, người dùng, ràng buộc | Đầu tiên — bắt buộc |
| `02-architecture.md` | Kiến trúc hệ thống, các service, data flow | Trước khi thiết kế DB hay viết code |
| `03-tech-stack.md` | Công nghệ cụ thể, lý do chọn, version | Khi setup môi trường |
| `04-database-schema.md` | Schema SQL, ERD, migration plan | Trước khi tạo model/migration |
| `05-implementation-plan.md` | Roadmap 14 tuần, milestone, deliverable | Tham chiếu liên tục khi code |
| `06-api-spec.md` | OpenAPI spec, endpoint, auth flow | Khi viết backend |
| `07-deployment-proxmox.md` | LXC setup, Docker Compose, networking | Trước khi deploy |
| `08-security-checklist.md` | Auth, secrets, audit, hardening | Trước khi go-live |
| `09-teacher-workflow.md` | UX cho giảng viên, dashboard | Khi build M2.5 + admin panel |
| `10-access-control.md` | Logic phân quyền chi tiết | Khi implement booking validation |

## Trạng thái dự án

- [x] **M0** — Bootstrap (FE + BE skeleton, docker-compose dev, CI lint+build, ADR-0011 cho SV14/SV08)
- [x] **M1** — VPS infra + Auth: SV14 Docker stack + SV08 nginx ingress + CF Tunnel + **whitelist email/password** (drop OIDC vì phiền) + JWT cookies + bcrypt + force-change-password lần đầu
- [x] **M1.D** — Schema migrations 0001 (11 tables + GIST EXCLUDE) + 0002 (`password_hash` + `must_change_password`) trên prod
- [x] **M2** — Device CRUD (admin), Class CRUD (lecturer-scoped), CSV bulk enrollment, class-device assignments, special-access cho khóa luận
- [x] **M2.5** — Admin/teacher hub UI (`/admin/{devices,classes,sessions,users}`) + admin tạo tài khoản trực tiếp
- [x] **M3** — `services/access_control.py` (canonical, 10 reason codes, 2 paths: class + special_access) + `POST /api/bookings` race-safe (GIST EXCLUDE fallback) + 10 mandatory tests
- [x] **M4** — SSH manager (ephemeral ed25519 với mock fallback) + Sessions endpoints (provision / end / active / kick)
- [x] **M5** — Plug controller (Tasmota / Shelly / mock) + `POST /api/devices/{id}/reset` với booking-owner authz
- [x] Audit logging service (append-only) + SSE events stream skeleton
- [x] Daily `pg_dump` cron (03:00 UTC) — backup labportal DB, 30-day retention
- [ ] **M6** — File transfer (`POST /api/sessions/{id}/upload`) + audit log viewer UI
- [ ] **M7** — Polish: Uptime Kuma, email notifications, Trivy scan, pilot 20 SV

## Cách dùng (cho người dùng cuối)

1. Truy cập <https://sv14.bcse-vju.com/login>
2. Login với email VJU + mật khẩu mặc định **`VJU@2026`** (admin gửi)
3. Lần đầu hệ thống bắt đổi mật khẩu — đặt mật khẩu mới (≥ 8 ký tự)
4. Vào `/devices` chọn thiết bị → đặt lịch (datetime + ghi chú)
5. Đến giờ click **Connect** ở `/bookings` → terminal SSH mở trong tab mới (private key copy vào clipboard)
6. Cancel/Logout/Đổi mật khẩu trong dropdown user

### Whitelist tài khoản (seed sẵn)
| Email | Role | Note |
|---|---|---|
| `admin@vju.ac.vn` | admin | Quản trị toàn hệ thống |
| `thaykien@vju.ac.vn`, `hung.le@vju.ac.vn`, `anh.nguyen@vju.ac.vn` | lecturer | Tạo lớp, gán device, kick session |
| `sv01@st.vju.ac.vn` … `sv10@st.vju.ac.vn` | student | 10 tài khoản pilot |

Tất cả seeded với `password=VJU@2026` + `must_change_password=true`. Chỉnh whitelist trong `backend/scripts/seed.py`.

### Admin tạo thêm tài khoản
Trong `/admin/users`: email + họ tên + role + (optional) mã SV → submit → hệ thống trả về mật khẩu ban đầu (default `VJU@2026`). User phải đổi mật khẩu khi login lần đầu. Admin cũng có thể reset password và đổi role bất kỳ user nào.

## Endpoints

### Frontend (Next.js 14 App Router)
| Route | Mô tả |
|---|---|
| `/` | Hero + 3-step + 3-device-feature cards + backend status |
| `/login` | Form đăng nhập email + password (real local auth) |
| `/change-password` | Đổi mật khẩu (force redirect khi `must_change_password=true`) |
| `/dashboard` | Bookings sắp tới + Quick actions + Available devices |
| `/devices` | List + filter theo type/status |
| `/devices/[id]` | Detail + form đặt lịch (datetime-local + notes) |
| `/bookings` | List + Connect (mở wetty + copy private key) + Cancel |
| `/admin` | Hub — 5 tile, scope theo role |
| `/admin/devices` | CRUD devices (admin only, click status để cycle) |
| `/admin/classes` | Tạo lớp + CSV enroll (lecturer + admin) |
| `/admin/sessions` | Active SSH sessions + Kick (auto-refresh 15s) |
| `/admin/users` | Tạo user, đổi role inline, reset password (admin only) |

### Backend (FastAPI 0.110)
| Method | Path | Auth |
|---|---|---|
| GET | `/api/health`, `/api/ready` | public |
| POST | `/api/auth/login` | public — body: `{email, password}` → 200 + cookies |
| POST | `/api/auth/change-password` | logged-in — body: `{current_password, new_password}` |
| GET | `/api/auth/me` | logged-in |
| POST | `/api/auth/logout` | logged-in — clears cookies |
| POST / GET | `/api/auth/admin/users` | admin only — create / list |
| POST | `/api/auth/admin/users/{id}/reset-password` | admin — reset to default |
| PATCH | `/api/auth/admin/users/{id}/role?role=…` | admin — change role |
| GET / POST / PATCH / DELETE | `/api/devices` | admin write, all-logged-in read |
| POST | `/api/devices/{id}/reset` | current booking owner OR admin/TA |
| GET / POST | `/api/classes` | lecturer-scoped (admin sees all) |
| GET / POST | `/api/classes/{id}/devices` | lecturer assignments |
| DELETE | `/api/classes/{id}/devices/{aid}` | revoke (soft-delete) |
| GET | `/api/classes/{id}/enrollments` | lecturer |
| POST | `/api/classes/{id}/enroll/csv` | lecturer bulk CSV |
| POST | `/api/teacher/special-access` | lecturer grants individual override |
| GET / POST | `/api/bookings` | logged-in (own only on GET; `access_control` gates POST) |
| POST | `/api/bookings/{id}/cancel` | owner |
| POST | `/api/sessions/provision/{booking_id}` | owner — ephemeral ed25519, returned ONCE |
| POST | `/api/sessions/{id}/end` | owner OR lecturer/admin |
| GET | `/api/sessions/active` | role-scoped |
| POST | `/api/sessions/{id}/kick` | lecturer/admin |
| GET | `/api/events/stream` | SSE heartbeat (15s) |

### Live URL
- App: <https://sv14.bcse-vju.com>
- API docs (dev only, prod = 404): <http://localhost:8000/api/docs>

### Mock mode (M4/M5 fallback)
SV14 không có route tới `192.168.20.0/24` (device pool) hay `192.168.30.0/24` (plug pool). Cho đến khi WireGuard tunnel ↔ Hòa Lạc lab được dựng, backend chạy ở mock mode:
- `MOCK_SSH_DEVICES=true` (default) → `provision_session` tạo keypair thật nhưng không SSH; trả `mocked: true`.
- `MOCK_PLUGS=true` (default) → `power_cycle` no-op; trả mock state.

Tắt mock khi tunnel up: set `MOCK_SSH_DEVICES=false` + `MOCK_PLUGS=false` trong `.env.prod`, mount backend SSH key vào `BACKEND_SSH_KEY_PATH`.

## Endpoints triển khai

### Frontend (Next.js 14 App Router)
| Route | Mô tả |
|---|---|
| `/` | Hero + 3-step + 3-device-feature cards + backend status |
| `/login` | Authentik OIDC redirect (M1.B chưa setup → 404 ở Authentik) |
| `/dashboard` | Bookings sắp tới + Quick actions + Available devices (real API) |
| `/devices` | List + filter theo type/status (real API) |
| `/devices/[id]` | Detail + form đặt lịch (datetime-local + notes) |
| `/bookings` | List bookings + Connect (mở wetty + copy private key) + Cancel |
| `/admin` | Hub — 5 tile, scope theo role |
| `/admin/devices` | CRUD devices (admin only, click status để cycle) |
| `/admin/classes` | Tạo lớp + CSV enroll (lecturer + admin) |
| `/admin/sessions` | List active SSH sessions + Kick button (auto-refresh 15s) |

### Backend (FastAPI 0.110)
| Method | Path | Auth |
|---|---|---|
| GET | `/api/health`, `/api/ready` | public |
| GET | `/api/auth/login?next=` | public — 302 → Authentik authorize |
| GET | `/api/auth/callback?code&state` | OIDC — sets httpOnly JWT cookies, upserts user |
| GET | `/api/auth/me` | any user |
| POST | `/api/auth/logout` | any user — clears cookies + redirect Authentik end-session |
| GET / GET / POST / PATCH / DELETE | `/api/devices` | admin write, all read |
| POST | `/api/devices/{id}/reset` | booking owner OR admin/TA — Tasmota power-cycle |
| GET / POST | `/api/classes` | lecturer-scoped (admin sees all) |
| GET / POST | `/api/classes/{id}/devices` | lecturer-only (assignments) |
| DELETE | `/api/classes/{id}/devices/{aid}` | revoke assignment (soft-delete) |
| GET | `/api/classes/{id}/enrollments` | lecturer-only |
| POST | `/api/classes/{id}/enroll/csv` | lecturer-only — bulk CSV |
| POST | `/api/teacher/special-access` | lecturer-only |
| GET / POST | `/api/bookings` | any user (own only on GET; access_control on POST) |
| POST | `/api/bookings/{id}/cancel` | owner only |
| POST | `/api/sessions/provision/{booking_id}` | owner — issues ephemeral ed25519, returns key once |
| POST | `/api/sessions/{id}/end` | owner OR lecturer/admin |
| GET | `/api/sessions/active` | role-scoped (admin all, lecturer own classes, user own) |
| POST | `/api/sessions/{id}/kick` | lecturer/admin |
| GET | `/api/events/stream` | SSE heartbeat (15s) — M3+ for device.status + booking events |

### Live URLs
- App: <https://sv14.bcse-vju.com>
- Authentik admin: <https://lab-auth.bcse-vju.com/if/admin/>
- API docs (dev only, prod = 404): <http://localhost:8000/api/docs>

### Mock mode (M4/M5 fallback)
SV14 không có route tới `192.168.20.0/24` (device pool) hay `192.168.30.0/24` (plug pool) — confirmed in initial probe. Cho đến khi WireGuard tunnel ↔ Hòa Lạc lab được dựng (ADR-0012, sẽ raise), backend chạy ở mock mode:
- `MOCK_SSH_DEVICES=true` (default) → `provision_session` tạo keypair thật nhưng không SSH; trả `mocked: true` flag.
- `MOCK_PLUGS=true` (default) → `power_cycle` no-op; trả mock state.

Tắt mock khi tunnel up: set `MOCK_SSH_DEVICES=false` + `MOCK_PLUGS=false` trong `.env.prod`, mount backend SSH key vào `BACKEND_SSH_KEY_PATH`.

## Triển khai (deployment variant ADR-0011)

Khác với thiết kế gốc (Proxmox LXC tại Hòa Lạc, DNAT public IP), bản triển khai
hiện tại đi theo pattern hệ sinh thái BCSE-VJU:

```
Internet → Cloudflare (sv14.bcse-vju.com, proxied) → CF Tunnel
        → SV08:80 (nginx vhost reverse proxy)
        → SV14:3000 (frontend) / 8000 (backend) / 3001 (wetty)
        Docker Compose: postgres + redis + backend + worker + frontend + wetty (6 services)
```

Run:
```bash
python scripts/cf_dns_sv14.py                            # one-time DNS
python scripts/deploy_lab_portal.py                      # full deploy
python scripts/deploy_lab_portal.py --skip-setup --skip-build   # subsequent
python scripts/deploy_lab_portal.py --smoke-only         # just verify
```

Xem chi tiết: `docs/decisions.md` ADR-0011 + `infrastructure/sv14/` + `infrastructure/sv08-ingress/`.

## Local dev quickstart

```bash
# 1. Compose up postgres + redis + adminer
cd infrastructure && docker compose up -d

# 2. Backend
cd ../backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
cp ../.env.example ../.env
uvicorn app.main:app --reload --port 8000             # http://localhost:8000/api/docs

# 3. Frontend (separate shell)
cd ../frontend
npm install
npm run dev                                           # http://localhost:3000
```

## Cấu trúc thư mục đề xuất

```
vju-lab-portal/
├── docs/                    # Tài liệu này (read-only sau khi finalize)
├── frontend/                # Next.js app
├── backend/                 # FastAPI app
├── infrastructure/
│   ├── docker-compose.yml
│   ├── proxmox/
│   │   ├── create-lxc.sh    # Auto-provision LXC containers
│   │   └── lxc-config.yaml
│   └── caddy/
├── scripts/                 # Helper scripts
└── tests/
```

## Quy ước làm việc với Claude Code

1. **Không hardcode secrets.** Mọi thứ đi qua `.env` (sample trong `.env.example`).
2. **Không tự ý cài thêm dependency** không có trong `03-tech-stack.md` mà không hỏi.
3. **Mỗi feature = 1 branch + 1 PR.** Không commit trực tiếp lên `main`.
4. **Test trước khi commit.** Tối thiểu unit test cho business logic.
5. **Dừng và hỏi** khi gặp quyết định ảnh hưởng kiến trúc (vd: đổi DB, đổi auth provider).

## Thông tin liên hệ

- Maintainer: [Thầy điền vào]
- Lab vật lý: Hòa Lạc, VJU
- Hạ tầng: Proxmox cluster tại Hòa Lạc với IP tĩnh
- Mục đích sử dụng: Sinh viên BCSE — VHDL, SoC, Embedded, AI Edge
