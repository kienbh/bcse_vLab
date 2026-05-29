"""Show capabilities JSON for the 13 original VPS rows."""
import sys, paramiko
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

j = paramiko.SSHClient(); j.set_missing_host_key_policy(paramiko.AutoAddPolicy())
j.connect("123.16.53.250", port=2223, username="root", password="VJuOffice@2024", timeout=20)
sock = j.get_transport().open_channel("direct-tcpip", ("192.168.2.114", 22), ("127.0.0.1", 0))
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.2.114", username="student", password="Student@2024", sock=sock, timeout=20)

sql = "SELECT name, capabilities FROM devices WHERE device_type='vps' ORDER BY name;"
cmd = (f'echo Student@2024 | sudo -S docker exec vju-lab-portal-postgres-1 '
       f'psql -U labportal -d labportal -c "{sql}" 2>&1')
_, out, _ = c.exec_command(cmd, timeout=30)
print(out.read().decode(errors="replace"))
c.close(); j.close()
