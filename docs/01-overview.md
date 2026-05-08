# 01 — Tổng quan dự án

## Bối cảnh

Trường Đại học Việt Nhật (VJU) có hai cơ sở:
- **Mỹ Đình**: Khu giảng đường chính, sinh viên học các môn lý thuyết và bài tập
- **Hòa Lạc**: Lab thực hành, đặt thiết bị phần cứng (FPGA, Jetson, RPi)

Khoảng cách hai cơ sở khoảng 20km, sinh viên không thể di chuyển hàng ngày để thực hành. Cần một giải pháp cho sinh viên truy cập thiết bị từ xa, có quản lý + có phân quyền theo môn học.

## Hạ tầng có sẵn

- **Máy chủ Proxmox** đặt tại Hòa Lạc, IP tĩnh public
- Đã host nhiều ứng dụng khác trong hệ sinh thái VJU
- **Cùng LAN với pool thiết bị** → giao tiếp trực tiếp, không cần VPN
- Có thể tạo LXC container/VM với cấu hình tùy ý

## Mục tiêu

Xây dựng một portal web cho phép:

1. Sinh viên đăng nhập bằng tài khoản trường
2. **Sinh viên chỉ thấy + book được kit mà giảng viên đã cấp quyền**
3. Giảng viên tạo lớp học, enroll sinh viên, gán kit cho lớp
4. Đặt lịch sử dụng thiết bị (booking) trong khung giờ lớp cho phép
5. Truy cập SSH tới thiết bị qua web terminal hoặc client native
6. Upload bitstream / source code lên thiết bị
7. Reset thiết bị khi treo (qua smart plug IoT)
8. Giảng viên/admin xem audit log, observe session SV đang chạy

## Người dùng và mô hình phân quyền

### 4 vai trò

| Vai trò | Mô tả | Quyền |
|---|---|---|
| **Student** | Sinh viên đang học | Book device được lecturer cấp, SSH access |
| **TA** | Trợ giảng | Quyền student + xem session SV trong lớp + can thiệp |
| **Lecturer** | Giảng viên phụ trách môn | Tạo class, enroll SV, gán kit, observe session, force end |
| **Admin** | Quản trị hệ thống | Tất cả + quản lý device, role, audit toàn cục |

### Phân quyền truy cập kit (key feature)

```
Mặc định: Sinh viên KHÔNG có quyền dùng kit nào
                         ↓
Bước 1: Lecturer tạo class "VHDL 2026 - Spring"
Bước 2: Lecturer enroll SV vào class (CSV upload hoặc thủ công)
Bước 3: Lecturer "assign" 6 kit KV260 cho class
        + thiết lập khung giờ class được dùng (vd T2-T6, 8h-22h)
        + thiết lập quota/SV (vd 5h/tuần)
                         ↓
SV thuộc class → Tự động có quyền book 6 kit đó trong khung giờ
```

**Đặc biệt — Cấp quyền cá nhân (cho khóa luận, đề tài đặc biệt):**

```
Lecturer có thể cấp quyền 1 SV cụ thể dùng kit X 
ngoài lớp, với:
- Khung thời gian custom (vd 1 tháng làm khóa luận)
- Lý do (logged trong audit)
- Có thể revoke bất kỳ lúc nào
```

## Pool thiết bị (target ban đầu)

| Loại | Số lượng | Đặc điểm | Linux on-board? |
|---|---|---|---|
| AMD Kria KV260 | 9 | FPGA + Cortex-A53, có Ubuntu/PetaLinux | ✅ |
| NVIDIA Jetson Nano/Orin | TBD | GPU edge, JetPack Linux | ✅ |
| Raspberry Pi 4/5 | TBD | Linux gen-purpose, GPIO | ✅ |

> Tất cả thiết bị target ban đầu đều có Linux on-board → tiếp cận **SSH-first**, không cần gateway PC chạy hw_server.

> **Mở rộng tương lai**: Có thể thêm board không có Linux (Basys3, Nexys A7) — khi đó sẽ cần gateway PC chạy Vivado hw_server. Kiến trúc phải cho phép mở rộng này.

## Ràng buộc

### Kỹ thuật
- Triển khai trên Proxmox LXC tại Hòa Lạc, cùng LAN device pool
- IP tĩnh có sẵn cho phía Internet (sinh viên truy cập từ Mỹ Đình)
- Bandwidth giữa portal và device LAN: gigabit, latency < 5ms
- Bandwidth từ Internet tới portal: phụ thuộc đường truyền VJU
- Thiết bị đôi khi treo → phải có cơ chế hardware reset (smart plug)

### Pháp lý + chính sách
- Dữ liệu sinh viên (PII) → tuân thủ chính sách bảo mật của VJU
- Audit trail bắt buộc — ai làm gì, khi nào, trên thiết bị nào
- Không expose IP nội bộ của lab Hòa Lạc ra Internet (chỉ portal expose)

### Ngân sách
- Phần mềm: 0đ (open source)
- Phần cứng: Proxmox + thiết bị có sẵn + smart plug ~3 triệu

## Phạm vi (scope)

### IN scope (MVP)
- Đăng nhập/đăng ký user, role-based access
- Lecturer dashboard: tạo class, enroll SV, gán kit, observe session
- SV dashboard: thấy chỉ kit có quyền, book + history
- Booking system với access control
- Web SSH terminal (wetty)
- Smart plug API integration (Tasmota/Shelly)
- Audit log đầy đủ
- File upload/download (max 100MB)
- Email notification (booking confirm, reminder)

### OUT of scope (giai đoạn 1)
- Web Vivado GUI (VNC over WebSocket)
- CI/CD tự động nạp bitstream từ Git push
- Mobile app native
- Video stream camera quan sát thiết bị
- Multi-tenant share thiết bị (1 device = 1 user/slot)
- Tích hợp LMS Moodle/Canvas
- Auto-grading code SV nộp lên

## Tiêu chí thành công

Sau pilot 1 lớp 20 sinh viên trong 2 tuần:
- ≥ 80% SV đăng nhập + book thành công không cần hỗ trợ
- Lecturer setup class + assign kit trong < 15 phút
- Uptime hệ thống ≥ 95%
- Thời gian từ "click book" đến "SSH được vào device" ≤ 30 giây
- ≤ 5 lần phải reset device thủ công bởi admin (số lần thực sự lỗi, không tính SV làm hỏng)
- Phản hồi NPS từ SV ≥ 7/10
- Phản hồi từ lecturer ≥ 7/10 (UX dashboard giáo viên)

## Glossary

- **Pool**: Tập hợp tất cả thiết bị quản lý bởi portal
- **Class**: Lớp học do lecturer tạo, gắn với 1 môn + học kỳ
- **Enrollment**: Quan hệ SV-Class
- **Device assignment**: Gán kit cho 1 class với khung giờ + quota
- **Special access**: Quyền dùng kit cấp cá nhân, ngoài lớp (cho khóa luận)
- **Booking**: Lịch đặt sử dụng 1 thiết bị trong khoảng thời gian
- **Session**: Phiên làm việc thực tế của SV trên thiết bị
- **Ephemeral key**: SSH key tạo riêng cho 1 session, hết slot tự xóa
- **PDU**: Power Distribution Unit, smart plug nhiều cổng
- **LXC**: Linux Container trên Proxmox (lightweight VM)
