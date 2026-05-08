# 09 — Teacher Workflow & UX

Tài liệu này mô tả workflow của **giảng viên (lecturer)** — vai trò có nhiều thao tác phức tạp nhất sau admin. Đây là **core feature** của portal, vì toàn bộ phân quyền SV phụ thuộc vào lecturer làm đúng.

## Triết lý thiết kế

1. **Lecturer là user, không phải DBA** — hide complexity, expose intent
2. **Setup 1 lần/học kỳ** — sau đó chỉ tương tác khi cần (observe, kick, special access)
3. **Phòng tránh lỗi** — confirm trước khi revoke, undo trong 30s
4. **Visibility cao** — luôn biết SV nào đang dùng kit nào ngay lúc này

## 4 use case chính

- **UC1**: Setup lớp đầu học kỳ (~15 phút)
- **UC2**: Cấp special access cho khóa luận (~1 phút)
- **UC3**: Theo dõi lớp đang học (passive)
- **UC4**: Can thiệp khi có vấn đề (kick session)

## UC1: Setup lớp đầu học kỳ

### Flow

```
1. Login → Dashboard lecturer
2. "Tạo lớp mới" → form
3. Upload danh sách SV (CSV) → preview → confirm
4. Chọn kit cho lớp + cấu hình khung giờ + quota → confirm
5. (Optional) Gửi email mời SV
6. Done. SV có thể login + book được.
```

### Mockup dashboard lecturer

```
┌─────────────────────────────────────────────────┐
│ VJU Lab Portal              Lecturer Mode       │
├─────────────────────────────────────────────────┤
│ ┌────────────────────────────────────────────┐ │
│ │  Lớp của tôi                  [+ Tạo lớp]   │ │
│ │  ────────────────────────────                │ │
│ │  📚 VHDL 2026 - Spring                       │ │
│ │     25 SV · 6 KV260 · 3 sessions             │ │
│ │     [Xem chi tiết]                           │ │
│ │                                              │ │
│ │  📚 SoC Design 2026 - Spring                 │ │
│ │     18 SV · 4 Jetson · 0 sessions            │ │
│ │     [Xem chi tiết]                           │ │
│ └────────────────────────────────────────────┘ │
│                                                  │
│ ┌────────────────────────────────────────────┐ │
│ │  Sessions đang chạy (real-time)             │ │
│ │  • Nguyễn Văn A · KV260-03 · 14h–16h         │ │
│ │     [Observe] [Kick]                         │ │
│ │  • Trần Thị B · KV260-05 · 14h–17h           │ │
│ │     [Observe] [Kick]                         │ │
│ └────────────────────────────────────────────┘ │
│                                                  │
│ ┌────────────────────────────────────────────┐ │
│ │  Hành động nhanh                             │ │
│ │  [+ Cấp quyền cá nhân (khóa luận)]           │ │
│ │  [📊 Xem báo cáo sử dụng]                    │ │
│ └────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

### Form tạo lớp

Fields:
- Mã lớp (required, unique) — vd `VJU3001-2026A`
- Tên lớp (required)
- Học kỳ (dropdown)
- Thời gian áp dụng (date range)
- Mô tả (optional)

### CSV upload

Format CSV (download mẫu từ portal):
```
email,full_name,student_code
sv001@vju.edu.vn,Nguyễn Văn A,20240001
sv002@vju.edu.vn,Trần Thị B,20240002
```

UI flow:
1. Drag-drop file CSV
2. Preview 5 dòng đầu, parse xong
3. Hiển thị thống kê: "25 SV, 22 mới, 3 đã có"
4. Checkbox "Gửi email mời SV mới"
5. Confirm → backend xử lý batch, trả progress

### Form assign device

Fields:
- Multi-select device (filter theo type)
- Khoảng thời gian (default = thời gian lớp)
- Khung giờ recurring trong tuần (TimeWindow editor)
- Quota: hours/week, max concurrent, advance days
- Notes

TimeWindow editor UI:
```
┌──────────────────────────────────┐
│ Thứ 2-6:  [08:00] - [22:00]      │
│ Thứ 7:    [08:00] - [12:00]      │
│ Chủ nhật: ☐ Đóng                 │
└──────────────────────────────────┘
[+ Thêm khung giờ tùy chỉnh]
```

## UC2: Cấp special access cho khóa luận

### Form

Fields:
- Sinh viên (search by email/MSSV with autocomplete)
- Device (single select)
- Thời gian (date range)
- Khung giờ: 24/7 hoặc custom
- Quota tuần
- **Lý do (required, ghi audit log)**
- Checkbox gửi email thông báo

## UC3: Theo dõi lớp đang học

Tab "Sessions" trong chi tiết lớp:

```
─── Đang chạy (3) ─────────────

🟢 Nguyễn Văn A · KV260-03
Slot: 14:00–16:00 (còn 47 phút)
Lab 3: VHDL counter
[Observe] [Kick] [Reset device]

🟢 Trần Thị B · KV260-05
Slot: 14:00–17:00 (còn 1h 47 phút)
Lab 4: FSM design
[Observe] [Kick] [Reset device]

─── Lịch sử 7 ngày ────────────

09/05  Lê Văn C · KV260-02 · 2h
09/05  Phạm Thị D · KV260-04 · 1h30
08/05  Nguyễn Văn A · KV260-03 · 2h
[Xem thêm]  [Export CSV]
```

### Observe session

- Click "Observe" → mở tab mới với terminal read-only
- Banner đầu trang: "👁 Đang observe — SV biết về điều này"
- SV nhận notification real-time
- Audit log: lecturer X observed session Y

## UC4: Kick session

Modal confirm với required reason:

```
Bạn sẽ ngắt kết nối SV "Nguyễn Văn A" khỏi
KV260-03 ngay lập tức.

Lý do (bắt buộc, ghi audit + gửi email SV):
┌────────────────────────────────────┐
│ Phát hiện code có dấu hiệu mining  │
│ cryptocurrency, vi phạm điều khoản.│
└────────────────────────────────────┘

[Hủy]  [⚠ Kick session]
```

## Stats dashboard

Tab "Báo cáo" trong chi tiết lớp:

- Tổng quan tuần: số booking, tổng giờ, % SV active
- Top SV theo giờ (bar chart)
- SV chưa hoạt động (alert lecturer cần hỗ trợ)
- Sử dụng theo device (bar chart)
- Export CSV

## Mobile responsive

- **Phone**: tab "Sessions đang chạy" + "Quick actions"
- **Tablet**: full dashboard 2 cột
- **Desktop**: full layout 3 cột

## Notification

Email cho lecturer khi:
- SV trong lớp request reset > 3 lần/session (có thể gặp vấn đề)
- 1 device trong lớp offline > 10 phút
- SV book đầy quota tuần (đang học chăm)
- Cuối tuần: weekly summary

## UI components cần build

- `<ClassCard>` — preview card
- `<StudentList>` với bulk actions
- `<DeviceAssignmentForm>`
- `<TimeWindowEditor>` — recurring weekly schedule
- `<SessionMonitor>` — list active, real-time SSE
- `<ObserveTerminal>` — read-only xterm view
- `<CSVUploader>` với preview
- `<UsageChart>` (recharts)

## API endpoints liên quan

Xem chi tiết trong `06-api-spec.md` mục "Teacher endpoints".
