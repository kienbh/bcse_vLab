# 06 — API Specification

## Convention chung

- Base URL: `https://lab.vju.edu.vn/api`
- Authentication: Bearer JWT trong header `Authorization: Bearer <token>`
- Content type: `application/json`
- Date format: ISO 8601 UTC (vd `2026-05-09T14:00:00Z`)
- Pagination: query params `?page=1&size=20`
- Error format:
  ```json
  {
    "error": {
      "code": "ACCESS_DENIED",
      "message": "Bạn chưa được giảng viên cấp quyền dùng kit này",
      "details": { "device_id": "uuid", "user_id": "uuid" }
    }
  }
  ```

## Auth endpoints

### `POST /auth/login`
Khởi tạo OIDC flow. Response 302 → Authentik authorize URL.

### `GET /auth/callback?code=...&state=...`
OIDC callback từ Authentik.

Response 200:
```json
{
  "access_token": "eyJhbG...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": { "id": "...", "email": "...", "role": "student" }
}
```

### `GET /auth/me`
Trả thông tin user hiện tại.

### `POST /auth/logout`
Revoke session.

## Student endpoints

### `GET /api/devices/accessible`
**Quan trọng**: Trả devices mà user hiện tại có quyền dùng (qua class hoặc special access).

Response 200:
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "kv260-03",
      "device_type": "kv260",
      "status": "available",
      "access_via": [
        {
          "source": "class",
          "class_id": "uuid",
          "class_name": "VHDL 2026 - Spring",
          "valid_until": "2026-06-30T23:59:59Z",
          "weekly_quota_remaining": 3.5
        }
      ]
    }
  ]
}
```

### `GET /api/bookings`
List booking của user hiện tại.

### `POST /api/bookings`
Tạo booking. Backend check access control trước.

Body:
```json
{
  "device_id": "uuid",
  "start_time": "2026-05-09T14:00:00Z",
  "end_time": "2026-05-09T16:00:00Z",
  "purpose": "Lab 3 - VHDL counter"
}
```

Backend tự xác định `granted_via` (class hay special_access) — không cần SV gửi.

Response 422 nếu fail access:
```json
{
  "error": {
    "code": "ACCESS_DENIED",
    "message": "Bạn chưa có quyền dùng kit này. Liên hệ giảng viên.",
    "details": {
      "device_id": "uuid",
      "reason": "no_active_assignment"
    }
  }
}
```

Response 422 nếu fail time window:
```json
{
  "error": {
    "code": "OUTSIDE_TIME_WINDOW",
    "message": "Slot này nằm ngoài khung giờ lớp cho phép. Khung giờ: T2-T6 8h-22h.",
    "details": {
      "allowed_windows": [...]
    }
  }
}
```

### `GET /api/bookings/availability`
Tìm slot trống cho 1 device.

### `DELETE /api/bookings/{id}`
Cancel booking.

### `GET /api/sessions/active`
Session đang active của user hiện tại.

### `GET /api/sessions/{id}/connect`
Lấy URL để connect web terminal.

Response 200:
```json
{
  "wetty_url": "https://lab.vju.edu.vn/term/?token=...",
  "ssh_command": "ssh -i ~/lab-key student@192.168.20.103",
  "ssh_private_key": "-----BEGIN OPENSSH PRIVATE KEY-----\n...",
  "expires_at": "2026-05-09T16:00:00Z"
}
```

> `ssh_private_key` chỉ trả về 1 lần. User phải lưu lại nếu muốn dùng SSH client native.

### `POST /api/sessions/{id}/upload`
Upload file lên device.

Multipart, field `file`, max 100MB.

### `POST /api/sessions/{id}/end`
Kết thúc session sớm.

### `POST /api/devices/{id}/reset`
Reset (power-cycle) device.

Auth: user phải có booking active trên device này, hoặc TA/lecturer/admin.

## Teacher endpoints ⭐

### `GET /api/teacher/classes`
List classes của lecturer hiện tại.

### `POST /api/teacher/classes`
Tạo class mới.

Body:
```json
{
  "code": "VJU3001-2026A",
  "name": "VHDL Programming - Spring 2026",
  "semester": "2026-Spring",
  "starts_at": "2026-02-01",
  "ends_at": "2026-06-30"
}
```

### `GET /api/teacher/classes/{id}`
Chi tiết class + students + devices + recent activity.

Response 200:
```json
{
  "id": "uuid",
  "code": "VJU3001-2026A",
  "name": "VHDL Programming - Spring 2026",
  "students": [
    { "id": "uuid", "email": "...", "full_name": "...", "enrolled_at": "..." }
  ],
  "devices": [
    {
      "device": { "id": "uuid", "name": "kv260-03" },
      "assignment": {
        "valid_from": "...",
        "valid_to": "...",
        "allowed_time_windows": [...],
        "per_student_weekly_hours": 5
      }
    }
  ],
  "stats": {
    "total_students": 25,
    "active_sessions": 3,
    "bookings_this_week": 47
  }
}
```

### `POST /api/teacher/classes/{id}/enroll`
Enroll students.

Body:
```json
{
  "student_emails": ["sv001@vju.edu.vn", "sv002@vju.edu.vn", ...]
}
```

Backend behavior:
- Email chưa có user → tạo placeholder user (active=false), gửi email mời
- Email đã có user → enroll luôn
- Trả về kết quả từng email (success/failed/already_enrolled)

### `POST /api/teacher/classes/{id}/enroll/csv`
Bulk enroll qua CSV upload.

Multipart, field `file`. Format CSV:
```
email,full_name,student_code
sv001@vju.edu.vn,Nguyễn Văn A,20240001
sv002@vju.edu.vn,Trần Thị B,20240002
```

### `DELETE /api/teacher/classes/{id}/students/{user_id}`
Remove student khỏi class.

### `POST /api/teacher/classes/{id}/devices`
Assign device cho class.

Body:
```json
{
  "device_id": "uuid",
  "valid_from": "2026-02-01T00:00:00Z",
  "valid_to": "2026-06-30T23:59:59Z",
  "allowed_time_windows": [
    { "day_of_week": 1, "start": "08:00", "end": "22:00" },
    { "day_of_week": 2, "start": "08:00", "end": "22:00" },
    { "day_of_week": 3, "start": "08:00", "end": "22:00" },
    { "day_of_week": 4, "start": "08:00", "end": "22:00" },
    { "day_of_week": 5, "start": "08:00", "end": "22:00" },
    { "day_of_week": 6, "start": "08:00", "end": "12:00" }
  ],
  "per_student_weekly_hours": 5,
  "per_student_max_concurrent": 1,
  "notes": "Default assignment cho học phần VHDL"
}
```

### `DELETE /api/teacher/classes/{id}/devices/{device_id}`
Revoke device khỏi class.

Body:
```json
{ "reason": "Học kỳ kết thúc" }
```

### `GET /api/teacher/sessions/active`
Active sessions của SV trong các lớp lecturer dạy.

### `POST /api/teacher/sessions/{id}/observe`
Observe session SV (read-only SSH).

Response: SSH info để lecturer connect như SV.

### `POST /api/teacher/sessions/{id}/kick`
Force end session.

Body:
```json
{ "reason": "Phát hiện hành vi không phù hợp" }
```

### `GET /api/teacher/special-access`
List special access đã cấp bởi lecturer này.

### `POST /api/teacher/special-access`
Cấp quyền cá nhân cho 1 SV.

Body:
```json
{
  "user_email": "sv001@vju.edu.vn",
  "device_id": "uuid",
  "valid_from": "2026-03-01T00:00:00Z",
  "valid_to": "2026-05-30T23:59:59Z",
  "allowed_time_windows": [],
  "weekly_hours_limit": 20,
  "reason": "Khóa luận: thiết kế CNN trên FPGA Kria KV260"
}
```

### `DELETE /api/teacher/special-access/{id}`
Revoke special access.

## Admin endpoints

### `GET /api/admin/stats`
Tổng quan hệ thống.

### `GET /api/admin/users`
List + manage users (CRUD, change role).

### `POST /api/admin/devices`
Thêm device mới vào pool.

### `PATCH /api/admin/devices/{id}`
Update device, kể cả status (vd "maintenance").

### `GET /api/admin/audit`
Filter audit logs.

### `PATCH /api/admin/users/{id}/quota`
Sửa quota global của user.

## WebSocket / SSE

### `GET /api/events/stream` (SSE)
Server-sent events cho real-time update.

Events:
- `device_status_changed`: `{ device_id, old_status, new_status }`
- `session_started`: `{ session_id, device_id, user_id }`
- `session_ended`: `{ session_id, reason }`
- `booking_starting_soon`: `{ booking_id, minutes_remaining }` (chỉ gửi cho user của booking)
- `lecturer_observing`: `{ session_id, lecturer_name }` (gửi cho SV nếu lecturer observe)

## OpenAPI

FastAPI tự generate `/api/openapi.json` và `/api/docs` (Swagger UI).

## Rate limiting

- Default: 100 req/phút/user
- `POST /auth/login`: 5 req/phút/IP
- `POST /api/devices/{id}/reset`: 3 req/phút/user
- `POST /api/teacher/classes/{id}/enroll/csv`: 10 req/giờ/lecturer
- `POST /api/sessions/{id}/upload`: 10 req/giờ/user

Implement bằng `slowapi` middleware.

## Error codes

| Code | HTTP | Khi nào |
|---|---|---|
| `UNAUTHORIZED` | 401 | Token thiếu/hết hạn |
| `FORBIDDEN` | 403 | Token có nhưng không đủ role |
| `ACCESS_DENIED` | 403 | Không có quyền dùng device (chưa được lecturer cấp) |
| `NOT_FOUND` | 404 | Resource không tồn tại |
| `VALIDATION_ERROR` | 422 | Input không hợp lệ |
| `BOOKING_CONFLICT` | 422 | Trùng slot |
| `OUTSIDE_TIME_WINDOW` | 422 | Slot ngoài khung giờ class |
| `QUOTA_EXCEEDED` | 422 | Vượt quota class hoặc global |
| `DEVICE_OFFLINE` | 503 | Device không reachable |
| `PLUG_API_FAILED` | 502 | Smart plug không phản hồi |
| `INTERNAL_ERROR` | 500 | Bug, log + alert |
