# 14 — Tích hợp VPS vào vLab

> **Runbook triển khai.** Cho phép vLab quản lý VPS (máy chủ ảo Proxmox) như một
> loại tài nguyên để sinh viên đặt lịch, bên cạnh FPGA / Jetson / RPi.
> Code đã sửa xong (2026-05-22) — tài liệu này để **lập kế hoạch deploy sau**.

## Bối cảnh

BCSE có node Proxmox i7 mới (`192.168.2.210`) chạy 3 VPS Ubuntu 24.04:

| VPS  | IP nội bộ        | Spec                    | Domain công khai     |
|------|------------------|-------------------------|----------------------|
| sv21 | 192.168.2.211    | 4GB RAM / 2 vCPU / 20GB | sv21.bcse-vju.com    |
| sv22 | 192.168.2.212    | 4GB RAM / 2 vCPU / 20GB | sv22.bcse-vju.com    |
| sv23 | 192.168.2.213    | 4GB RAM / 2 vCPU / 20GB | sv23.bcse-vju.com    |

Mục tiêu: sinh viên mượn VPS qua vLab (đặt lịch + SSH qua gateway, không lộ
jump host). vLab trước đó chỉ hỗ trợ FPGA/Jetson/RPi — đã bổ sung loại `vps`.

## Thay đổi code (đã thực hiện)

### Backend
- `backend/app/models/enums.py` — thêm `DeviceType.VPS = "vps"`.
- `backend/migrations/versions/20260522_1200_0008_device_type_vps.py` — migration
  mới `0008`: `ALTER TYPE device_type ADD VALUE 'vps'`. `downgrade` là no-op
  (PostgreSQL không xoá được giá trị enum).
- `backend/scripts/seed.py` — đăng ký sv21/sv22/sv23 (idempotent, chạy lại an toàn).

### Frontend — thêm "family" thứ 4 là **VPS** (màu indigo, icon Server)
- `components/DeviceCard.tsx` — `DeviceFamily` += `vps`; thêm `THEMES.vps`.
- `components/FamilyDashboard.tsx` — `FAMILY_TO_TYPES.vps`, `FAMILY_META.vps`,
  tab VPS.
- `app/devices/vps/page.tsx` — trang mới `/devices/vps`.
- `app/devices/page.tsx` — icon / màu / bộ lọc cho VPS.
- `app/admin/devices/page.tsx` — thêm lựa chọn "VPS" trong form tạo thiết bị.
- `components/TopNav.tsx` — link **VPS** trên thanh điều hướng.

## Các bước deploy (trên server vLab / SV14)

1. **Đưa code mới lên server** theo quy trình deploy hiện tại.
2. **Rebuild image** backend + frontend (cả hai đều có thay đổi):
   ```bash
   cd infrastructure/sv14
   docker compose -f docker-compose.prod.yml build backend frontend
   ```
3. **Restart** — backend khi khởi động chạy `alembic upgrade head` → áp
   migration `0008`:
   ```bash
   docker compose -f docker-compose.prod.yml up -d
   ```
4. **Chạy seed** để tạo 3 VPS trong DB:
   ```bash
   docker exec <backend-container> python /app/seed.py
   ```
   (tên container backend: kiểm tra bằng `docker ps`, vd `vju-lab-portal-backend-1`)
5. Kiểm tra: vào `https://sv14.bcse-vju.com` → tab **VPS** → thấy sv21/sv22/sv23.

## Bật truy cập SSH thật (chế độ MOCK)

vLab mặc định chạy **`MOCK_SSH_DEVICES=true`** — mọi thao tác SSH tới thiết bị là
giả lập; các kit kv260/jetson trong seed là mock (IP `192.168.20.x` không route
được). **3 VPS này là thiết bị thật đầu tiên.**

Để gateway SSH thật vào VPS:

1. Đặt `MOCK_SSH_DEVICES=false` cho backend.
   - ⚠️ **Ảnh hưởng toàn bộ pool** — các kit mock sẽ thành "offline" vì backend
     không ping được. Chỉ bật khi chấp nhận điều đó (hoặc khi pool thật đã sẵn).
2. Thêm **public key của backend admin** vào `/home/student/.ssh/authorized_keys`
   trên cả 3 VPS — gateway ProxyJump dùng key này (xem
   `backend/app/services/ssh_manager.py`, tham số `backend_admin_key_path`).
3. VPS sv21-23: tài khoản `student` đã có NOPASSWD sudo từ cloud-init → không cần
   đặt `KIT_SUDO_PASS`.

## Sau deploy — cấp quyền cho sinh viên

1. Giảng viên tạo `Class` (vd "BCSE Backend Lab").
2. Enroll sinh viên (CSV).
3. Gán 3 VPS cho lớp (`ClassDeviceAssignment`) — đặt `valid_from`/`valid_to`,
   `per_student_weekly_hours`, `allowed_time_windows`. VPS thường mượn dài ngày
   → đặt khoảng thời gian dài (vài tuần).
4. Hoặc cấp cho cá nhân qua `SpecialAccess` (đồ án/luận văn).

## Kiểm chứng

- Migration: `docker exec <backend> alembic current` → `0008`.
- DB: `SELECT name, device_type, internal_ip FROM devices WHERE device_type='vps';`
  → 3 dòng sv21/sv22/sv23.
- Frontend: tab **VPS** hiển thị 3 card.
- Đặt thử 1 slot → tới giờ bấm "Get access" → nhận lệnh SSH; SSH vào được VPS
  (chỉ chạy thật khi đã tắt MOCK + cài key như trên).

## Rollback

- Code frontend/backend: revert commit.
- Migration `0008`: `downgrade` là no-op. Giá trị `vps` thừa trong enum vô hại —
  không cần gỡ. Nếu bắt buộc gỡ, phải tạo lại type `device_type` và rewrite cột
  (không khuyến nghị).
- Gỡ 3 VPS khỏi DB: `DELETE FROM devices WHERE device_type='vps';` (sẽ bị chặn
  nếu còn booking active).
