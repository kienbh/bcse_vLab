# 02 — Kiến trúc hệ thống

## Tổng quan high-level

```
[ SV Browser/Client ] (Mỹ Đình hoặc bất kỳ đâu)
         |
         v  HTTPS
[ IP tĩnh public của Proxmox ]
         |
         v  Caddy reverse proxy
[ LXC: Frontend + Backend + wetty ]
         |
         v  Internal LAN (gigabit, < 5ms)
[ Pool: KV260, Jetson, RPi ]  +  [ Smart Plug PDU ]
```

**Điểm khác biệt so với version 1**: KHÔNG cần WireGuard, KHÔNG cần Pi bastion. Vì Proxmox cùng LAN với pool thiết bị, container trên Proxmox SSH thẳng vào device được.

## Layout LXC trên Proxmox

5 LXC containers, tách biệt theo trách nhiệm:

| Container | vCPU | RAM | Disk | Network | Vai trò |
|---|---|---|---|---|---|
| `lab-proxy` | 1 | 1GB | 10GB | bridge ra Internet + LAN | Caddy + reverse proxy + entry point |
| `lab-app` | 4 | 4GB | 40GB | LAN nội bộ | Frontend Next.js + Backend FastAPI + wetty |
| `lab-db` | 2 | 4GB | 60GB | LAN nội bộ | PostgreSQL + Redis (riêng để backup dễ) |
| `lab-auth` | 2 | 2GB | 20GB | LAN nội bộ | Authentik OIDC server |
| `lab-monitor` | 1 | 1GB | 20GB | LAN nội bộ | Uptime Kuma + Grafana (optional) |

**Tổng**: 10 vCPU, 12GB RAM, 150GB disk — rất nhẹ với Proxmox.

> **Lý do tách 5 LXC**: Backup riêng được, restart 1 service không ảnh hưởng service khác, dễ scale ngang trong tương lai. Nếu thầy thấy phức tạp, có thể merge thành 2 LXC (proxy + all-in-one app+db+auth+monitor).

## Network topology

### Subnet design

```
192.168.1.0/24   LAN chính của lab Hòa Lạc (đã có)
  192.168.1.1    Router/gateway (uplink Internet)
  192.168.1.10   Proxmox host (IP tĩnh public)
  
  Proxmox internal bridge "vmbr1" — 10.10.10.0/24:
    10.10.10.10  lab-proxy
    10.10.10.20  lab-app
    10.10.10.30  lab-db
    10.10.10.40  lab-auth
    10.10.10.50  lab-monitor
  
  Proxmox bridge "vmbr0" (ra LAN chính):
    Chỉ lab-proxy có interface trên này, expose port 80/443 ra Internet
    
192.168.20.0/24   Device pool (subnet riêng, có thể VLAN)
  192.168.20.101-109   KV260 #1-9
  192.168.20.111-119   Jetson #1-N
  192.168.20.121-129   RPi #1-M

192.168.30.0/24   Smart plugs
  192.168.30.101-129   Tasmota plugs (1 plug = 1 device)
```

### Firewall rules (iptables/ufw trên Proxmox host)

- Internet → `lab-proxy` ports 80/443 only ✓
- `lab-proxy` → `lab-app` port 3000 (Next), 8000 (FastAPI), 3001 (wetty) ✓
- `lab-app` → `lab-db` port 5432, 6379 ✓
- `lab-app` → `lab-auth` port 9000 ✓
- `lab-app` → device pool port 22, 3121 (hw_server nếu có) ✓
- `lab-app` → smart plugs port 80 (Tasmota HTTP) ✓
- Device pool → Internet: **DENY** (chỉ allow apt mirror cố định)
- Mọi inbound từ Internet tới device pool: **DENY**

## Các service và trách nhiệm

### 1. Frontend (Next.js) — trong `lab-app`
- Render UI: login, dashboard SV, dashboard lecturer, admin panel, web terminal
- Gọi REST API tới backend
- Mở WebSocket tới wetty để hiển thị terminal
- Stateless — không lưu data riêng

### 2. Backend API (FastAPI) — trong `lab-app`
- Xử lý auth (JWT)
- CRUD: user, class, enrollment, device_assignment, device, booking, session, audit
- **Access control logic**: kiểm tra SV có quyền book device không (xem `10-access-control.md`)
- Sinh ephemeral SSH key + push lên thiết bị qua SSH
- Gọi smart plug API để reset thiết bị
- Emit event tới Redis pub/sub cho real-time UI

### 3. Database (PostgreSQL) — trong `lab-db`
- Lưu user, class, enrollment, class_device_assignment, special_access, device, booking, session, audit_log
- Dùng SQLAlchemy ORM trong backend

### 4. Cache + Queue (Redis) — trong `lab-db`
- Cache session token
- Queue cho background job (gửi email, cleanup ephemeral key)
- Pub/sub cho real-time UI update (Server-Sent Events)

### 5. Auth Provider (Authentik) — trong `lab-auth`
- OIDC server self-hosted
- Support Google OAuth + LDAP nếu trường có
- Backend integrate qua OIDC client

### 6. Web SSH Bridge (wetty) — trong `lab-app`
- Container Docker bên trong LXC `lab-app`
- Forward SSH tới device pool

### 7. Smart Plug Controller — module trong `lab-app/backend`
- Adapter pattern: TasmotaAdapter, ShellyAdapter
- Backend gọi: `plug_controller.power_cycle("kv260-03")`
- Map device_id → plug_ip trong database

### 8. Reverse proxy (Caddy) — trong `lab-proxy`
- Auto HTTPS với Let's Encrypt (vì có IP tĩnh public + domain)
- Route:
  - `/` → frontend
  - `/api/*` → backend
  - `/auth/*` → authentik
  - `/term/*` → wetty
- Logging access log

### 9. Monitoring — trong `lab-monitor`
- Uptime Kuma: ping mọi thiết bị mỗi 60s, alert khi down
- Grafana + Prometheus (optional, có thể bỏ qua MVP)

## Data flow chính

### Flow A: Lecturer cấp quyền cho lớp

```
1. Lecturer login → /api/teacher/classes (POST) tạo class "VHDL 2026"
2. Lecturer upload CSV danh sách SV → /api/teacher/classes/{id}/enroll
   Backend tạo nhiều enrollment records
3. Lecturer chọn 6 kit KV260 + thiết lập:
   - valid_from = 2026-02-01, valid_to = 2026-06-30
   - allowed_time_windows = [{T2-T6: 8h-22h}, {T7: 8h-12h}]
   - per_student_weekly_hours = 5
4. Backend tạo class_device_assignments records
5. Audit log: lecturer X assigned device Y to class Z
```

### Flow B: Sinh viên book và sử dụng thiết bị

```
1. SV vào portal → login qua Authentik OIDC
2. Frontend lấy JWT, gọi GET /api/devices?available_to_me=true
3. Backend query: device nào SV có quyền dùng (qua enrollment + assignment + special_access)
   → Trả list device + slot khả dụng
4. SV chọn KV260-03, slot 14h-16h thứ 3 → POST /api/bookings
5. Backend validate (Xem chi tiết trong 10-access-control.md):
   a. SV có thuộc class nào với device này?
   b. Slot có nằm trong allowed_time_windows?
   c. Còn quota?
   d. Không trùng booking khác?
6. Pass hết → tạo booking record
7. Tới 14h, scheduler chạy job:
   a. Sinh ephemeral SSH key pair
   b. SSH thẳng tới KV260-03 (cùng LAN)
   c. Append public key vào /home/student/.ssh/authorized_keys
   d. Tạo session record với connection info
   e. Gửi email cho SV "device ready, click here to connect"
8. SV click connect → Frontend mở wetty iframe với host=192.168.20.103, port=22, key=<ephemeral>
9. SV làm việc bình thường
10. Tới 16h, scheduler chạy job cleanup:
    a. Kill mọi SSH session đang mở
    b. Remove public key khỏi authorized_keys
    c. (Optional) power cycle device để clean state
    d. Update session.status = 'completed'
```

### Flow C: Lecturer observe session SV

```
1. Lecturer vào dashboard /teacher → tab "Active sessions"
2. Frontend GET /api/teacher/sessions/active
3. Backend trả: chỉ session của SV thuộc class lecturer đó
4. Lecturer click session → /api/teacher/sessions/{id}/observe
5. Backend cấp temporary read-only SSH access cho lecturer
6. Lecturer mở terminal song song với SV (read-only mode)
7. Hoặc lecturer click "Kick" → force end session với reason
```

### Flow D: Reset thiết bị khi treo

```
1. SV/TA click "Reset" trên dashboard
2. Frontend POST /api/devices/{id}/reset
3. Backend kiểm tra: SV có booking active trên device này? hoặc role=ta/lecturer/admin?
4. Backend lookup device.plug_ip
5. Backend gọi Tasmota API:
   POST http://192.168.30.103/cm?cmnd=Power%20Off  (await 5s)
   POST http://192.168.30.103/cm?cmnd=Power%20On
6. Wait 60s cho device boot
7. Ping device, khi up → emit event "device_ready"
8. Frontend nhận event qua SSE, hiện toast "Device đã sẵn sàng"
9. Audit log: who, when, which device, action=reset
```

## Security boundary

```
+-------------------- Internet ---------------------+
|                                                   |
|  SV browser ---> [ TLS ] ---> Proxmox public IP   |
|                                                   |
+-------- LXC lab-proxy (DMZ-like) ----------------+
|  Caddy: chỉ port 80/443 expose ra ngoài           |
|  Forward tới các LXC khác qua internal network    |
+--------------------+-----------------------------+
                     |
+-------- Internal Proxmox network ----------------+
|                                                   |
|  lab-app (frontend + backend + wetty)             |
|  lab-db (postgres + redis)                        |
|  lab-auth (authentik)                             |
|  lab-monitor                                      |
|                                                   |
+--------------------+-----------------------------+
                     |
+-------- LAN Hòa Lạc (trusted) -------------------+
|                                                   |
|  Pool kit (192.168.20.x) — KHÔNG có IP public     |
|  Smart plug (192.168.30.x) — KHÔNG có IP public   |
|                                                   |
+---------------------------------------------------+
```

Nguyên tắc: **Chỉ `lab-proxy` exposed**. Mọi LXC khác và device không bao giờ có IP public. `lab-app` bị compromise → mất data nhưng không mất quyền vào device LAN khác (cần re-auth qua authentik).

## Kiến trúc khả mở rộng

### Khi có nhiều thiết bị (50+)
- Tách `lab-app` thành multiple replica sau load balancer
- Database vẫn 1 instance (Postgres handle 50+ concurrent dễ)

### Khi có thêm board không có Linux (Basys3, Nexys)
- Tạo thêm 1 LXC `lab-hwserver` chạy Vivado Lab Edition + USB passthrough
- Backend route SV "Vivado JTAG over IP" tới đúng instance
- Cần Proxmox GPU/USB passthrough config

### Khi có thêm campus
- Mỗi campus = 1 Proxmox node tham gia cluster
- Migration LXC giữa các node trong vài giây
- Pool kit có thể distributed, location attribute trong DB

### Khi có nhiều lớp đồng thời
- Hiện tại 1 device = 1 user/slot
- Có thể thêm sharing mode (vd 4 SV đồng dùng 1 RPi qua tmux session) — không phải MVP
