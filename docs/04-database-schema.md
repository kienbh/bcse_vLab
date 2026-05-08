# 04 — Database Schema

## ERD tổng quan

```
users ──< enrollments >── classes ──< class_device_assignments >── devices
  │             │             │                    │                   │
  │             └── special_access >─────────────────────────────────┘
  │                                                                    │
  └──< bookings >─────────────────────────────────────────────────────┘
       │           │
       │           └──< sessions
       │                    │
       │                    └── device_credentials (1-to-1)
       │
       └── audit_logs

devices ── plug_mappings (1-to-1)
users ── user_quotas (1-to-1)
```

## Bảng chi tiết

### `users`
Lưu thông tin sinh viên, TA, giảng viên, admin.

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(64) UNIQUE NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    student_code VARCHAR(32),
    role VARCHAR(20) NOT NULL CHECK (role IN ('student', 'ta', 'lecturer', 'admin')),
    oidc_subject VARCHAR(255) UNIQUE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_email ON users(email);
```

### `devices`
Mỗi bộ kit phần cứng = 1 row.

```sql
CREATE TABLE devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(64) UNIQUE NOT NULL,           -- vd "kv260-03"
    device_type VARCHAR(32) NOT NULL,           -- "kv260", "jetson_orin", "rpi5"
    description TEXT,
    location VARCHAR(64),                        -- "rack-A1-shelf-2"
    
    -- Network info (chỉ truy cập từ LAN nội bộ)
    internal_ip INET NOT NULL,                   -- vd 192.168.20.103
    ssh_port INTEGER DEFAULT 22,
    ssh_user VARCHAR(64) DEFAULT 'student',
    
    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'available'
        CHECK (status IN ('available', 'in_use', 'maintenance', 'offline')),
    last_seen_at TIMESTAMPTZ,
    
    -- Capabilities (JSON cho flexible)
    capabilities JSONB DEFAULT '{}',             -- vd {"has_jtag": true, "fpga_family": "ZynqMP"}
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_devices_type ON devices(device_type);
CREATE INDEX idx_devices_status ON devices(status);
```

### `plug_mappings`
Map mỗi device tới 1 smart plug để power-cycle.

```sql
CREATE TABLE plug_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID UNIQUE REFERENCES devices(id) ON DELETE CASCADE,
    plug_ip INET NOT NULL,
    plug_type VARCHAR(32) NOT NULL,              -- "tasmota", "shelly"
    plug_relay_index INTEGER DEFAULT 0,
    api_token VARCHAR(255),
    last_action_at TIMESTAMPTZ,
    last_action_by UUID REFERENCES users(id)
);
```

### `classes`
Lớp học do giảng viên tạo.

```sql
CREATE TABLE classes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(64) UNIQUE NOT NULL,            -- "VJU3001-2026A" hoặc tự sinh
    name VARCHAR(255) NOT NULL,                  -- "VHDL Programming - Spring 2026"
    semester VARCHAR(16),                         -- "2026-Spring"
    description TEXT,
    
    lecturer_id UUID NOT NULL REFERENCES users(id),
    
    starts_at DATE,
    ends_at DATE,
    
    is_active BOOLEAN DEFAULT TRUE,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_classes_lecturer ON classes(lecturer_id);
CREATE INDEX idx_classes_active ON classes(is_active) WHERE is_active = TRUE;
```

### `enrollments`
Sinh viên thuộc lớp nào.

```sql
CREATE TABLE enrollments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    class_id UUID NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    
    enrolled_at TIMESTAMPTZ DEFAULT NOW(),
    enrolled_by UUID REFERENCES users(id),       -- ai enroll (lecturer hoặc bulk import bởi admin)
    
    is_active BOOLEAN DEFAULT TRUE,              -- soft remove
    removed_at TIMESTAMPTZ,
    
    UNIQUE(class_id, user_id)
);
CREATE INDEX idx_enrollments_user ON enrollments(user_id) WHERE is_active = TRUE;
CREATE INDEX idx_enrollments_class ON enrollments(class_id) WHERE is_active = TRUE;
```

### `class_device_assignments` ⭐ Bảng quan trọng nhất
Gán kit cho lớp với khung giờ + quota.

```sql
CREATE TABLE class_device_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    class_id UUID NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    device_id UUID NOT NULL REFERENCES devices(id),
    
    -- Khoảng thời gian gán
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ NOT NULL,
    
    -- Khung giờ tuần được phép book
    -- Format: [{"day": 1, "start": "08:00", "end": "22:00"}, ...]  (1=T2, 7=CN)
    -- Nếu null/empty → cho phép 24/7 trong khoảng valid_from..valid_to
    allowed_time_windows JSONB DEFAULT '[]',
    
    -- Quota cho từng SV của lớp với device này
    per_student_weekly_hours INTEGER DEFAULT 5,
    per_student_max_concurrent INTEGER DEFAULT 1,
    per_student_max_advance_days INTEGER DEFAULT 7,
    
    -- Audit
    granted_by UUID NOT NULL REFERENCES users(id),
    granted_at TIMESTAMPTZ DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    revoked_by UUID REFERENCES users(id),
    revoke_reason TEXT,
    
    notes TEXT,                                   -- ghi chú lecturer
    
    CONSTRAINT cda_valid_period CHECK (valid_to > valid_from),
    UNIQUE(class_id, device_id, valid_from)
);
CREATE INDEX idx_cda_class ON class_device_assignments(class_id);
CREATE INDEX idx_cda_device ON class_device_assignments(device_id);
CREATE INDEX idx_cda_active ON class_device_assignments(class_id, device_id) 
    WHERE revoked_at IS NULL;
```

### `special_access` ⭐ Cấp quyền cá nhân (cho khóa luận, đề tài đặc biệt)
Cấp quyền 1 SV cụ thể dùng kit ngoài lớp.

```sql
CREATE TABLE special_access (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    device_id UUID NOT NULL REFERENCES devices(id),
    
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ NOT NULL,
    
    -- Khung giờ (như class_device_assignments)
    allowed_time_windows JSONB DEFAULT '[]',
    
    -- Quota riêng (override quota mặc định)
    weekly_hours_limit INTEGER,
    max_concurrent_bookings INTEGER DEFAULT 1,
    
    -- Lý do cấp
    reason TEXT NOT NULL,                         -- "Khóa luận: thiết kế CNN trên FPGA"
    
    granted_by UUID NOT NULL REFERENCES users(id),
    granted_at TIMESTAMPTZ DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    revoked_by UUID REFERENCES users(id),
    revoke_reason TEXT,
    
    CONSTRAINT sa_valid_period CHECK (valid_to > valid_from)
);
CREATE INDEX idx_sa_user_device ON special_access(user_id, device_id);
CREATE INDEX idx_sa_active ON special_access(user_id) 
    WHERE revoked_at IS NULL;
```

### `bookings`
Lịch đặt thiết bị.

```sql
CREATE TABLE bookings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    device_id UUID NOT NULL REFERENCES devices(id),
    
    -- Nguồn quyền: từ class assignment hoặc special access
    granted_via VARCHAR(20) NOT NULL CHECK (granted_via IN ('class', 'special_access')),
    class_id UUID REFERENCES classes(id),                      -- nếu granted_via=class
    special_access_id UUID REFERENCES special_access(id),      -- nếu granted_via=special_access
    
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    
    purpose VARCHAR(255),                         -- "Lab 3 - VHDL counter"
    
    status VARCHAR(20) NOT NULL DEFAULT 'scheduled'
        CHECK (status IN ('scheduled', 'active', 'completed', 'cancelled', 'no_show')),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    cancelled_at TIMESTAMPTZ,
    cancelled_by UUID REFERENCES users(id),
    
    CONSTRAINT booking_time_check CHECK (end_time > start_time),
    CONSTRAINT booking_duration_max CHECK (end_time - start_time <= INTERVAL '8 hours'),
    CONSTRAINT booking_grant_consistency CHECK (
        (granted_via = 'class' AND class_id IS NOT NULL AND special_access_id IS NULL) OR
        (granted_via = 'special_access' AND special_access_id IS NOT NULL AND class_id IS NULL)
    )
);
CREATE INDEX idx_bookings_user_time ON bookings(user_id, start_time);
CREATE INDEX idx_bookings_device_time ON bookings(device_id, start_time, end_time);
CREATE INDEX idx_bookings_status ON bookings(status);

-- Constraint: không trùng slot trên cùng 1 device
CREATE EXTENSION IF NOT EXISTS btree_gist;
ALTER TABLE bookings ADD CONSTRAINT no_overlap
    EXCLUDE USING gist (
        device_id WITH =,
        tstzrange(start_time, end_time) WITH &&
    ) WHERE (status IN ('scheduled', 'active'));
```

### `sessions`
Phiên làm việc thực tế khi booking active.

```sql
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID UNIQUE REFERENCES bookings(id),
    user_id UUID NOT NULL REFERENCES users(id),
    device_id UUID NOT NULL REFERENCES devices(id),
    
    -- Ephemeral SSH key (private NEVER stored)
    ssh_pubkey TEXT NOT NULL,
    ssh_pubkey_fingerprint VARCHAR(255) NOT NULL,
    
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    end_reason VARCHAR(64),
    
    -- Lecturer observation
    observed_by_lecturer_id UUID REFERENCES users(id),
    observe_started_at TIMESTAMPTZ,
    
    -- Stats
    bytes_transferred BIGINT DEFAULT 0,
    commands_count INTEGER DEFAULT 0,
    
    status VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'completed', 'failed', 'kicked'))
);
CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_sessions_device ON sessions(device_id);
CREATE INDEX idx_sessions_active ON sessions(status) WHERE status = 'active';
```

### `audit_logs`
Mọi hành động quan trọng — bắt buộc cho compliance.

```sql
CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    user_id UUID REFERENCES users(id),
    actor_role VARCHAR(20),
    
    action VARCHAR(64) NOT NULL,                 -- "device.reset", "class.create", "session.kick", "access.grant"
    resource_type VARCHAR(32),                    -- "device", "booking", "session", "class", "special_access"
    resource_id UUID,
    
    details JSONB DEFAULT '{}',                  -- payload tự do
    
    ip_address INET,
    user_agent TEXT,
    
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT
);
CREATE INDEX idx_audit_user_time ON audit_logs(user_id, timestamp DESC);
CREATE INDEX idx_audit_action ON audit_logs(action, timestamp DESC);
CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id);
```

### `user_quotas`
Quota global của user (override default).

```sql
CREATE TABLE user_quotas (
    user_id UUID PRIMARY KEY REFERENCES users(id),
    weekly_hours_limit INTEGER DEFAULT 10,       -- tổng từ mọi nguồn
    max_concurrent_bookings INTEGER DEFAULT 2,
    
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by UUID REFERENCES users(id)
);
```

### `device_credentials`
Master credentials backend dùng để SSH vào device.

```sql
CREATE TABLE device_credentials (
    device_id UUID PRIMARY KEY REFERENCES devices(id),
    encrypted_admin_key TEXT NOT NULL,           -- AES-256-GCM encrypted
    key_algorithm VARCHAR(32) DEFAULT 'ed25519',
    rotated_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Migration plan

### Migration 0001: Initial schema
Tạo tất cả các bảng + extensions (`uuid-ossp`, `btree_gist`).

### Migration 0002: Seed data
Insert: 1 admin user, 1 lecturer mẫu, 9 device KV260, 9 plug mapping.

### Migration 0003+: Iterate
Mỗi feature mới = 1 migration. Không sửa migration đã apply lên prod.

## Sample queries thường dùng

```sql
-- Devices SV có quyền dùng (qua class hoặc special access)
WITH user_classes AS (
    SELECT class_id FROM enrollments 
    WHERE user_id = $1 AND is_active = TRUE
),
class_devices AS (
    SELECT DISTINCT cda.device_id, 'class' as source, cda.class_id
    FROM class_device_assignments cda
    WHERE cda.class_id IN (SELECT class_id FROM user_classes)
    AND cda.revoked_at IS NULL
    AND NOW() BETWEEN cda.valid_from AND cda.valid_to
),
special_devices AS (
    SELECT device_id, 'special' as source, NULL::uuid as class_id
    FROM special_access
    WHERE user_id = $1
    AND revoked_at IS NULL
    AND NOW() BETWEEN valid_from AND valid_to
)
SELECT d.*, accessible.source, accessible.class_id
FROM devices d
JOIN (
    SELECT * FROM class_devices
    UNION
    SELECT * FROM special_devices
) accessible ON accessible.device_id = d.id
WHERE d.status != 'maintenance';

-- Booking sắp tới của user
SELECT b.*, d.name as device_name
FROM bookings b
JOIN devices d ON d.id = b.device_id
WHERE b.user_id = $1
AND b.status = 'scheduled'
AND b.start_time > NOW()
ORDER BY b.start_time
LIMIT 5;

-- Quota check trước khi cho book mới — class quota
SELECT 
    SUM(EXTRACT(EPOCH FROM (b.end_time - b.start_time)) / 3600) AS hours_used
FROM bookings b
WHERE b.user_id = $1
AND b.device_id = $2
AND b.granted_via = 'class'
AND b.class_id = $3
AND b.status IN ('scheduled', 'active', 'completed')
AND b.start_time >= date_trunc('week', NOW());

-- Lecturer xem session đang active của lớp mình
SELECT s.*, d.name as device_name, u.full_name as student_name
FROM sessions s
JOIN devices d ON d.id = s.device_id
JOIN users u ON u.id = s.user_id
WHERE s.status = 'active'
AND EXISTS (
    SELECT 1 FROM enrollments e 
    JOIN classes c ON c.id = e.class_id
    WHERE e.user_id = s.user_id
    AND c.lecturer_id = $1
);
```

## Backup chiến lược

- **Daily**: `pg_dump` lúc 3h sáng → snapshot Proxmox + upload S3 hoặc backup lab khác
- **Hourly WAL archive** (nếu prod scale)
- **Test restore mỗi tháng** vào staging DB
- Retention: 30 ngày daily, 12 tháng monthly
- **Proxmox snapshot** LXC `lab-db` mỗi tuần (instant backup toàn bộ container)
