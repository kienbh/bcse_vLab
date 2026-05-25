"""Peek at the VPS gateway flow on prod: recent auth log + active gateway
sessions tied to VPS bookings. Reads through the same paramiko jump pattern
as scripts/peek_sv14.py so it works from anywhere on the LAN/Internet."""
from __future__ import annotations

import sys
import paramiko

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

j = paramiko.SSHClient()
j.set_missing_host_key_policy(paramiko.AutoAddPolicy())
j.connect("123.16.53.250", port=2223, username="root", password="VJuOffice@2024", timeout=20)
sock = j.get_transport().open_channel("direct-tcpip", ("192.168.2.114", 22), ("127.0.0.1", 0))
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.2.114", username="student", password="Student@2024", sock=sock, timeout=20)


def psql(sql: str) -> str:
    cmd = (
        "echo Student@2024 | sudo -S docker exec vju-lab-portal-postgres-1 "
        f"psql -U labportal -d labportal -A -F'|' -c \"{sql}\""
    )
    _, out, err = c.exec_command(cmd, timeout=60)
    return out.read().decode(errors="replace").strip() + (
        ("\n[stderr] " + err.read().decode(errors="replace").strip()) if err else ""
    )


print("\n=== Recent gateway_auth_log (Asia/Ho_Chi_Minh) ===")
print(
    psql(
        "SELECT to_char(ts AT TIME ZONE 'Asia/Ho_Chi_Minh','HH24:MI:SS') ts_local, "
        "ssh_username, outcome, COALESCE(reason,'') reason, "
        "COALESCE(client_ip::text,'') client_ip, "
        "COALESCE(session_id::text,'') session_id "
        "FROM gateway_auth_log ORDER BY ts DESC LIMIT 20"
    )
)

print("\n=== Active gateway_sessions for VPS bookings ===")
print(
    psql(
        "SELECT gs.id session_id, "
        "to_char(gs.issued_at AT TIME ZONE 'Asia/Ho_Chi_Minh','HH24:MI') issued, "
        "to_char(gs.expires_at AT TIME ZONE 'Asia/Ho_Chi_Minh','MM-DD HH24:MI') expires, "
        "gs.ssh_username, gs.target_user, gs.target_host::text, gs.target_port, "
        "u.email, d.name device, b.shared_resource, b.status, "
        "COALESCE(gs.revoked_at::text,'') revoked, "
        "to_char(gs.last_auth_at AT TIME ZONE 'Asia/Ho_Chi_Minh','HH24:MI:SS') last_auth, "
        "LENGTH(gs.password_hash) pw_hash_len, "
        "gs.regenerate_count "
        "FROM gateway_sessions gs "
        "JOIN bookings b ON b.id = gs.booking_id "
        "JOIN users u ON u.id = gs.user_id "
        "JOIN devices d ON d.id = gs.device_id "
        "WHERE d.device_type = 'vps' "
        "ORDER BY gs.issued_at DESC LIMIT 10"
    )
)

print("\n=== Recent access_requests + their granted SAs ===")
print(
    psql(
        "SELECT ar.id req_id, u.email student, d.name device, ar.status, "
        "to_char(ar.requested_from AT TIME ZONE 'Asia/Ho_Chi_Minh','MM-DD') req_from, "
        "to_char(ar.requested_to AT TIME ZONE 'Asia/Ho_Chi_Minh','MM-DD') req_to, "
        "COALESCE(ar.granted_access_id::text,'') sa_id "
        "FROM access_requests ar "
        "JOIN users u ON u.id = ar.student_id "
        "JOIN devices d ON d.id = ar.device_id "
        "ORDER BY ar.created_at DESC LIMIT 10"
    )
)

print("\n=== Active SpecialAccess for VPS ===")
print(
    psql(
        "SELECT sa.id, u.email student, d.name device, "
        "to_char(sa.valid_from AT TIME ZONE 'Asia/Ho_Chi_Minh','MM-DD HH24:MI') v_from, "
        "to_char(sa.valid_to AT TIME ZONE 'Asia/Ho_Chi_Minh','MM-DD HH24:MI') v_to, "
        "COALESCE(sa.revoked_at::text,'') revoked "
        "FROM special_access sa "
        "JOIN users u ON u.id = sa.user_id "
        "JOIN devices d ON d.id = sa.device_id "
        "WHERE d.device_type = 'vps' "
        "ORDER BY sa.granted_at DESC LIMIT 10"
    )
)

print("\n=== PVE jump host gateway env (cat /etc/vlab/gateway.env on PVE) ===")
# Same pattern as deploy_lab_portal but read-only.
sock2 = j.get_transport().open_channel("direct-tcpip", ("192.168.2.10", 22), ("127.0.0.1", 0))
try:
    p = paramiko.SSHClient()
    p.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    p.connect("192.168.2.10", username="root", password="VJuOffice@2024", sock=sock2, timeout=20)
    _, out, _ = p.exec_command("cat /etc/vlab/gateway.env 2>&1; echo '---'; tail -30 /var/log/vlab-gateway-auth.log 2>/dev/null || echo no auth log")
    print(out.read().decode(errors="replace"))
    p.close()
except Exception as e:
    print(f"PVE peek failed: {e}")

c.close()
j.close()
