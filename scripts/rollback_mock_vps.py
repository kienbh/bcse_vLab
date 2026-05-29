"""Rollback the 6 mock VPS rows inserted by seed_vps_pool — the original
13-row pool (sv21..sv30, ai01..ai03) was already set up by thầy in a prior
session, not empty as I assumed."""
import sys, paramiko
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

j = paramiko.SSHClient(); j.set_missing_host_key_policy(paramiko.AutoAddPolicy())
j.connect("123.16.53.250", port=2223, username="root", password="VJuOffice@2024", timeout=20)
sock = j.get_transport().open_channel("direct-tcpip", ("192.168.2.114", 22), ("127.0.0.1", 0))
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.2.114", username="student", password="Student@2024", sock=sock, timeout=20)


def run(cmd, timeout=30):
    _, out, err = c.exec_command(cmd, timeout=timeout)
    return out.read().decode(errors="replace") + err.read().decode(errors="replace")


# Delete the 6 mocks by exact name (safer than date filter).
delete_sql = (
    "DELETE FROM devices WHERE name IN "
    "('sv21-vps','sv22-vps','sv23-vps','sv24-vps','sv25-vps','sv26-vpsgpu') "
    "RETURNING name;"
)
print("=== DELETE 6 mocks")
print(run(f'echo Student@2024 | sudo -S docker exec vju-lab-portal-postgres-1 '
          f'psql -U labportal -d labportal -c "{delete_sql}" 2>&1'))

# Verify pool inventory back to 13.
verify_sql = (
    "SELECT capabilities->>'tier' AS tier, COUNT(*) "
    "FROM devices WHERE device_type='vps' GROUP BY tier ORDER BY tier;"
)
print("\n=== Pool inventory by tier")
print(run(f'echo Student@2024 | sudo -S docker exec vju-lab-portal-postgres-1 '
          f'psql -U labportal -d labportal -c "{verify_sql}" 2>&1'))

# Full list to confirm names.
list_sql = (
    "SELECT name, capabilities->>'tier' AS tier "
    "FROM devices WHERE device_type='vps' ORDER BY name;"
)
print("\n=== Full VPS list")
print(run(f'echo Student@2024 | sudo -S docker exec vju-lab-portal-postgres-1 '
          f'psql -U labportal -d labportal -c "{list_sql}" 2>&1'))

c.close(); j.close()
