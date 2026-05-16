# ADR-0013 — Gateway Redesign: SSH ProxyJump với password per-session

**Status**: Accepted (2026-05)
**Supersedes**: M4 wetty + ed25519 approach
**Authors**: Thầy Kiên + Claude (planning)

---

## TL;DR cho Claude Code

Trước khi đụng vào bất kỳ file nào, đọc trọn ADR này. Nếu thấy mâu thuẫn với code cũ (đặc biệt là `services/ssh_manager.py`, `wetty` service, `/api/sessions/provision/*`), **code cũ sai, ADR đúng**. Xoá/viết lại theo đây.

Triết lý 1 câu: *"Nền tảng chỉ cung cấp đường nối từ máy user → SV14 (gateway) → kit. Web để đặt lịch và phát password. SSH client của user làm phần còn lại."*

KHÔNG làm những thứ sau (đã làm rồi thì xoá):
- ❌ Wetty / web terminal trong browser
- ❌ Phát ed25519 keypair cho user (kể cả "copy private key vào clipboard")
- ❌ Yêu cầu user import file `.pem` / `.ppk` vào MobaXterm
- ❌ Bất kỳ shell access nào trên SV14 cho user (chỉ forward)

PHẢI làm:
- ✅ User đặt lịch → đến giờ click "Get access" → web hiện **1 password ngắn** + lệnh SSH copy-paste
- ✅ User SSH từ máy họ (MobaXterm/PuTTY/ssh CLI) qua SV14 (ProxyJump) tới kit
- ✅ Password hết hạn đúng `end_time` của booking
- ✅ Worker kill session đang chạy khi hết giờ, có banner cảnh báo 5 phút trước

---

## 1. Kiến trúc mới

```
SV ở nhà (bất kỳ đâu có Internet)
   │
   │  ssh -J vlab@sv14.bcse-vju.com  pi@kit-03
   │  (MobaXterm: Jump host = sv14, Remote = kit-03)
   │  Password prompt #1: a7k9-bm4q-x2nz   ← từ DB lookup
   │  Password prompt #2: (none — SV14 → kit dùng key cố định)
   ▼
┌──────────────────────────────────────────────────┐
│ SV14 — Gateway (sshd hardened)                   │
│                                                  │
│  • Linux user duy nhất: `vlab` (no shell)        │
│  • PAM module gọi backend /api/gateway/auth      │
│  • ForceCommand: chỉ cho ProxyJump, không shell  │
│  • Backend giữ SSH key đi vào pool kit           │
│  • Worker tick mỗi 30s: kill session hết hạn     │
└──────────────────────────────────────────────────┘
   │
   │  SSH (key auth, IP allowlist)
   ▼
Pool kit ở Hoà Lạc: kit-01..kit-N
   • Mỗi kit có account `pi` / `student` cố định
   • authorized_keys chỉ chứa public key của SV14 backend
   • Không expose ra Internet
```

**Vì sao ProxyJump (chứ không phải bastion 2-hop)**:
- User chỉ gõ password 1 lần
- SV14 không cần cấp shell → ít attack surface
- MobaXterm/OpenSSH native support, không phải dạy SV gì nhiều

---

## 2. Thay đổi DB schema

Migration `0003_gateway_sessions.sql`:

```sql
-- Bảng mới: lưu password per-session (bcrypt hash, không bao giờ lưu plaintext)
CREATE TABLE gateway_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id      UUID NOT NULL UNIQUE REFERENCES bookings(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id),
    device_id       UUID NOT NULL REFERENCES devices(id),

    -- Định danh user phía SSH (luôn là 'vlab' trong M4-redesign, để mở cho tương lai)
    ssh_username    TEXT NOT NULL DEFAULT 'vlab',

    -- bcrypt hash của password 12 ký tự dạng xxxx-xxxx-xxxx
    password_hash   TEXT NOT NULL,

    -- Lifecycle
    issued_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL,       -- = bookings.end_time
    revoked_at      TIMESTAMPTZ,                -- null = còn dùng được
    last_auth_at    TIMESTAMPTZ,                -- update mỗi lần PAM gọi auth thành công

    -- Forwarding target: SV14 sẽ ProxyJump tới đây
    target_host     INET NOT NULL,              -- IP kit trong 192.168.20.0/24
    target_port     INTEGER NOT NULL DEFAULT 22,
    target_user     TEXT NOT NULL,              -- 'pi' / 'student' / 'root' tuỳ kit

    -- Audit
    client_ip       INET,                       -- IP user kết nối lần cuối
    bytes_in        BIGINT DEFAULT 0,
    bytes_out       BIGINT DEFAULT 0
);

CREATE INDEX idx_gateway_sessions_active
    ON gateway_sessions (expires_at)
    WHERE revoked_at IS NULL;

CREATE INDEX idx_gateway_sessions_booking ON gateway_sessions (booking_id);

-- Audit table cho mỗi lần auth attempt qua gateway
CREATE TABLE gateway_auth_log (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    booking_id      UUID,
    user_id         UUID,
    client_ip       INET,
    outcome         TEXT NOT NULL,              -- 'ok', 'expired', 'wrong_password', 'revoked', 'no_booking'
    reason          TEXT
);

CREATE INDEX idx_gateway_auth_log_ts ON gateway_auth_log (ts DESC);
```

**Lưu ý**: `gateway_sessions` thay thế vai trò của bảng `ssh_sessions` cũ (nếu có). Migrate dữ liệu cũ sang hoặc drop nếu mock data, hỏi thầy trước.

---

## 3. Backend changes

### 3.1. Service mới: `services/gateway_credentials.py`

```python
# Pseudocode — implement đầy đủ
import secrets, bcrypt
from datetime import datetime, timezone

PASSWORD_ALPHABET = "abcdefghkmnpqrstuvwxyz23456789"  # bỏ 0/o/1/l/i để dễ đọc

def generate_password() -> str:
    """Sinh password 12 ký tự dạng xxxx-xxxx-xxxx."""
    groups = [
        "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(4))
        for _ in range(3)
    ]
    return "-".join(groups)

def issue_gateway_session(db, booking) -> tuple[str, GatewaySession]:
    """
    Gọi khi user click 'Get access' và booking đang active.
    Trả về (plaintext_password, session_record).
    Password chỉ tồn tại trong memory của response này — không log, không lưu.
    """
    plaintext = generate_password()
    pw_hash = bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt(rounds=12)).decode()

    session = GatewaySession(
        booking_id=booking.id,
        user_id=booking.user_id,
        device_id=booking.device_id,
        password_hash=pw_hash,
        expires_at=booking.end_time,
        target_host=booking.device.lan_ip,
        target_port=booking.device.ssh_port,
        target_user=booking.device.ssh_user,
    )
    db.add(session)
    db.commit()
    return plaintext, session


def verify_password(db, attempted_password: str, client_ip: str) -> GatewaySession | None:
    """
    Gọi từ endpoint /api/gateway/auth (PAM trên SV14 gọi vào).
    Quét các session còn hạn, bcrypt.checkpw từng cái.
    Trả về session nếu match, None nếu không.

    Performance note: với <100 booking active đồng thời thì OK.
    Nếu lên 1000+, thêm prefix lookup (lưu thêm 4 ký tự đầu của password).
    """
    now = datetime.now(timezone.utc)
    candidates = db.query(GatewaySession).filter(
        GatewaySession.expires_at > now,
        GatewaySession.revoked_at.is_(None),
    ).all()

    for s in candidates:
        if bcrypt.checkpw(attempted_password.encode(), s.password_hash.encode()):
            s.last_auth_at = now
            s.client_ip = client_ip
            db.commit()
            log_auth(db, s.booking_id, s.user_id, client_ip, "ok")
            return s

    log_auth(db, None, None, client_ip, "wrong_password")
    return None
```

### 3.2. Endpoints mới / sửa

| Method | Path | Auth | Mô tả |
|---|---|---|---|
| POST | `/api/bookings/{id}/access` | booking owner | Replace `sessions/provision`. Trả `{password, ssh_command, expires_at, target_user, target_host}` — password chỉ trả 1 lần |
| GET | `/api/bookings/{id}/access` | booking owner | Xem lại info (KHÔNG có password — show "đã cấp, regenerate?") |
| POST | `/api/bookings/{id}/access/regenerate` | booking owner | Revoke session cũ + cấp password mới |
| POST | `/api/gateway/auth` | internal (shared secret hoặc unix socket) | PAM gọi: `{username, password, client_ip}` → `200 {target_host, target_port, target_user, session_id}` hoặc `401` |
| POST | `/api/gateway/session-start` | internal | sshd báo session bắt đầu (để worker track PID) |
| POST | `/api/gateway/session-end` | internal | sshd báo session kết thúc |
| GET | `/api/sessions/active` | role-scoped | Giữ nguyên, query `gateway_sessions` thay vì bảng cũ |
| POST | `/api/sessions/{id}/kick` | lecturer/admin | Set `revoked_at = now()` + signal worker kill |

### 3.3. Xoá / deprecate

- ❌ `POST /api/sessions/provision/{booking_id}` — bỏ
- ❌ `services/ssh_manager.py` (phần ed25519 keypair gen cho user) — bỏ
- ❌ Service `wetty` trong `docker-compose.yml` — bỏ
- ❌ Frontend: nút "Connect" mở wetty + copy private key — viết lại

---

## 4. SV14 sshd setup

### 4.1. PAM auth via backend

File `/etc/pam.d/sshd-vlab`:
```
auth    required   pam_exec.so   expose_authtok   /usr/local/bin/vlab-pam-auth.sh
account required   pam_permit.so
session required   pam_permit.so
```

Script `/usr/local/bin/vlab-pam-auth.sh`:
```bash
#!/bin/bash
# Read password from stdin (pam_exec expose_authtok), POST to backend
PASSWORD=$(cat)
CLIENT_IP="${PAM_RHOST:-unknown}"

RESPONSE=$(curl -sS --max-time 3 -X POST \
    -H "Content-Type: application/json" \
    -H "X-Gateway-Secret: ${GATEWAY_SHARED_SECRET}" \
    -d "{\"username\":\"${PAM_USER}\",\"password\":\"${PASSWORD}\",\"client_ip\":\"${CLIENT_IP}\"}" \
    http://backend:8000/api/gateway/auth)

if [ "$?" -ne 0 ]; then exit 1; fi
echo "$RESPONSE" | jq -e '.ok == true' > /dev/null && exit 0 || exit 1
```

### 4.2. sshd_config snippet (Match block cho user `vlab`)

```
Match User vlab
    PasswordAuthentication yes
    PubkeyAuthentication no
    AuthenticationMethods password
    UsePAM yes
    AuthorizedKeysFile /dev/null

    # User không có shell, chỉ làm ProxyJump
    PermitTTY no
    X11Forwarding no
    AllowTcpForwarding yes
    PermitOpen 192.168.20.0/24:22

    # ForceCommand đọc target từ backend rồi exec ssh tới kit
    ForceCommand /usr/local/bin/vlab-jump.sh
```

Script `/usr/local/bin/vlab-jump.sh`:
```bash
#!/bin/bash
# Lookup target từ backend dựa trên session vừa auth
TARGET=$(curl -sS http://backend:8000/api/gateway/resolve-target \
    -H "X-Gateway-Secret: ${GATEWAY_SHARED_SECRET}" \
    -d "{\"client_ip\":\"${SSH_CLIENT%% *}\"}")
HOST=$(echo "$TARGET" | jq -r .target_host)
PORT=$(echo "$TARGET" | jq -r .target_port)
USER=$(echo "$TARGET" | jq -r .target_user)

exec ssh -i /etc/vlab/backend_ed25519 \
    -o StrictHostKeyChecking=accept-new \
    -p "$PORT" "${USER}@${HOST}"
```

**Note**: nếu Claude Code muốn dùng `AuthorizedKeysCommand` thay vì PAM, không phản đối — miễn đảm bảo password lookup DB. PAM là cách đơn giản nhất.

---

## 5. Worker: kill session khi hết giờ

`backend/workers/gateway_janitor.py`, chạy bằng APScheduler interval=30s:

```python
async def tick():
    now = datetime.now(timezone.utc)

    # 1. Tìm session sắp hết hạn trong 5 phút → gửi banner cảnh báo
    warning_threshold = now + timedelta(minutes=5)
    expiring = db.query(GatewaySession).filter(
        GatewaySession.expires_at <= warning_threshold,
        GatewaySession.expires_at > now,
        GatewaySession.revoked_at.is_(None),
        GatewaySession.warning_sent.is_(False),  # cần thêm cột này vào schema
    ).all()

    for s in expiring:
        await send_terminal_banner(
            s,
            f"\r\n*** Phiên sẽ kết thúc trong "
            f"{int((s.expires_at - now).total_seconds() / 60)} phút. "
            f"Lưu công việc của bạn. ***\r\n"
        )
        s.warning_sent = True

    # 2. Tìm session đã hết hạn → revoke + kill process
    expired = db.query(GatewaySession).filter(
        GatewaySession.expires_at <= now,
        GatewaySession.revoked_at.is_(None),
    ).all()

    for s in expired:
        s.revoked_at = now
        await kill_ssh_session(s)   # signal SV14 qua control socket

    db.commit()
```

**Banner trong terminal**: cách đơn giản nhất là worker ssh vào SV14 `pkill -SIGUSR1 <pid>` không work với sshd — thực tế nên dùng `write(1)` qua tty của session. Implement options (chọn 1):

- **Option A (đơn giản)**: SV14 lưu `(session_id → pty path)` khi session-start, worker `echo "..." > /dev/pts/N`. Dirty nhưng work.
- **Option B (sạch hơn)**: Wrap `vlab-jump.sh` bằng 1 process trung gian (Python script) hold tty và inject banner. Phức tạp hơn 1 bậc.

Recommend **Option A** trước, refactor sang B nếu cần.

`kill_ssh_session`: gửi SIGTERM tới PID đã ghi nhận trong `session-start`, hoặc `pkill -u vlab -f "ssh.*${target_host}"` nếu không track PID.

---

## 6. Frontend changes

### 6.1. Thay nút "Connect" hiện tại

File `frontend/app/bookings/page.tsx` (đoán đường dẫn):

**Cũ** (cần xoá):
```tsx
<button onClick={openWetty}>Connect</button>
// → mở /wetty?key=... trong tab mới + copy private key vào clipboard
```

**Mới**:
```tsx
<button onClick={requestAccess}>Get SSH access</button>

// requestAccess() = POST /api/bookings/{id}/access → mở modal
```

### 6.2. Modal "Thông tin SSH"

```tsx
<Modal title={`Phiên #${booking.id} đã sẵn sàng`}>
  <Row label="Host">      <Code>sv14.bcse-vju.com</Code> </Row>
  <Row label="Port">      <Code>22</Code> </Row>
  <Row label="Username">  <Code>vlab</Code> </Row>
  <Row label="Password">
    <Code>{password}</Code>
    <CopyButton value={password} />
    <Note>Password chỉ hiện 1 lần. Nếu mất, bấm Regenerate.</Note>
  </Row>

  <Divider>Hoặc dán nguyên lệnh này vào terminal:</Divider>
  <CodeBlock>
    ssh -J vlab@sv14.bcse-vju.com {targetUser}@{targetHost}
  </CodeBlock>
  <CopyButton value={sshCommand} />

  <Note>
    Phiên hết hạn lúc {formatTime(expiresAt)} ({timeLeft} còn lại).
    MobaXterm: Session → SSH → Remote host = {targetHost},
    Advanced SSH → Jump host = sv14.bcse-vju.com
  </Note>

  <Button onClick={regenerate}>Regenerate password</Button>
</Modal>
```

### 6.3. Trang `/help/ssh-setup`

Trang hướng dẫn ngắn (1 page) có screenshot MobaXterm + OpenSSH CLI cho SV biết cách nhập jump host. Có thể tạo skeleton, fill screenshot sau.

---

## 7. Acceptance criteria

Claude Code chỉ được coi là "xong" task này khi:

- [ ] Migration `0003_gateway_sessions.sql` chạy clean, có rollback
- [ ] `services/gateway_credentials.py` có ≥5 unit test (generate format, bcrypt verify ok/fail, expired, revoked, regenerate flow)
- [ ] Endpoint `POST /api/bookings/{id}/access` trả password đúng format `xxxx-xxxx-xxxx`, password chỉ trả 1 lần
- [ ] Endpoint `POST /api/gateway/auth` trả 200 cho password đúng + còn hạn, 401 cho mọi case khác, log đủ vào `gateway_auth_log`
- [ ] Worker test: tạo session với `expires_at = now + 6 phút` → 1 phút sau worker phải gửi warning, 6 phút sau phải revoke
- [ ] Frontend: xoá hết reference tới wetty, modal SSH info render đúng, copy button work
- [ ] `docker-compose.yml` không còn service wetty
- [ ] `infrastructure/sv14/` có file `sshd_config.d/vlab.conf` + `pam.d/sshd-vlab` + 2 script bash
- [ ] README cập nhật phần "Cách dùng" — bỏ "private key copy vào clipboard", thay bằng "password + ssh -J"
- [ ] Smoke test thủ công: từ máy ngoài, `ssh -J vlab@sv14 pi@kit-mock` với password đúng → connect được; password sai → từ chối; sau `expires_at` → từ chối connection mới + session đang chạy bị cắt trong ≤60s

---

## 8. Mock mode (vẫn cần vì chưa có tunnel Hoà Lạc)

Giữ env `MOCK_SSH_DEVICES=true` như cũ, nhưng đổi behavior:

- Khi mock: backend vẫn issue password thật, `target_host` set về `mock-kit` (1 container Alpine + sshd chạy trong stack SV14)
- User vẫn SSH thật, vẫn cảm nhận đúng UX, chỉ là kit là Alpine không có FPGA
- Tắt mock = đổi `target_host` lookup từ DB thật (192.168.20.x)

---

## 9. Câu hỏi mở (Claude Code dừng và hỏi trước khi quyết)

1. Backend SSH key `/etc/vlab/backend_ed25519` đã tồn tại chưa? Nếu chưa, gen ở đâu, public key push lên kit pool bằng tool gì?
2. Bảng `devices` đã có cột `lan_ip`, `ssh_port`, `ssh_user` chưa? Nếu chưa, migration `0003` add luôn.
3. `GATEWAY_SHARED_SECRET` — sinh bằng `openssl rand -hex 32`, lưu trong `.env.prod`, mount vào cả backend container và SV14 host. OK?

Nếu thầy/Claude Code unblock được 3 câu này, có thể bắt đầu code ngay.
