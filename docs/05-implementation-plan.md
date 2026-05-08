# 05 — Implementation Plan

Tài liệu này là **roadmap quan trọng nhất** cho Claude Code. Khi Claude Code đọc, nó nên follow tuần tự và **không nhảy bước**.

## Nguyên tắc cho Claude Code

1. **Mỗi milestone = 1 branch riêng** (vd `feat/M1-infrastructure`)
2. **Cuối mỗi milestone**: chạy test, demo cho thầy, merge vào `main` mới đi tiếp
3. **Không skip test.** Code không có test ≠ done
4. **Document as you go**: update `README.md` và `docs/` khi có thay đổi
5. **Hỏi thầy** khi gặp ambiguous requirement, không tự đoán

## Milestone 0 — Project bootstrap (Day 1)

**Goal**: Có repository + CI cơ bản + môi trường dev local chạy được.

Tasks cho Claude Code:
- [ ] Init git repo, push lên GitHub/GitLab
- [ ] Tạo `.gitignore`, `.env.example`, `README.md`
- [ ] Setup Docker Compose dev với 3 service: postgres, redis, adminer
- [ ] Tạo skeleton `backend/` với FastAPI hello-world
- [ ] Tạo skeleton `frontend/` với Next.js fresh app
- [ ] Setup pre-commit hooks: ruff (Python), eslint + prettier (JS)
- [ ] CI pipeline chạy được: lint + build cho cả FE và BE

**Definition of Done**: 
- Chạy `docker compose up` → tất cả service xanh
- `curl localhost:8000/health` → 200
- `curl localhost:3000` → Next.js home page
- Push code → CI pass

## Milestone 1 — Proxmox infrastructure + Auth (Tuần 1-3)

**Goal**: 5 LXC chạy trên Proxmox + user có thể đăng nhập.

### Phần 1.A: Proxmox LXC provisioning

- [ ] Viết script `infrastructure/proxmox/create-lxc.sh`:
  - Tạo 5 LXC với specs trong `02-architecture.md`
  - Network bridge config (vmbr0 + vmbr1)
  - SSH key install
  - Auto-start on Proxmox boot
- [ ] Viết Ansible playbook để cài Docker, basic packages vào từng LXC
- [ ] Test: thầy chạy script trên Proxmox của thầy, 5 LXC up trong < 10 phút
- [ ] Document trong `07-deployment-proxmox.md`

### Phần 1.B: Database + Auth flow

- [ ] Setup Alembic, viết migration 0001 với schema từ `04-database-schema.md`
- [ ] Cài Authentik trong LXC `lab-auth`, config OIDC
- [ ] Backend: implement OIDC flow (callback `/auth/callback`)
- [ ] Backend: JWT issuance + verification middleware
- [ ] Backend: endpoints `/auth/me`, `/auth/logout`
- [ ] Frontend: login page redirect tới Authentik
- [ ] Frontend: protected route wrapper, lưu JWT trong httpOnly cookie
- [ ] Tạo seed script: 1 admin, 1 lecturer, 5 student giả lập

**Definition of Done**:
- 5 LXC chạy ổn định trên Proxmox
- SV mở `https://lab.vju.edu.vn` → redirect Authentik → login → quay lại dashboard
- F5 reload → vẫn logged in
- Logout xóa session cả 2 phía
- Lecturer login → thấy dashboard khác (chưa có content, chỉ shell)

## Milestone 2 — Device + Class core (Tuần 4-5)

**Goal**: Có CRUD device + class + enrollment + assignment.

Tasks:
- [ ] Backend: CRUD `/api/devices` (admin only cho create/update)
- [ ] Backend: CRUD `/api/classes` (lecturer + admin)
- [ ] Backend: `/api/classes/{id}/enroll` — bulk enroll bằng email list
- [ ] Backend: `/api/classes/{id}/devices` — assign/revoke device cho class
- [ ] Backend: validate khung thời gian (allowed_time_windows format)
- [ ] Frontend admin: trang quản lý device
- [ ] Frontend admin: trang quản lý user (assign role)
- [ ] Seed: 9 KV260 mock với IP giả (không cần device thật ở giai đoạn này)

**Definition of Done**:
- Admin tạo được class + assign 6 KV260 cho class
- Lecturer enroll 5 SV vào class
- Tất cả thao tác có audit log
- Test E2E pass

## Milestone 2.5 — Teacher dashboard (Tuần 6) ⭐

**Goal**: Lecturer có dashboard đầy đủ để quản lý lớp.

> Đây là **feature core của portal** — đừng coi là "phụ".

Tasks (xem chi tiết trong `09-teacher-workflow.md`):
- [ ] Frontend `(teacher)/teacher/classes` — list class của lecturer
- [ ] Frontend `(teacher)/teacher/classes/[id]` — chi tiết 1 class:
  - Tab "Sinh viên": list + bulk enroll (CSV upload)
  - Tab "Thiết bị": list devices đã assign + add/revoke
  - Tab "Lịch": calendar view xem booking của cả lớp
  - Tab "Sessions": active sessions + history
- [ ] Frontend `(teacher)/teacher/special-access` — cấp quyền cá nhân (cho khóa luận)
- [ ] Frontend: Form CSV upload với preview + validate trước khi commit
- [ ] Backend: endpoint POST `/api/teacher/classes/{id}/enroll/csv` (multipart)
- [ ] Backend: endpoint POST `/api/teacher/special-access` 
- [ ] Backend: endpoint GET `/api/teacher/sessions/active` (chỉ lớp của lecturer)
- [ ] Backend: endpoint POST `/api/teacher/sessions/{id}/observe` (read-only)
- [ ] Backend: endpoint POST `/api/teacher/sessions/{id}/kick` (force end)

**Definition of Done**:
- Lecturer setup 1 class hoàn chỉnh trong < 15 phút
- CSV với 30 SV import < 30 giây
- Lecturer thấy được session SV đang chạy (chưa cần observe live, chỉ list)
- UX cho lecturer được test bởi 1 giảng viên thật và feedback positive

## Milestone 3 — Booking với access control (Tuần 7-8)

**Goal**: SV book device được, nhưng chỉ device có quyền dùng.

Tasks:
- [ ] Backend service `access_control.py`:
  - `get_devices_accessible_to_user(user_id)` → list device IDs
  - `can_user_book_device(user_id, device_id, start, end)` → (bool, reason)
  - Logic chi tiết trong `10-access-control.md`
- [ ] Backend: CRUD `/api/bookings` với access control gate
- [ ] Backend: scheduled job (RQ) check booking sắp tới và mark `active`
- [ ] Frontend SV: Dashboard chỉ hiển thị device user có quyền
- [ ] Frontend SV: Booking calendar (react-big-calendar)
- [ ] Frontend SV: Form tạo booking với device dropdown filter theo quyền
- [ ] Frontend SV: Trang "My bookings" liệt kê + cancel
- [ ] SSE endpoint emit khi device status change → frontend update real-time

**Definition of Done**:
- SV thuộc class A thấy được 6 KV260, SV không thuộc class nào → empty list
- SV book trong khung giờ allowed → success
- SV book ngoài khung giờ → 403 với message rõ ràng
- SV book trùng slot bị reject với suggestion slot khác
- Cancel booking → slot lại free
- Test access control coverage ≥ 90%

## Milestone 4 — SSH access core (Tuần 9-10)

**Goal**: SV book xong → click connect → SSH vào device qua web terminal.

> **CHÚ Ý**: Đây là milestone phức tạp nhất, có nhiều rủi ro bảo mật. Claude Code đọc kỹ `08-security-checklist.md` trước khi làm.

Tasks:
- [ ] Setup network giữa LXC `lab-app` và 1 device thật (1 KV260) cho test
- [ ] Backend service `ssh_manager.py`:
  - `generate_ephemeral_keypair()` → tạo ed25519 key
  - `provision_session(booking_id)` → SSH vào device, append pubkey
  - `revoke_session(session_id)` → SSH vào device, remove pubkey
- [ ] Background job: provision khi booking đến giờ, revoke khi hết
- [ ] Setup wetty container trong LXC `lab-app`
- [ ] Backend endpoint `/api/sessions/{id}/connect` → trả về wetty URL với token
- [ ] Frontend: Trang `/terminal/[deviceId]` nhúng wetty iframe
- [ ] Test với 1 KV260 thật

**Definition of Done**:
- SV book slot, đến giờ nhận email "ready to connect"
- Click connect → terminal hiện trong browser
- Gõ command, output hiển thị real-time
- Hết slot → terminal bị disconnect, key bị revoke (verify: SSH lại → fail)
- Lecturer observe được session (read-only) — bonus nếu xong sớm

## Milestone 5 — Smart plug + reset (Tuần 11)

**Goal**: Device treo → reset được qua portal.

Tasks:
- [ ] Backend service `plug_controller.py` với adapter pattern:
  - `TasmotaAdapter`, `ShellyAdapter`, abstract `PlugAdapter`
  - Method: `power_off()`, `power_on()`, `power_cycle()`, `get_state()`
- [ ] Migration: insert plug_mappings cho từng device
- [ ] Endpoint `/api/devices/{id}/reset` (auth: device đang trong booking của user, hoặc admin/TA)
- [ ] Frontend: Nút "Reset" trên device card, confirm dialog
- [ ] Background job: poll device state mỗi 5s sau reset
- [ ] Audit log: ai reset, khi nào, kết quả
- [ ] Test với 1 smart plug Tasmota thật

**Definition of Done**:
- SV reset device được, sau 60s device live lại
- Audit log record đầy đủ
- SV không thuộc booking → click reset → 403

## Milestone 6 — File transfer + admin panel (Tuần 12)

**Goal**: SV upload file lên device, admin có dashboard quản lý.

Tasks:
- [ ] Backend: endpoint `POST /api/sessions/{id}/upload` (multipart, max 100MB)
  - Stream file qua SSH lên `/home/student/work/uploads/`
  - Return path để SV biết file ở đâu
- [ ] Frontend: drag-drop upload trong terminal page
- [ ] Frontend: Admin panel
  - List all sessions (active + history)
  - Force disconnect session bất kỳ
  - View audit log với filter
  - Manage devices (toggle maintenance mode)
  - Manage user quotas
  - Manage roles
- [ ] Backend: endpoints admin với role check

**Definition of Done**:
- SV upload bitstream `.bit` 50MB thành công
- Admin thấy hết session, kick được session bất kỳ
- Maintenance mode → device không bookable

## Milestone 7 — Polish + Pilot (Tuần 13-14)

**Goal**: Hệ thống production-ready + pilot 20 SV.

### Phần 7.A: Polish (Tuần 13)
- [ ] Setup Uptime Kuma trong LXC `lab-monitor`
- [ ] Email notification: booking confirm, reminder 30 phút trước, session ended
- [ ] HTTPS production với Caddy auto Let's Encrypt
- [ ] Backup: cron daily `pg_dump` + Proxmox snapshot
- [ ] Performance test: 30 concurrent users, đo response time
- [ ] Security scan: `trivy` cho Docker images
- [ ] Tài liệu user guide 1 trang cho SV (`docs/user-guide-sv.pdf`)
- [ ] Tài liệu user guide 1 trang cho lecturer (`docs/user-guide-gv.pdf`)

### Phần 7.B: Pilot (Tuần 14)
- [ ] Onboard 1 lớp 20 SV thật + 1 lecturer thật
- [ ] Theo dõi log + feedback hàng ngày
- [ ] Hot-fix bugs phát sinh
- [ ] Họp retrospective với SV + lecturer cuối tuần
- [ ] Viết post-mortem + lessons learned

**Definition of Done**:
- Site live trên `https://lab.vju.edu.vn` với certificate hợp lệ
- ≥ 80% SV book + connect thành công không cần hỗ trợ
- Lecturer setup class trong < 15 phút
- Uptime ≥ 95%
- Document hết các issue và workaround
- Decision: GA hay tiếp tục sửa

## Anti-pattern cần tránh

Claude Code, KHÔNG làm những điều này:

❌ **Tự cài thêm framework không có trong stack** (vd cài Vue cùng với Next.js)
❌ **Hardcode credential** vào source — luôn qua env var
❌ **Skip migration** chỉ dùng `Base.metadata.create_all()` ở prod
❌ **Disable HTTPS** vì "test cho nhanh" — luôn có local HTTPS qua mkcert
❌ **Tự ý merge vào main** mà không có code review của thầy
❌ **Tạo admin user qua API endpoint** — chỉ qua seed script hoặc CLI
❌ **Lưu private SSH key vào DB** — chỉ lưu public key
❌ **Mở port DB ra Internet** — DB chỉ lắng nghe trong Docker network nội bộ container
❌ **Skip access control check** — SV book device PHẢI qua check class+enrollment+device_assignment
❌ **Cài thư viện đã deprecate** — check release date trước khi pin version
❌ **Quên error handling** ở mọi external call (SSH, plug API, OIDC)

## Khi gặp vấn đề

Claude Code, khi gặp situation không có trong tài liệu:

1. **Thử search tài liệu**: re-read `02-architecture.md`, `10-access-control.md` xem có hint không
2. **Đề xuất 2-3 phương án** cho thầy chọn, kèm trade-off
3. **Implement tạm với TODO comment** + log vào `docs/decisions.md` (ADR pattern)
4. **Không tự ý** thay đổi schema, đổi auth provider, đổi major dependency

## Tracking progress

Cuối mỗi milestone, update bảng dưới:

| Milestone | Status | Branch | Merged date | Notes |
|---|---|---|---|---|
| M0 Bootstrap | ⬜ Pending | - | - | - |
| M1 Infra+Auth | ⬜ Pending | - | - | - |
| M2 Device+Class | ⬜ Pending | - | - | - |
| M2.5 Teacher Dashboard | ⬜ Pending | - | - | - |
| M3 Booking+ACL | ⬜ Pending | - | - | - |
| M4 SSH | ⬜ Pending | - | - | - |
| M5 Plug | ⬜ Pending | - | - | - |
| M6 File+Admin | ⬜ Pending | - | - | - |
| M7 Polish+Pilot | ⬜ Pending | - | - | - |
