# 14 — Cơ chế trả permission sau khi Connect (Gateway Access Flow)

**Status**: Shipped (M5.8 → M5.9, 05/2026)
**Phụ thuộc**: [ADR-0013](./13-gateway-redesign.md) — quyết định kiến trúc
**Mục đích**: Mô tả **chính xác** code đang chạy production sau khi sinh viên book slot, được approve, và bấm nút **Connect**. Đọc file này khi cần debug, sửa endpoint, hoặc thêm field mới vào payload.

> **Cảnh báo**: đây là tài liệu *mô tả hiện trạng*, không phải decision record. Nếu thấy mâu thuẫn với code, code đúng → mở PR sửa file này.

---

## 0. Tóm tắt 1 đoạn

Sau khi SV bấm **Connect** trên `/bookings`, frontend gọi `POST /api/bookings/{id}/access`. Backend kiểm tra ownership + thời gian, mint 1 password 12 ký tự (bcrypt-hash vào DB, plaintext trả về **đúng 1 lần**), và trả JSON gồm: `password`, `ssh_command` paste-ready, thông tin gateway (`jump_host`/`jump_port`/`ssh_username`), thông tin kit (`target_*` — info-only), lifecycle (`expires_at`, `issued_at`, `regenerate_count`). Modal `SessionLaunchModal` hiển thị 2 thứ user thật sự dùng: **password** và **lệnh SSH**. Mọi thứ khác để debug / MobaXterm hint.

---

## 1. Sơ đồ luồng

```
SV (browser)              Backend (SV14)              Gateway jump host
─────────────             ──────────────              ───────────────────
[Connect] ─POST /bookings/{id}/access─►
                          ▼
                   _load_booking_for_owner()     ← check user_id == booking.user_id
                   _validate_booking_window()    ← scheduled|active + grace 5'
                          ▼
                   gateway_credentials.issue_for_booking()
                          ├─ random password (12 chars, secrets.token_urlsafe)
                          ├─ bcrypt hash → gateway_sessions.password_hash
                          ├─ booking.status: scheduled → active
                          └─ audit_log("gateway.access.issue")
                          ▼
       ◄── 200 OK ── AccessIssueResponse(password=<plaintext>, ssh_command=..., ...)
                          ▼
[SessionLaunchModal mở]
  ↳ Copy password
  ↳ Copy ssh_command "ssh -p 2222 vlab@ssh.bcse-vju.com"
  ↳ Paste vào terminal/MobaXterm ─────────────────────────► sshd:2222
                                                              ▼
                                                          PAM script
                                                              │
                              POST /api/gateway/auth ◄────────┤  (X-Gateway-Secret)
                          ▼
                   verify_password() bcrypt scan
                   ─ session.last_auth_at = now
                          ▼
       ◄── 200 {ok:true, target_user, target_host, target_port} ─►
                                                              ▼
                                                       ForceCommand vlab-jump.sh
                                                              │
                          POST /api/gateway/resolve-target ◄──┤
                          ▼
                   query session by username+client_ip in last 60s
                          ▼
       ◄── 200 {target_host, target_port, target_user} ──────►
                                                              ▼
                          POST /api/gateway/session-start ◄───┤  (pid, pty)
                                                              ▼
                                                       ssh -i admin_key
                                                            target_user@kit
                                                              ▼
                                                       [user trong shell kit]
```

---

## 2. Endpoint chi tiết

### 2.1 `POST /api/bookings/{id}/access` — Issue/rotate password

**Code**: [`backend/app/api/routes/gateway.py:191`](../backend/app/api/routes/gateway.py)

**Auth**: cookie JWT (booking owner only).

**Gate trước khi mint**:

| Check | Code | HTTP nếu fail |
|---|---|---|
| Booking tồn tại và thuộc caller | `_load_booking_for_owner()` | `404 BOOKING_NOT_FOUND` |
| Status ∈ {scheduled, active} | `_validate_booking_window()` | `409 BOOKING_NOT_ACTIVATABLE` |
| Chưa quá sớm (>5 phút trước start) | `_validate_booking_window()` | `425 BOOKING_NOT_STARTED_YET` |
| Chưa quá hạn (>= end_time) | `_validate_booking_window()` | `410 BOOKING_EXPIRED` |
| Device tồn tại | `_issue_or_rotate()` | `404 DEVICE_NOT_FOUND` |

**Side effect khi thành công**:
- Sinh password mới (hoặc tái sử dụng nếu đã có session active — xem `issue_for_booking`)
- `gateway_sessions` row được tạo/update với `password_hash`, `target_user`, `target_host`, `target_port`, `expires_at = booking.end_time`
- `booking.status`: `scheduled` → `active`
- Audit log entry `gateway.access.issue` (hoặc `gateway.access.regenerate`)

### 2.2 Payload `AccessIssueResponse`

**Code**: [`backend/app/api/routes/gateway.py:49`](../backend/app/api/routes/gateway.py)

```python
class AccessIssueResponse(BaseModel):
    session_id: str         # UUID phiên gateway
    password: str           # PLAINTEXT — chỉ trả về 1 lần ở response này
    ssh_username: str       # "vlab" (account trên gateway, fix qua settings)
    jump_host: str          # "ssh.bcse-vju.com" (settings.JUMP_HOST_PUBLIC)
    jump_port: int          # 2222 (settings.JUMP_HOST_PUBLIC_PORT)
    target_user: str        # User trên kit ("pi" / "student" / ...)
    target_host: str        # IP nội bộ kit (info-only, FE không dùng để SSH)
    target_port: int        # SSH port kit (mặc định 22)
    ssh_command: str        # "ssh -p 2222 vlab@ssh.bcse-vju.com" — paste-ready
    expires_at: datetime    # == booking.end_time
    issued_at: datetime
    regenerate_count: int   # 0 lần đầu, +1 mỗi lần rotate
```

**Quan trọng — Pattern B**:
- `ssh_command` **không có `-J`** và **không có thông tin kit**. User chỉ thấy gateway. Sau khi vào gateway, ForceCommand wrapper `vlab-jump.sh` mới tự nhảy vào kit bằng admin key (backend-managed).
- `target_*` trả về để FE *hiển thị* cho user biết "đang vào kit nào", nhưng user không cần copy/paste những thông tin này.

### 2.3 Các endpoint kèm theo

| Method | Path | Mục đích | Response |
|---|---|---|---|
| `POST` | `/bookings/{id}/access/regenerate` | Force rotate — password cũ vô hiệu ngay | `AccessIssueResponse` (password mới) |
| `GET` | `/bookings/{id}/access` | Đọc metadata (KHÔNG có password) | `AccessInfoResponse` |
| `DELETE` | `/bookings/{id}/access` | User chủ động revoke | `{status: "revoked", session_id}` |

`AccessInfoResponse` giống `AccessIssueResponse` nhưng **bỏ field `password`** và thêm `last_auth_at`, `revoked_at`, `ssh_command_template`. Dùng để hiển thị "phiên đã cấp lúc nào, lần auth gần nhất" trên các trang lịch sử.

---

## 3. Frontend — `SessionLaunchModal`

**Code**: [`frontend/src/components/BookingModal.tsx:316`](../frontend/src/components/BookingModal.tsx)

### 3.1 Cách trigger

Trang `/bookings` ([`frontend/src/app/bookings/page.tsx:164`](../frontend/src/app/bookings/page.tsx)):

```ts
const r = await fetch(`${API}/bookings/${id}/access`, {
  method: "POST",
  credentials: "include",
});
// Wrapper try/catch + retry 1 lần sau 600ms cho NETWORK / HTTP 5xx
// (commit ead7ba6 — hardening transient errors)
```

Khi thành công: `setSessionOpen({ data, bookingId })` → mount `SessionLaunchModal`.

### 3.2 Cấu trúc modal (4 phần)

| # | Phần | Field FE dùng | Ghi chú |
|---|---|---|---|
| 1 | **Password** | `password` | Input mono, viền emerald nổi bật. Hiện/Ẩn + Copy. Click = select-all. |
| 2 | **SSH command** | `ssh_command` | Pre-formatted, copy 1 click. |
| 3 | **MobaXterm hint** (collapse) | `jump_host`, `jump_port`, `ssh_username` | Điền sẵn cho user kéo vào dialog "Session → SSH" của MobaXterm. |
| 4 | **Lifecycle warning** | `expires_at`, `regenerate_count` | Cảnh báo: hết slot → gateway chặn auth, kill phiên trong 30s, banner 5 phút trước. |

### 3.3 Regenerate

Nút **Regenerate password** ở cuối modal → `POST /access/regenerate` → modal update password mới in-place qua `onSessionReplaced` callback. Confirm dialog ngăn rotate nhầm.

### 3.4 Auto-transition (M5.9)

Trang `/bookings` chạy `setInterval` 20s để re-evaluate `canConnect` / `showLockedConnect`. Khi slot vừa bắt đầu, nút Connect tự chuyển từ "Chưa tới giờ" → clickable trong vòng 20s mà không cần F5 ([commit e07eae9](../backend/app/api/routes/devices.py)).

---

## 4. Phía gateway — Xác thực và kết nối kit

### 4.1 PAM auth (sshd → backend)

**Code**: [`backend/app/api/routes/gateway.py:339`](../backend/app/api/routes/gateway.py) — `POST /api/gateway/auth`

**Auth giữa gateway và backend**: header `X-Gateway-Secret: <settings.GATEWAY_SHARED_SECRET>`. Hosts không có secret → 401 ngay, không reach tới bcrypt scan.

**Body**:
```json
{
  "username": "vlab",
  "password": "<plaintext SV gõ>",
  "client_ip": "1.2.3.4"
}
```

**Logic**: backend bcrypt-verify password với mọi `gateway_session` đang active (`expires_at > now`, `revoked_at IS NULL`). Match → set `last_auth_at = now` + trả về `target_*`. Pam script chỉ kiểm tra `ok==true` qua `jq`.

**Response (ok)**:
```json
{
  "ok": true,
  "session_id": "...",
  "target_user": "pi",
  "target_host": "192.168.1.42",
  "target_port": 22,
  "expires_at": "2026-05-22T15:00:00Z"
}
```

Failure (kể cả `bad_secret`) trả `ok: false` và được log qua `log_attempt()`.

### 4.2 Resolve target (ForceCommand → backend)

**Code**: [`backend/app/api/routes/gateway.py:387`](../backend/app/api/routes/gateway.py) — `POST /api/gateway/resolve-target`

Sau khi PAM pass, ForceCommand wrapper `vlab-jump.sh` chưa biết target nào. Nó gọi resolve-target với `username + client_ip`. Backend tìm session có `last_auth_at` trong **60 giây gần nhất**, khớp username (+ optional `session_id` nếu PAM lưu vào env). Trả về `target_host`/`target_port`/`target_user` → wrapper chạy `ssh -i /etc/vlab/admin_key target_user@target_host -p target_port`.

### 4.3 Session lifecycle hooks

| Hook | Khi nào | Side effect |
|---|---|---|
| `POST /api/gateway/session-start` | sshd accept_pty hook | Ghi `active_pid`, `pty_path` → janitor có thể `kill` |
| `POST /api/gateway/session-end` | sshd disconnect hook | Cộng `bytes_in/out`, clear `active_pid` |
| Janitor (M5.8) | Cron mỗi 30s | Quét sessions có `expires_at < now` → revoke + `kill -TERM` PID + ghi audit |

---

## 5. Bảng so sánh "user nhận gì" vs "backend dùng gì"

| Field trả về | User cần | Backend cần | Hiển thị FE |
|---|---|---|---|
| `password` | ✅ paste khi sshd hỏi | ❌ (đã hash) | Input mono lớn |
| `ssh_command` | ✅ paste vào terminal | ❌ | Pre block, copy 1 click |
| `jump_host` | ⚠ (đã có trong `ssh_command`) | ❌ | MobaXterm hint |
| `jump_port` | ⚠ (đã có trong `ssh_command`) | ❌ | MobaXterm hint |
| `ssh_username` | ⚠ (đã có trong `ssh_command`) | ❌ | MobaXterm hint |
| `target_user` | ℹ info "vào kit nào" | ✅ resolve-target | Header modal `pi@192.168...` |
| `target_host` | ℹ info | ✅ resolve-target | Header modal |
| `target_port` | ℹ info | ✅ resolve-target | Ẩn |
| `session_id` | ❌ | ✅ session-start/end | Ẩn |
| `expires_at` | ✅ biết khi nào hết | ✅ janitor | "Hết slot: DD/MM HH:mm" |
| `regenerate_count` | ℹ debug | ❌ | Badge "đã regenerate N lần" nếu > 0 |
| `issued_at` | ℹ debug | ✅ audit | Ẩn (chỉ GET dùng) |

**Quy tắc**: user chỉ cần 2 thứ — **password** và **ssh_command**. Mọi thứ khác là chú thích.

---

## 6. Test plan tham chiếu

| Scenario | File test | Đã pass M5.9 |
|---|---|---|
| Issue password lần đầu | `backend/tests/test_gateway_access.py::test_issue_first_time` | ✅ |
| Re-issue trả về session cũ (không rotate) | `…::test_issue_returns_existing` | ✅ |
| Regenerate rotate password mới | `…::test_regenerate_rotates` | ✅ |
| Past start_time + grace 5' | `…::test_issue_too_early_blocked` | ✅ |
| End-to-end PAM auth | `backend/tests/test_gateway_auth.py` | ✅ |
| Slot-expiry force-quit | [commit 3a46f0f](../backend/tests/test_janitor_smoke.py) | ✅ |

---

## 7. Khi nào cần update file này

- Thêm/xoá field trong `AccessIssueResponse` → cập nhật bảng §2.2 và §5
- Đổi endpoint path → cập nhật §2 và sơ đồ §1
- Đổi Pattern B sang Pattern khác (vd: dùng lại ssh -J, hay wetty) → cần ADR mới, KHÔNG sửa file này; mark deprecated thay vì viết đè

**Liên quan**:
- ADR gốc: [`docs/13-gateway-redesign.md`](./13-gateway-redesign.md)
- Access control upstream (ai được book): [`docs/10-access-control.md`](./10-access-control.md)
- Schema `gateway_sessions`: [`docs/04-database-schema.md`](./04-database-schema.md)
- API spec full: [`docs/06-api-spec.md`](./06-api-spec.md)
