# M5.8: gateway redesign — password ProxyJump + admin audit page

## Summary

Implements ADR-0013 (gateway redesign — password ProxyJump) and closes the long-standing `/admin/audit` 404.

**M5.8 — gateway redesign**
- Per-slot 12-char password (bcrypt-hashed + AES-GCM at rest in `gateway_sessions.password_ciphertext`). Idempotent: POST `/api/bookings/{id}/access` returns the SAME password until the slot ends or `/regenerate` is hit explicitly.
- Pattern B (1 password): `ssh -p 2223 vlab@ssh.bcse-vju.com` → PAM verify → `vlab-jump.sh` ForceCommand → `ssh -i /etc/vlab/backend_ed25519 ubuntu@<kit>`. User never sees a kit password.
- Pattern A (`-J`) still works for power users via `PermitOpen` allow-list (pilot kits `192.168.2.93/100/121:22`).
- Force-quit at `expires_at` by `timeout --signal=HUP --kill-after=5 <duration>s` wrapping the exec'd ssh — on PVE, no backend SSH-back. 5-min English ASCII banner emitted from a forked subshell so it survives the exec.
- `gateway_janitor` revokes the password row + `pkill -u vlab` fallback if `active_pid` is null.
- 4 new migrations: **0004** (`gateway_sessions` + `gateway_auth_log`), **0005** (TimestampMixin cols), **0006** (`password_ciphertext`).
- PVE setup script idempotent — installs static `vlab` user + PAM conditional + sshd Match block + backend admin key.
- 8 unit tests + `scripts/smoke_test_m5_8_expiry.py` end-to-end check.

**Admin audit page**
- `GET /api/admin/audit` paginated reader (action / actor / target / since filters), `GET /api/admin/audit/actions` for dropdown.
- `/admin/audit/page.tsx` — 100-row pages, expand-on-click JSON, color-coded action badges by prefix.

**UI polish**
- Real lab photos on landing/bookings/devices (pic1 cinematic / pic3 circuit-art / pic4 isometric).
- /bookings + /devices banners enlarged, /login reverted to text-only per feedback.
- /bookings Connect button gated by slot start; success state offers "Xem lịch đặt".

## Test plan
- [ ] `python scripts/smoke_test_m5_8_expiry.py --password <12-char>` on an active booking with ≥3 min left
- [ ] Manual: login → /bookings → Get SSH access → `ssh -p 2223 vlab@ssh.bcse-vju.com` → kit shell → wait expires → connection drops
- [ ] `/admin/audit` loads, filter dropdown populated, pagination Prev/Next works
- [ ] `/bookings` + `/devices` banners render correctly on mobile + desktop

🤖 Generated with [Claude Code](https://claude.com/claude-code)
