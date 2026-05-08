# Security & secrets — đọc trước khi push public

Repo này hiện chứa một số **credential nội bộ BCSE-VJU** đã hardcode trong code. **Phải private repo** (GitHub private / chỉ chia sẻ với thầy + collaborator) cho đến khi sanitize hoàn tất.

## Thứ ĐÃ sanitize

| Chỗ | Trước | Sau |
|---|---|---|
| `backend/scripts/seed.py` | hardcode password thầy `bh.kien@vju.ac.vn` | đọc từ env `ADMIN_BH_KIEN_PASSWORD` |
| `.env.prod` (SV14) | tự generate secrets, không vào git | `.gitignore` exclude |

## Thứ chưa sanitize (TODO khi đi public)

| File | Loại creds | Hành động cần |
|---|---|---|
| `scripts/deploy_lab_portal.py` | Jump host pass, SV14/SV08 student pass, CF API token | Move sang env: `BCSE_JUMP_PASS`, `SV14_PASS`, `SV08_PASS`, `CF_API_TOKEN` |
| `scripts/cf_dns_sv14.py` | CF API token | env `CF_API_TOKEN` |
| `scripts/deploy_auth_subdomain.py` | Jump pass + SV pass + CF token + Global Key | env vars |
| `scripts/peek_sv14.py` `verify_sv14.py` `probe_sv14_sv08.py` `peek_sv14_compose.py` | Jump pass + SV pass | env vars |

## Cách chạy local sau khi sanitize

```bash
# Trên máy thầy
export ADMIN_BH_KIEN_PASSWORD="<password thực>"
export BCSE_JUMP_PASS="..."
export SV14_PASS="Student@2024"
export SV08_PASS="..."
export CF_API_TOKEN="..."

python scripts/deploy_lab_portal.py --skip-cf --skip-setup --skip-build
docker exec vju-lab-portal-backend-1 python /app/seed.py
```

## Quy tắc

1. **KHÔNG commit** `.env.prod`, `*.env`, hay file có password thật
2. Nếu add user mới qua admin UI, password trả về client (mật khẩu khởi tạo) **không** lưu plaintext trong DB — chỉ bcrypt hash
3. JWT secret + bcrypt rounds định nghĩa trong `.env.prod` (auto-generated lần deploy đầu, được preserve qua các lần re-deploy nhờ deploy script backup `.env.prod` qua `/tmp`)
4. Default password `VJU@2026` chỉ dùng cho seed user mới — bắt buộc đổi lần đầu (ép qua `must_change_password=true` flag)
