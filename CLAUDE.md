# Hướng dẫn cho Claude Code

Đây là file Claude Code đọc đầu tiên khi mở project. Đọc kỹ và follow.

## Bạn đang giúp xây dựng

**VJU Hardware Lab Portal** — cổng truy cập thiết bị FPGA/Jetson/RPi cho sinh viên trường Đại học Việt Nhật.

**Đặc điểm cốt lõi cần nhớ:**
1. Triển khai trên Proxmox LXC tại Hòa Lạc, cùng LAN với pool thiết bị → không cần VPN
2. Sinh viên KHÔNG mặc định có quyền dùng kit — phải qua giảng viên cấp quyền
3. Cấp quyền 2 mức: cả lớp dùng pool kit + override từng SV cho khóa luận

## Quy trình làm việc bắt buộc

### Trước khi viết code
1. **Đọc toàn bộ `docs/` theo thứ tự** (01 → 10). Không skip.
2. Sau khi đọc xong, **báo cáo lại bằng 1 đoạn ngắn** (5-7 dòng) tóm tắt project để xác nhận hiểu đúng.
3. **Hỏi thầy** nếu có chỗ mâu thuẫn hoặc thiếu thông tin.

### Khi implement
1. **Làm theo `docs/05-implementation-plan.md`** từ Milestone 0 → 7.
2. **Mỗi milestone = 1 git branch riêng** (`feat/M0-bootstrap`, `feat/M1-auth`, ...).
3. **Không skip milestone**. Hoàn thành Definition of Done trước khi đi tiếp.
4. **Test trước khi commit**.
5. **Update `docs/decisions.md`** khi có quyết định kiến trúc.

### Khi gặp vấn đề
1. **Re-read `docs/`** xem có hint không.
2. **Đề xuất 2-3 phương án** với trade-off cho thầy chọn.
3. **Không tự ý** quyết định những thứ ảnh hưởng kiến trúc, schema, security.

## Hard rules — KHÔNG vi phạm

❌ **Không hardcode secrets** vào source code. Luôn qua `.env`.

❌ **Không lưu private SSH key vào DB**. Chỉ lưu public key.

❌ **Không expose DB port ra Internet**. Chỉ trong Docker network nội bộ container.

❌ **Không skip migration** dùng `Base.metadata.create_all()` ở prod.

❌ **Không cài thêm framework** không có trong `docs/03-tech-stack.md`.

❌ **Không tự merge vào `main`**. Mọi PR cần thầy review.

❌ **Không tạo admin user qua API**. Chỉ qua seed script.

❌ **Không skip access control check**. SV book device phải qua check class+enrollment+device_assignment.

❌ **Không skip test**. Code không test = chưa xong.

❌ **Không disable HTTPS** với lý do "test cho nhanh". Dùng mkcert local.

❌ **Không log secrets** ra stdout/file.

## Soft rules — Best practices

✓ **Code style**:
- Backend: ruff format + ruff check
- Frontend: prettier + eslint
- Imports sorted, không unused
- Type hints đầy đủ (Python: 100%, TS: strict mode)

✓ **Commit message** — Conventional format:
- `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- Tiếng Anh
- Mô tả "what" + "why", không chỉ "what"

✓ **PR description**:
- Link tới milestone trong `05-implementation-plan.md`
- Screenshot/screencast nếu có UI change
- Test plan
- Breaking changes? Migration cần manual?

✓ **Error handling**:
- Mọi external call (SSH, plug API, OIDC) phải có try/except
- User-facing error message → tiếng Việt friendly
- Internal error message → tiếng Anh chi tiết với context

✓ **Logging**:
- Loguru ở backend, structured (JSON ở prod)
- Level đúng: DEBUG (dev only), INFO (state changes), WARN (recoverable), ERROR (need attention)
- Mỗi request có request_id để trace

## Khi viết tests

**Backend (pytest)**:
- Unit test cho business logic ở `services/`
- Integration test cho mỗi API endpoint với httpx
- Fixtures cho DB session (rollback cuối test)
- Mock external service (SSH, plug API)
- Coverage target ≥ 80%
- **BẮT BUỘC**: test access control logic (`can_user_book_device`)

**Frontend (Vitest + Playwright)**:
- Component test cho UI logic phức tạp
- E2E test cho critical flow: login → book → connect → end
- E2E test cho teacher: tạo lớp → enroll SV → assign kit
- Visual regression optional

## Khi cần feedback từ thầy

Format câu hỏi:

```
**Context**: [tóm tắt tình huống]

**Vấn đề**: [vấn đề cụ thể]

**Phương án**:
1. [option A] — Pros: ... — Cons: ...
2. [option B] — Pros: ... — Cons: ...

**Đề xuất của em**: [option] vì [lý do]

**Cần thầy quyết định**: [câu hỏi cụ thể]
```

KHÔNG hỏi câu chung chung kiểu "Em làm như nào ạ?".

## Project context riêng

- **Người dùng**: sinh viên Việt Nam, giao tiếp tiếng Việt là chính.
- **UI text** mặc định tiếng Việt, có toggle EN.
- **Timezone**: Asia/Ho_Chi_Minh (UTC+7) cho hiển thị, lưu UTC trong DB.
- **Date format hiển thị**: `DD/MM/YYYY HH:mm`.
- **Múi giờ ở backend xử lý**: luôn UTC, convert chỉ ở presentation layer.
- **Performance ưu tiên**: SV ở Mỹ Đình kết nối qua mạng VJU campus, có thể chậm. UI nhẹ, lazy load.
- **Same-LAN với devices**: latency từ portal tới device < 5ms, không phải tối ưu network nhiều.

## Khi không chắc

Câu thần chú: **"Đo hai lần, cắt một lần"**.

Khi không chắc về một quyết định, dừng lại. Hỏi. Kiểm tra. Đừng đoán.

Đặc biệt với những thứ:
- Security (authentication, authorization, secrets)
- Database schema (khó migrate sau)
- API contract (consumer phụ thuộc)
- Permissions / role logic (đây là core feature)
- File upload / path handling

## Tài liệu tham chiếu

Khi cần biết thêm:
- FastAPI: https://fastapi.tiangolo.com
- SQLAlchemy 2.0: https://docs.sqlalchemy.org
- Next.js App Router: https://nextjs.org/docs
- Authentik: https://goauthentik.io/docs
- Proxmox LXC: https://pve.proxmox.com/wiki/Linux_Container
- Tasmota HTTP API: https://tasmota.github.io/docs/Commands/
- AsyncSSH: https://asyncssh.readthedocs.io
- Caddy: https://caddyserver.com/docs/

## Kiểm tra trạng thái dự án

Mỗi khi resume work (vd ngày hôm sau token reset), Claude Code chạy:

```bash
# Xem milestone đang làm
git branch --show-current

# Xem progress
cat docs/05-implementation-plan.md | grep -A 1 "Milestone"

# Xem decision history
cat docs/decisions.md

# Xem TODO trong code
git grep -n "TODO\|FIXME" -- '*.py' '*.ts' '*.tsx'
```

Sau đó **báo cáo trạng thái** cho thầy trước khi tiếp tục.
