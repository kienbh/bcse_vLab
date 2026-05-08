# 08 — Security Checklist

Checklist này phải pass HẾT trước khi go-live cho sinh viên.

## Authentication

- [ ] **Không hardcode credentials** — mọi secret qua env var
- [ ] **JWT secret ≥ 64 chars** ngẫu nhiên
- [ ] **JWT lifetime ≤ 1h**, refresh token ≤ 7 ngày
- [ ] **Cookie httpOnly + Secure + SameSite=Strict** cho session
- [ ] **OIDC state parameter** verify để chống CSRF
- [ ] **MFA cho admin** (Authentik hỗ trợ TOTP)
- [ ] **MFA cho lecturer** (recommended)
- [ ] **Account lockout**: 5 fail login → block 15 phút

## Authorization (đặc biệt quan trọng cho project này)

- [ ] **Role check ở từng endpoint**, không tin tưởng JWT claim mà không check DB
- [ ] **Owner check** cho resource user-scoped (booking, session)
- [ ] **Access control gate** cho mọi booking action — check qua `access_control.py`
- [ ] **Lecturer scope check**: lecturer chỉ xem được session của SV trong lớp mình
- [ ] **Admin endpoint** có dedicated middleware
- [ ] **Default deny**: API mới phải explicitly khai báo public hay không
- [ ] **No privilege escalation**: SV không thể tự upgrade role qua API
- [ ] **Test access control**: 100% coverage cho `can_user_book_device`
- [ ] **Time window enforce**: validate slot trong allowed_time_windows

## SSH Key Management

- [ ] **Ephemeral keys**: mỗi session 1 key pair riêng, ed25519
- [ ] **Private key NEVER lưu DB** — sinh và trả về 1 lần
- [ ] **Public key có expiration** trong comment
- [ ] **Cleanup job** chạy mỗi 5 phút, remove expired keys
- [ ] **Backend admin key** lưu encrypted (AES-256-GCM)
- [ ] **Key rotation** plan: rotate backend admin key mỗi 90 ngày

## Network Security (Proxmox-specific)

- [ ] **Devices KHÔNG có IP public**
- [ ] **Chỉ `lab-proxy` exposed** ra Internet (port 80/443)
- [ ] **LXC khác không có public IP** — chỉ trong vmbr1 internal
- [ ] **Devices outbound deny** Internet
- [ ] **Proxmox host firewall**: chỉ open 22 + 8006 (UI)
- [ ] **DB không expose** ra ngoài LXC `lab-db`
- [ ] **Redis có password** + chỉ trong vmbr1
- [ ] **Authentik không expose port 9000 trực tiếp**

## TLS/HTTPS

- [ ] HTTPS only, redirect 80→443
- [ ] HSTS max-age ≥ 1 năm
- [ ] TLS 1.3 ưu tiên
- [ ] Certificate auto-renew (Let's Encrypt)
- [ ] CSP header restrictive

## Input Validation

- [ ] Pydantic schema mọi request body
- [ ] SQL injection không thể (dùng ORM)
- [ ] XSS prevention
- [ ] Path traversal: validate upload path
- [ ] CSV upload: validate header, escape, check size
- [ ] File whitelist extension
- [ ] File size limit 100MB
- [ ] Filename sanitize

## Rate Limiting

- [ ] Login: 5/phút/IP
- [ ] API tổng: 100/phút/user
- [ ] Reset device: 3/phút/user
- [ ] File upload: 10/giờ/user
- [ ] CSV enroll: 10/giờ/lecturer

## Audit Logging

- [ ] Mọi auth event
- [ ] Mọi resource mutation
- [ ] Access control events (grant, revoke)
- [ ] Session events (start, end, kick, observe)
- [ ] Power actions
- [ ] Log retention ≥ 1 năm
- [ ] Log immutable (append-only)

## Secrets Management

- [ ] `.env.prod` không commit
- [ ] gitleaks trong CI
- [ ] No secret in logs
- [ ] Rotation plan documented
- [ ] Proxmox root password mạnh

## Container Security

- [ ] LXC unprivileged
- [ ] Docker image base nhỏ (alpine/slim)
- [ ] Non-root user trong Docker
- [ ] Read-only filesystem
- [ ] No privileged mode
- [ ] Trivy scan trong CI
- [ ] Image pinned by digest ở prod

## Database

- [ ] Backup encrypted
- [ ] DB user app quyền tối thiểu
- [ ] Prepared statements
- [ ] Connection pool limit
- [ ] PII encrypt at rest (nếu compliance)

## Operational

- [ ] Incident playbook
- [ ] Contact list
- [ ] Status page (Uptime Kuma public)
- [ ] Kill switch admin endpoint
- [ ] RTO < 4h, RPO < 24h
- [ ] Proxmox snapshot weekly

## Pen-test light

- [ ] SQL injection trong login
- [ ] File `.sh` rename thành `.bit`
- [ ] Truy cập booking user khác bằng đoán UUID
- [ ] Book device không thuộc class của mình
- [ ] Reset device không trong booking
- [ ] Lecturer A access session lớp lecturer B
- [ ] Spam reset 100 lần
- [ ] JWT expired còn dùng được?
- [ ] Booking với negative duration
- [ ] Booking ngoài time window
- [ ] Upload 1GB file
- [ ] Concurrent booking same slot
- [ ] Chỉnh DOM force admin button
- [ ] CSV với 10000 dòng
- [ ] CSV email injection

## Go/no-go criteria

✅ Go-live khi:
- Tất cả checkbox trên pass
- 0 high/critical CVE
- Pen-test light pass
- Backup + restore drill thành công
- Access control test coverage ≥ 90%

❌ KHÔNG go-live nếu:
- TODO hardcoded credentials
- HTTP only
- Audit log không hoạt động
- DB chưa backup tự động
- Access control chưa test đầy đủ
