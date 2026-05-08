# Quickstart — Bootstrap dự án với Claude Code

Tài liệu này cho thầy. Đọc 5 phút, copy 1 prompt, Claude Code sẽ làm phần còn lại.

## Pre-requisites

### Trên máy dev (laptop của thầy)
- VS Code đã cài
- **Claude Code extension** trong VS Code
- Git
- Node.js 20+ (`node --version`)
- Python 3.11+ (`python --version`)
- Docker Desktop (để test local)

### Trên Proxmox host (Hòa Lạc)
- SSH access từ laptop của thầy (`ssh root@<proxmox-public-ip>` hoạt động)
- Đã download LXC template Ubuntu 22.04
- Storage pool còn trống ≥ 150GB

### Domain
- Đã trỏ DNS `lab.vju.edu.vn` (hoặc tương tự) → IP public của Proxmox
- Hoặc tạm dùng IP trực tiếp + self-signed cert cho dev

### Credentials cần chuẩn bị
- Google OAuth credentials (cho Authentik) hoặc bỏ qua, dùng Authentik local users ban đầu
- SMTP credentials (cho email notification): Gmail App Password hoặc Mailgun/SendGrid
- (Optional) GitHub Personal Access Token cho CI/CD

## Bước 1: Tạo project

```bash
mkdir vju-lab-portal
cd vju-lab-portal
git init
```

## Bước 2: Copy tài liệu vào project

Sau khi giải nén `vju-lab-portal-docs-v2.zip`, copy:
- `README.md` → `./README.md`
- `CLAUDE.md` → `./CLAUDE.md`
- `QUICKSTART.md` → `./QUICKSTART.md`
- `.env.example` → `./.env.example`
- `.gitignore` → `./.gitignore`
- `docs/` → `./docs/`

## Bước 3: Mở VS Code + Claude Code

```bash
code .
```

Mở Claude Code panel (Cmd/Ctrl+L hoặc Cmd/Ctrl+Shift+L tùy version).

## Bước 4: Bootstrap prompt — copy nguyên đoạn dưới

Paste vào Claude Code:

````
Hi Claude, you are about to bootstrap a project called "VJU Hardware Lab Portal".

The full design documentation is in the `docs/` folder. Your first job is:

1. Read CLAUDE.md (in project root) — these are the working rules.
2. Read all files in `docs/` in numerical order (01 → 10 + decisions.md).
3. After reading, give me a 5-7 line summary of the project to confirm you understand it.
4. Wait for my "go ahead" before writing any code.

After I confirm:
5. Begin Milestone 0 (Project bootstrap) from `docs/05-implementation-plan.md`.
6. Follow the rules in CLAUDE.md strictly. No hardcoded secrets, no skipping migrations, no skipping tests.
7. Create a feature branch `feat/M0-bootstrap`.
8. At the end of M0, run all the tests and show me the result, then ask me to review before merging.

Important context:
- Target deployment: Proxmox LXC at Hòa Lạc, on the same LAN as the device pool. So no VPN, no bastion.
- Access control is critical: students don't have default access to any device. Lecturers must grant access by creating classes and assigning devices to those classes. Read `docs/10-access-control.md` very carefully.
- All UI text and user-facing messages should be in Vietnamese (with EN toggle option later).
- Database timezone: store UTC, display in Asia/Ho_Chi_Minh (UTC+7).

Communicate with me in Vietnamese. Use "thầy" to refer to me.

Start now: read CLAUDE.md and docs/, then give me your understanding summary.
````

## Bước 5: Chờ Claude Code xác nhận hiểu

Claude Code sẽ:
1. Đọc `CLAUDE.md` + `docs/01..10`
2. Tóm tắt 5-7 dòng về project
3. Hỏi thầy có gì cần clarify

Nếu hiểu sai, **stop và clarify ngay**. Đừng để Claude Code làm tiếp khi hiểu sai.

## Bước 6: Cho phép Claude Code làm M0

Sau khi confirm hiểu đúng, paste:

```
OK, you understand the project correctly. Please proceed with Milestone 0.
After M0 is done, I'll review and we move to M1.
```

Claude Code sẽ tạo:
- `frontend/` (Next.js skeleton)
- `backend/` (FastAPI skeleton)
- `infrastructure/docker-compose.yml` (postgres + redis cho dev local)
- `.github/workflows/ci.yml`
- Pre-commit hooks
- Smoke test

## Bước 7: Verify M0

```bash
docker compose up -d
curl http://localhost:8000/health  # → 200
curl http://localhost:3000          # → Next.js page

cd backend && pytest
cd ../frontend && npm test

git add . && git commit -m "feat: M0 bootstrap" && git push
```

Pass hết → merge `feat/M0-bootstrap` vào `main`.

## Bước 8: Tiếp tục M1 (Proxmox + Auth)

```
M0 done and merged. Let's start M1: Proxmox infrastructure + Auth.

Special instructions for M1:
- Phase 1.A: Generate the Proxmox provisioning scripts. I'll run them on my Proxmox host.
- Phase 1.B: Implement OIDC flow with Authentik.

Key info for M1:
- Proxmox public IP: [thầy điền vào]
- Domain: lab.vju.edu.vn
- Internal subnet for LXC: 10.10.10.0/24 (already documented in 02-architecture.md)
- For Authentik: I'll set up Google OAuth credentials and provide them when needed.

Create branch `feat/M1-infra-auth`.
```

## Bước 9: Test trên Proxmox thật

```bash
# SCP script lên Proxmox
scp infrastructure/proxmox/create-lxc.sh root@<proxmox-ip>:/root/

# SSH + chạy
ssh root@<proxmox-ip>
bash create-lxc.sh

# Verify
pct list
```

5 LXC up trong 5-10 phút.

## Tiếp tục các Milestone khác

Pattern lặp lại:
1. "Begin Milestone X"
2. Claude Code làm trên branch riêng
3. Thầy review + test
4. Merge vào main
5. Lặp lại với M(X+1)

## Khi gặp vấn đề

### "Claude Code đang làm điều ngu ngốc"
Stop ngay. Paste:
```
Stop. Look at what you just did. Check against CLAUDE.md and docs/05-implementation-plan.md. 
Tell me what went wrong and propose how to fix.
```

### "Claude Code skip test"
```
You skipped tests. Per CLAUDE.md hard rules, code without tests is not done.
Add tests for [feature], target ≥ 80% coverage.
```

### "Claude Code đề xuất thay đổi schema/architecture"
```
This is an architecture-level change. Per CLAUDE.md, you must propose 2-3 options 
with trade-offs and wait for my decision. Do not implement until I approve.
Update docs/decisions.md with the chosen ADR.
```

### "Token cạn / context full"
Tạo `RESUME.md` ghi: milestone đang làm, last commit hash, TODO list. Paste vào conversation mới + nói "Resume from RESUME.md".

## Tài liệu tham chiếu

Trong project:
- `docs/05-implementation-plan.md` — roadmap chi tiết
- `docs/06-api-spec.md` — API contract
- `docs/10-access-control.md` — logic phân quyền (đọc kỹ trước M3)
- `docs/decisions.md` — ADR log

External:
- Claude Code docs: https://docs.claude.com/en/docs/claude-code
- Proxmox docs: https://pve.proxmox.com/pve-docs/

## Lời khuyên cuối

1. **Đừng vội**: M0 → M7 trải dài 14 tuần. Đừng cố làm nhanh hơn.
2. **Review từng PR**: đừng auto-merge, đọc diff để hiểu code.
3. **Test với thiết bị thật sớm**: M4 (SSH access) cần 1 KV260 để verify.
4. **Pilot 1 lớp nhỏ trước**: M7 phase B chỉ 20 SV, đừng rollout 200 SV ngay.
5. **Backup từ đầu**: cài backup script ở M1, không phải M7.
6. **Lecturer feedback**: M2.5 xong, mời 1 đồng nghiệp test dashboard giáo viên trước khi đi tiếp.

Chúc thầy success! 🚀
