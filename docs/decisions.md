# Architecture Decision Records (ADR)

Mỗi quyết định ảnh hưởng kiến trúc, schema, hoặc trade-off lớn được log ở đây.

Format mỗi entry:

```
## ADR-NNNN: [Tiêu đề ngắn]

**Date**: YYYY-MM-DD
**Status**: Proposed | Accepted | Superseded by ADR-NNNN
**Decided by**: [Tên]

### Context
### Decision
### Alternatives considered
### Consequences
```

---

## ADR-0001: FastAPI + Next.js thay vì monolith

**Date**: 2026-05-08  
**Status**: Accepted

### Context
Cần web app fullstack với REST API, real-time UI updates, và web SSH terminal.

### Decision
Tách FE (Next.js 14 App Router) và BE (FastAPI) hoàn toàn. Communicate qua REST + SSE.

### Alternatives
- Django monolith: làm được hết nhưng async support yếu, Python templating outdated
- SvelteKit fullstack: ít người biết Svelte ở VN, harder to recruit
- Phoenix LiveView: Elixir learning curve quá cao

### Consequences
- ✅ FE/BE deploy + scale độc lập
- ✅ FastAPI async + OpenAPI auto-gen
- ✅ Next.js SSR/RSC + ecosystem React rất mạnh
- ❌ 2 codebase cần maintain
- 🔄 Cho phép thay 1 phía mà không động phía kia

---

## ADR-0002: Authentik thay vì Keycloak

**Date**: 2026-05-08  
**Status**: Accepted

### Context
Cần OIDC server self-hosted để integrate Google OAuth + LDAP nếu trường có.

### Decision
Dùng Authentik 2024.x.

### Alternatives
- Keycloak: mature nhất, java-based, RAM ~1GB
- Hanko: nhẹ nhất nhưng còn beta
- Authelia: tập trung 2FA hơn, không full OIDC

### Consequences
- ✅ UI hiện đại, RAM ~500MB
- ✅ Built-in flow editor, đỡ code custom
- ❌ Community nhỏ hơn Keycloak
- 🔄 Cả 2 đều OIDC compliant, swap được sau

---

## ADR-0003: Ephemeral SSH key cho session

**Date**: 2026-05-08  
**Status**: Accepted

### Context
Cần cho SV SSH vào device. Không thể cấp credential cố định (khó revoke khi kết thúc lớp).

### Decision
Mỗi session sinh 1 ed25519 key pair mới. Public key push lên device khi session start, remove khi end. Private key trả về 1 lần qua API, không lưu DB.

### Alternatives
- Password authentication: yếu, hard to revoke per session
- Cấp permanent key: không revoke được granular
- Certificate-based SSH: phức tạp, cần CA

### Consequences
- ✅ Auto-revoke khi hết slot
- ✅ Audit theo key fingerprint
- ❌ User phải lưu key local nếu dùng SSH client native
- 🔄 Có thể nâng cấp lên SSH CA model sau nếu cần

---

## ADR-0004: Triển khai trên Proxmox LXC tại Hòa Lạc

**Date**: 2026-05-08  
**Status**: Accepted

### Context
Lab Hòa Lạc đã có Proxmox host với IP tĩnh public, cùng LAN với pool thiết bị.

### Decision
Deploy 5 LXC trên Proxmox host: lab-proxy, lab-app, lab-db, lab-auth, lab-monitor. Tất cả nói chuyện qua bridge nội bộ vmbr1 (10.10.10.0/24). Chỉ lab-proxy có interface ra LAN chính/Internet.

### Alternatives
- 1 VPS public + WireGuard về lab: thêm overhead 20-30ms latency, single point of failure
- 1 LXC duy nhất chứa hết: dễ deploy, khó backup riêng + scale
- Kubernetes (K3s): overhead lớn, học curve cao

### Consequences
- ✅ Không cần VPN — backend SSH thẳng tới device qua LAN
- ✅ Latency portal-device < 5ms
- ✅ Backup snapshot LXC dễ
- ✅ Tận dụng infra có sẵn của thầy
- ❌ Cần Proxmox available (single point — nhưng đã chấp nhận)
- 🔄 Cluster nhiều node sau dễ — chỉ cần thêm Proxmox node thứ 2

---

## ADR-0005: Class-based access control (không phải pure RBAC)

**Date**: 2026-05-08  
**Status**: Accepted

### Context
Yêu cầu: SV không mặc định có quyền dùng kit. Lecturer phải cấp qua "lớp học". Đặc biệt cần override cho khóa luận (1-on-1).

### Decision
2 path để có quyền dùng device:
1. **Class path**: SV thuộc class C → class C có `class_device_assignment` cho device D → SV được dùng D
2. **Special access path**: Lecturer cấp quyền cá nhân cho 1 SV trên 1 device cụ thể, có lý do + audit

### Alternatives
- Pure RBAC: SV nào cũng dùng được mọi kit. Không phù hợp policy.
- Permission-based ACL: quá granular, lecturer setup phức tạp.
- Group-based: gần giống class nhưng abstract hơn, không gắn với học kỳ.

### Consequences
- ✅ Map đúng business model: class = unit cơ bản trong giáo dục
- ✅ Lecturer kiểm soát rõ ràng
- ✅ Audit trail đầy đủ (ai cấp quyền cho ai khi nào)
- ❌ Setup ban đầu cần lecturer làm 1 lần/học kỳ
- ❌ SV chuyển lớp giữa kỳ cần admin can thiệp
- 🔄 Có thể thêm "self-service" mode sau (SV apply, lecturer approve)

---

## ADR-0006: Soft delete cho assignments + enrollments

**Date**: 2026-05-08  
**Status**: Accepted

### Context
Khi lecturer revoke device khỏi class, hoặc remove SV khỏi class, cần giữ history cho audit.

### Decision
Dùng cột `revoked_at`/`is_active` thay vì DELETE. Booking đã tồn tại không bị ảnh hưởng (chỉ cấm tạo booking mới sau revoke).

### Alternatives
- Hard delete + cascade: mất history, audit không trace được
- Hard delete + audit log riêng: phức tạp hơn

### Consequences
- ✅ Audit trail nguyên vẹn
- ✅ Booking lịch sử vẫn link đúng class/assignment
- ❌ Index cần WHERE clause filter active records
- 🔄 Có job archive định kỳ sau 1 năm để giảm size

---

## ADR-0007: Special access dùng table riêng, không phải "virtual class"

**Date**: 2026-05-08  
**Status**: Accepted

### Context
Lecturer cần cấp quyền cá nhân cho SV làm khóa luận (ngoài bất kỳ lớp nào).

### Decision
Tạo table `special_access` riêng. Không tái sử dụng `classes` + `enrollments` cho case này.

### Alternatives
- Virtual class "1-1": tạo 1 class riêng cho SV, enroll SV vào, assign device. Hack.
- Reuse class table với flag `is_special=true`: pollute model.

### Consequences
- ✅ Schema clean, intent rõ
- ✅ Lý do (reason) là field bắt buộc → audit dễ
- ✅ UI cho lecturer 2 màn hình tách biệt: "Quản lý lớp" vs "Cấp quyền cá nhân"
- ❌ Logic access control phải union 2 path
- 🔄 Sau có thể merge nếu cần — migration không khó

---

## ADR-0008: Docker Compose trong từng LXC

**Date**: 2026-05-08  
**Status**: Accepted

### Context
LXC đã isolation rồi. Nhưng app cần multiple service (vd lab-app: frontend + backend + wetty + worker).

### Decision
Trong mỗi LXC chạy Docker Compose. LXC = "machine", Docker = "process orchestration".

### Alternatives
- Systemd unit cho từng service trong LXC: phải cài deps trực tiếp lên LXC, harder rollback
- 1 Docker container/LXC: lãng phí, mất ưu điểm compose

### Consequences
- ✅ `docker compose up/down` làm được restart granular
- ✅ Image immutable, deploy = pull + restart
- ✅ Test local trên laptop (Docker Desktop) y hệt prod
- ❌ Phải bật `nesting=1` trên LXC (đã handle trong create script)
- 🔄 Migrate sang K8s sau cũng dễ vì đã có Dockerfile

---

## ADR-0009: SSE thay vì WebSocket cho real-time UI

**Date**: 2026-05-08  
**Status**: Accepted

### Context
UI cần real-time update khi: device status change, session started/ended, lecturer observe, booking starting soon.

### Decision
Dùng Server-Sent Events (SSE) qua endpoint `/api/events/stream`. WebSocket chỉ dùng cho web terminal (do wetty).

### Alternatives
- WebSocket cho mọi thứ: complex hơn (manual ping/pong, reconnect logic)
- Long-polling: ineffficient
- Push notification: cần infra riêng

### Consequences
- ✅ HTTP/2 native support, qua reverse proxy không cần special config
- ✅ Auto-reconnect built-in trong EventSource API
- ✅ One-way (server→client) là đủ cho use case
- ❌ Một số corp proxy block SSE (rare)
- 🔄 Migrate WebSocket sau nếu cần two-way

---

## ADR-0010: CSV upload cho enroll, không API integration ban đầu

**Date**: 2026-05-08  
**Status**: Accepted

### Context
Lecturer cần enroll 25-30 SV vào class. Có thể tích hợp với hệ thống trường (LMS, SIS) nhưng phức tạp.

### Decision
Bắt đầu với CSV upload. API integration là enhancement sau.

### Alternatives
- API integration với hệ thống trường ngay: phụ thuộc IT trường, blocker timeline
- Manual nhập từng email: chậm, dễ typo

### Consequences
- ✅ Lecturer làm được ngay, không cần IT trường support
- ✅ Universal — mọi LMS export CSV được
- ❌ Lecturer phải refresh CSV mỗi học kỳ
- 🔄 Phase 2: tích hợp API với hệ thống trường, vẫn giữ CSV làm fallback

---

## ADR-0011: Triển khai trên VPS SV14 với SV08 làm reverse-proxy ingress

**Date**: 2026-05-08
**Status**: Accepted (supersedes ADR-0004 cho phần "Proxmox host duy nhất + DNAT public IP")
**Decided by**: Thầy + Claude Code

### Context
ADR-0004 giả định Proxmox host tại Hòa Lạc với IP tĩnh public, đảm nhiệm cả role hosting LXC lẫn ingress (DNAT 80/443 → vmbr1). Trong thực tế hệ sinh thái BCSE-VJU đang dùng:

- **Cloudflare Tunnel** cho mọi domain `*.bcse-vju.com`, không expose IP public của Proxmox host
- Mỗi VPS gắn 1 sub-domain riêng (sv01.bcse-vju.com, sv02..., sv13...) qua CNAME → CF Tunnel → jump host LAN `123.16.53.250:2223`
- Reserved slot: SV05/07/**08**/10/12 — `SV08` chưa được gán app nào

Yêu cầu mới của thầy:
1. Deploy VJU Lab Portal lên **SV14** (VM114, IP nội bộ giả định `192.168.2.114`)
2. Mở "1 cổng dịch vụ của SV14 trên VPS SV08" — tức SV08 làm reverse-proxy/ingress public, đứng trước SV14

### Decision

Topology mới:

```
Internet
  │
  ▼
Cloudflare (sv14.bcse-vju.com → CNAME → bcse-vju.com, proxied)
  │
  ▼  CF Tunnel
SV08 (192.168.2.108) — Caddy reverse proxy (TLS termination tại CF, internal LAN HTTP OK)
  │  via internal LAN 192.168.2.0/24 (cùng Proxmox cluster)
  ▼
SV14 (192.168.2.114) — Docker Compose stack (frontend, backend, postgres, redis, authentik, wetty)
  │  via Proxmox host LAN bridge tới device pool
  ▼
Device pool 192.168.20.0/24 (KV260/Jetson/RPi) + Plug pool 192.168.30.0/24
  (giả định: cùng Proxmox cluster Hòa Lạc, thầy verify; nếu không thì cần WireGuard tunnel)
```

Cụ thể:
- **SV14**: chạy `docker compose` với 6 service: `frontend` (Next.js :3000), `backend` (FastAPI :8000), `worker` (RQ), `wetty` (:3001), `postgres` (:5432, internal-only), `redis` (:6379, internal-only). Authentik thường co-locate trong M1 nhưng sẽ chạy trong cùng compose stack ở SV14 (port nội bộ :9000) để đơn giản — không tách LXC như ADR-0004 nữa.
- **SV08**: chạy Caddy 2.x (single Caddyfile) làm reverse proxy duy nhất exposes port 80 vào CF Tunnel. Caddy proxy:
  - `sv14.bcse-vju.com/` → `192.168.2.114:3000` (Next.js)
  - `sv14.bcse-vju.com/api/*` → `192.168.2.114:8000` (FastAPI)
  - `sv14.bcse-vju.com/auth/*` → `192.168.2.114:9000` (Authentik)
  - `sv14.bcse-vju.com/term/*` → `192.168.2.114:3001` (wetty)
- **TLS**: Cloudflare terminates TLS ở edge; SV08 ↔ SV14 là LAN HTTP nội bộ (chấp nhận được vì network 192.168.2.0/24 nằm trong Proxmox cluster, không Internet).
- **Backend → Device pool**: nếu Proxmox host của SV14 có route trực tiếp tới `192.168.20.0/24` và `192.168.30.0/24` → dùng trực tiếp (giữ ưu điểm same-LAN của ADR-0004). Nếu **không** có route, **phải thêm WireGuard tunnel** từ SV14 tới gateway Hòa Lạc; ADR-0011 ghi nhận khả năng này nhưng không bật mặc định — đợi thầy xác nhận topology vật lý.

### Alternatives considered
- **A. Public-IP DNAT trên Proxmox như ADR-0004 gốc**: phá vỡ pattern Cloudflare Tunnel của hệ sinh thái BCSE; cần expose IP public mới; mỗi domain đăng ký riêng (không tận dụng `*.bcse-vju.com`).
- **B. Caddy chạy trên SV14, SV08 chỉ NAT/passthrough**: SV14 vẫn cần TLS cert; mất đồng bộ với pattern hiện tại (SV01-SV13 đều có CF Tunnel ingress).
- **C. SV14 trực tiếp expose qua Cloudflare Tunnel (bỏ SV08)**: được nhưng mất "1 cổng dịch vụ trên SV08" theo yêu cầu thầy. Tùy chọn này dự phòng nếu SV08 không khả dụng.

### Consequences
- ✅ Đồng nhất pattern với SV01-SV13 (CF Tunnel + sub-domain + Caddy/Nginx ingress)
- ✅ TLS auto-managed bởi Cloudflare, không cần Let's Encrypt local — nhẹ hơn
- ✅ Public IP của Proxmox host không bị expose
- ✅ SV08 đóng vai DMZ — nếu app trên SV14 bị compromise, attacker vẫn phải chui qua Caddy + CF Tunnel
- ✅ Reserved slot SV08 được tận dụng (không tốn VM thêm)
- ❌ **Hop thừa SV08 → SV14** thêm ~0.5-1ms latency LAN, chấp nhận được vì cùng cluster
- ❌ Hai-VPS dependency: nếu SV08 down → SV14 không reachable từ Internet (mitigation: SV08 chạy `caddy + systemd`, restart on-failure; có thể fallback bypass qua Cloudflare Tunnel trực tiếp lên SV14 trong sự cố)
- ❌ ADR-0004 phần "5 LXC" không còn áp dụng — collapsed thành 1 VPS chạy compose; đánh đổi để đơn giản hóa ops cho phiên bản hiện tại
- ❌ Backup snapshot LXC → đổi thành Proxmox VPS snapshot + `pg_dump` cron như các SV khác trong hệ sinh thái
- 🔄 Có thể tách lab-db, lab-auth ra LXC riêng sau khi pilot scale lên >50 SV concurrent
- 🔄 Nếu SV14 không có route tới device pool → ADR-0012 (sẽ raise sau) cho WireGuard back-haul

### Open follow-ups
- Xác nhận với thầy: SV14 (192.168.2.114) **có route tới `192.168.20.0/24` và `192.168.30.0/24` không?** (sẽ test bằng `ping` / `arp` sau khi VPS up)
- Xác nhận: Domain `sv14.bcse-vju.com` có ổn không, hay thầy muốn `lab.vju.edu.vn` (domain khác zone)?
- Tạo CNAME Cloudflare cho `sv14` → `bcse-vju.com` (pattern hiện tại)

---

## Template cho ADR mới

Khi Claude Code có quyết định kiến trúc mới, append vào file này theo format:

```markdown
## ADR-NNNN: [Tiêu đề]

**Date**: YYYY-MM-DD
**Status**: Proposed
**Decided by**: [Claude Code + thầy]

### Context
[Vấn đề]

### Decision
[Quyết định]

### Alternatives considered
- Option A: pros/cons
- Option B: pros/cons

### Consequences
- ✅ Pros
- ❌ Cons
- 🔄 Future implications
```
