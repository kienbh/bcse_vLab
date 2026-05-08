# M1 Roadmap — VPS infra + Auth (deployment variant)

Following ADR-0011, M1 trên SV14/SV08 hơi khác `docs/05-implementation-plan.md` gốc.
Kế thừa: M0 đã deploy frontend/backend skeleton + 9 container Docker stack, UI shell
với 5 pages live (`/`, `/login`, `/dashboard`, `/devices`, `/bookings`).

## M1 deliverables

### 1.A — Hạ tầng (đã làm phần lớn ở M0, còn 3 việc)
- [x] SV14 base setup (Docker, UFW, swap)
- [x] SV08 nginx ingress vhost
- [x] CF Tunnel + DNS
- [ ] **Tạo subdomain `auth.sv14.bcse-vju.com`** (CNAME + Tunnel rule + nginx vhost)
- [ ] **Daily `pg_dump` cron** trên SV14 (script đã có ở `infrastructure/sv14/backup.sh`)
- [ ] **Off-site backup**: rsync hoặc upload S3-compatible

### 1.B — Auth (Authentik OIDC)
- [ ] Authentik first-login với `AUTHENTIK_BOOTSTRAP_PASSWORD` (xem `.env.prod` trên SV14)
- [ ] Tạo OIDC provider trong Authentik UI:
  - name: `labportal`
  - signing key: ed25519 (auto-generate)
  - redirect URIs: `https://sv14.bcse-vju.com/api/auth/callback`
  - scope: `openid email profile`
- [ ] Tạo Application liên kết với provider
- [ ] Setup Google OAuth source nếu trường có (Sources → Google) — optional, có thể dùng email/password local trước
- [ ] Update `OIDC_CLIENT_ID` + `OIDC_CLIENT_SECRET` trong `.env.prod` của backend
- [ ] Restrict email domain ở Authentik flow: `@st.vju.ac.vn` cho student, `@vju.ac.vn` cho lecturer

### 1.C — Backend auth flow
- [ ] `app/api/routes/auth.py` — endpoints:
  - `GET /api/auth/login` → 302 → Authentik authorize URL với `state` + PKCE
  - `GET /api/auth/callback?code=...&state=...` → exchange code → fetch user info → upsert user in DB → set httpOnly JWT cookie
  - `GET /api/auth/me` → return current user from JWT
  - `POST /api/auth/logout` → clear cookie + redirect Authentik logout
- [ ] `app/services/auth.py` — Authlib OIDC client + JWT issuer
- [ ] `app/middleware/auth.py` — dependency `get_current_user(request)` raise 401 if no JWT
- [ ] Rate limit: `slowapi` 5/min cho login

### 1.D — Database schema migration 0001
Theo `docs/04-database-schema.md`:
- [ ] `app/models/__init__.py` — import all models
- [ ] `app/models/user.py` — `users` (UUID, role enum, oidc_subject, student_code, ...)
- [ ] `app/models/device.py` — `devices` + `plug_mappings` + `device_credentials`
- [ ] `app/models/class_.py` — `classes` + `enrollments` + `class_device_assignments`
- [ ] `app/models/access.py` — `special_access`
- [ ] `app/models/booking.py` — `bookings` + `sessions` + GIST EXCLUDE constraint
- [ ] `app/models/audit.py` — `audit_logs`
- [ ] `app/models/quota.py` — `user_quotas`
- [ ] Alembic `0001_initial_schema.py` migration
- [ ] `scripts/seed.py` — 1 admin, 1 lecturer, 5 mock students, 9 mock KV260

### 1.E — Frontend auth integration
- [ ] `frontend/src/lib/auth.ts` — wrapper `useUser()` (TanStack Query) hits `/api/auth/me`
- [ ] Update `/login` page — redirect tới `/api/auth/login`
- [ ] Update TopNav — show "Sign in" if no user, show user menu (dropdown logout) nếu có
- [ ] Protect `/dashboard`, `/bookings` (client-side redirect tới `/login` nếu chưa auth)

### 1.F — Definition of Done
- [ ] Click "Đăng nhập với VJU SSO" → redirect Authentik → login với mock account → redirect về portal → user info hiển thị
- [ ] F5 giữ session (httpOnly cookie + refresh token)
- [ ] Logout clears both Authentik session + portal cookie
- [ ] User row trong DB sau lần login đầu tiên (auto-upsert)
- [ ] Lecturer vs Student thấy menu khác (admin vs student dashboard placeholder)
- [ ] Test auth middleware: 401 nếu không có JWT
- [ ] CI green

## Estimated effort
~ 5-7 ngày (theo plan gốc Tuần 2-3 = 14 ngày, nhưng M0 đã preload UI shell + nhiều scaffolding).

## Risks
- **Authentik subpath issue (đã gặp)**: phải dùng subdomain. Giải bằng CF Tunnel rule mới + nginx vhost mới.
- **DB schema phức tạp**: 11 bảng + GIST EXCLUDE. Cần `btree_gist` extension (đã có trong `init-extensions.sql`).
- **OIDC state/PKCE**: dùng `authlib` thay vì tự code để tránh bug security.

## Next milestone after M1
- M2: Device + Class CRUD (admin/lecturer)
- M2.5: Teacher dashboard
- M3: Booking + access_control.py (cốt lõi business logic)
