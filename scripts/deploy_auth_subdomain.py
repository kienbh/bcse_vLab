"""Deploy lab-auth.bcse-vju.com — subdomain for Authentik (M1 fix for subpath issue).

Steps:
  1. Create CF DNS CNAME `lab-auth.bcse-vju.com` → tunnel cfargotunnel
  2. Add CF Tunnel ingress rule lab-auth.bcse-vju.com → http://192.168.2.108:80
  3. Install nginx vhost on SV08 (uses existing rate-limit + connection-upgrade map)
  4. Update Authentik env on SV14 to know its public URL
  5. Smoke test lab-auth.bcse-vju.com
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import paramiko

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Reuse same constants
JUMP_HOST, JUMP_PORT, JUMP_USER, JUMP_PASS = "123.16.53.250", 2223, "root", "VJuOffice@2024"
SV14_IP, SV14_USER, SV14_PASS = "192.168.2.114", "student", "Student@2024"
SV08_IP, SV08_USER, SV08_PASS = "192.168.2.108", "student", "OLH67LDg8B9yH9co2bXsIt4ZfIWoybea"

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DOMAIN_FULL = "lab-auth.bcse-vju.com"
SUBDOMAIN = "lab-auth"

CF_API_TOKEN = "7_RQ60b8dFfUTDzW2699TwbfNxVKBAEvurMKRmfI"
CF_EMAIL, CF_API_KEY = "buihuykien1311@gmail.com", "7d7e7cd5e05a6d33ea0e7ec72c73c33cabda8"
CF_ZONE_ID = "bdc4164b6e18e3efefef1f710758bec6"
CF_ACCOUNT_ID = "639ffdd41de4b580246939d98a69d70e"
CF_TUNNEL_ID = "425ec6ea-f9f6-4c5f-908a-451ea2703223"


def log(m: str) -> None:
    print(f"[auth-deploy] {m}", flush=True)


def cf_send(method: str, path: str, body: dict | None = None, *, global_key: bool = False) -> dict:
    headers = {"Content-Type": "application/json"}
    if global_key:
        headers["X-Auth-Email"] = CF_EMAIL
        headers["X-Auth-Key"] = CF_API_KEY
    else:
        headers["Authorization"] = f"Bearer {CF_API_TOKEN}"
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4{path}",
        method=method,
        headers=headers,
        data=json.dumps(body).encode() if body is not None else None,
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def cf_dns() -> None:
    target = f"{CF_TUNNEL_ID}.cfargotunnel.com"
    res = cf_send("GET", f"/zones/{CF_ZONE_ID}/dns_records?type=CNAME&name={DOMAIN_FULL}")
    body = {
        "type": "CNAME", "name": SUBDOMAIN, "content": target,
        "ttl": 1, "proxied": True,
        "comment": "Authentik subdomain for VJU Lab Portal (M1)",
    }
    if res.get("result"):
        rec = res["result"][0]
        log(f"updating CF DNS {DOMAIN_FULL} (id={rec['id']})")
        out = cf_send("PUT", f"/zones/{CF_ZONE_ID}/dns_records/{rec['id']}", body)
    else:
        log(f"creating CF DNS {DOMAIN_FULL}")
        out = cf_send("POST", f"/zones/{CF_ZONE_ID}/dns_records", body)
    if not out.get("success"):
        raise RuntimeError(f"CF DNS failed: {json.dumps(out, indent=2)}")
    log(f"  OK — {DOMAIN_FULL} → {target}")


def cf_tunnel() -> None:
    log("fetching CF Tunnel ingress")
    cfg = cf_send("GET", f"/accounts/{CF_ACCOUNT_ID}/cfd_tunnel/{CF_TUNNEL_ID}/configurations",
                  body=None, global_key=True)
    if not cfg.get("success"):
        raise RuntimeError(f"GET tunnel failed: {json.dumps(cfg, indent=2)}")
    config = cfg["result"]["config"] or {}
    ingress = config.get("ingress", [])
    catch_all = next((i for i, r in enumerate(ingress)
                      if not r.get("hostname") and r.get("service", "").startswith("http_status")),
                     None)
    existing = {r.get("hostname") for r in ingress if r.get("hostname")}
    if DOMAIN_FULL not in existing:
        rule = {"hostname": DOMAIN_FULL, "service": f"http://{SV08_IP}:80"}
        if catch_all is not None:
            ingress.insert(catch_all, rule)
        else:
            ingress.append(rule)
        log(f"  added {DOMAIN_FULL} → http://{SV08_IP}:80")
        out = cf_send("PUT",
                      f"/accounts/{CF_ACCOUNT_ID}/cfd_tunnel/{CF_TUNNEL_ID}/configurations",
                      {"config": {**config, "ingress": ingress}}, global_key=True)
        if not out.get("success"):
            raise RuntimeError(f"PUT tunnel failed: {json.dumps(out, indent=2)}")
        log("  Tunnel ingress updated.")
    else:
        log(f"  {DOMAIN_FULL} already in tunnel ingress, skipping")


def open_jump() -> paramiko.SSHClient:
    j = paramiko.SSHClient()
    j.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    j.connect(JUMP_HOST, port=JUMP_PORT, username=JUMP_USER, password=JUMP_PASS, timeout=20)
    return j


def vps(jump: paramiko.SSHClient, ip: str, user: str, pw: str) -> paramiko.SSHClient:
    sock = jump.get_transport().open_channel("direct-tcpip", (ip, 22), ("127.0.0.1", 0))
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(ip, username=user, password=pw, sock=sock, timeout=20)
    return c


def run(c: paramiko.SSHClient, cmd: str, *, check: bool = True, quiet: bool = False) -> tuple[int, str]:
    if not quiet:
        log(f"  $ {cmd}")
    _, out, err = c.exec_command(cmd, timeout=120)
    rc = out.channel.recv_exit_status()
    o = out.read().decode(errors="replace").strip()
    e = err.read().decode(errors="replace").strip()
    if not quiet and (o or e):
        for ln in (o or e).splitlines()[:25]:
            print(f"    {ln}")
    if check and rc != 0 and not quiet:
        raise RuntimeError(f"rc={rc}: {cmd}\n{e}")
    return rc, o


def sudo_run(c: paramiko.SSHClient, cmd: str, pw: str, **kw) -> tuple[int, str]:
    return run(c, f"echo {json.dumps(pw)} | sudo -S bash -c {json.dumps(cmd)}", **kw)


def install_nginx_vhost(jump: paramiko.SSHClient) -> None:
    log("installing nginx vhost on SV08 for lab-auth.bcse-vju.com")
    c = vps(jump, SV08_IP, SV08_USER, SV08_PASS)
    try:
        sftp = c.open_sftp()
        sftp.put(str(PROJECT_ROOT / "infrastructure/sv08-ingress/nginx-auth-vhost.conf"),
                 "/tmp/auth-sv14.conf")
        sftp.close()
        sudo_run(c, "mv /tmp/auth-sv14.conf /etc/nginx/sites-available/auth-sv14 "
                    "&& chown root:root /etc/nginx/sites-available/auth-sv14 "
                    "&& chmod 644 /etc/nginx/sites-available/auth-sv14 "
                    "&& ln -sf /etc/nginx/sites-available/auth-sv14 /etc/nginx/sites-enabled/auth-sv14",
                 SV08_PASS)
        sudo_run(c, "nginx -t && systemctl reload nginx", SV08_PASS)
        log("  nginx reloaded")
        _, out = run(c, f"curl -s -o /dev/null -w '%{{http_code}}' "
                        f"-H 'Host: {DOMAIN_FULL}' http://127.0.0.1/", quiet=True)
        log(f"  local probe http://127.0.0.1/ Host:{DOMAIN_FULL} → HTTP {out}")
    finally:
        c.close()


def update_authentik_env(jump: paramiko.SSHClient) -> None:
    """Set AUTHENTIK_HOST in env so links reference auth.sv14 correctly."""
    log("updating Authentik env on SV14 to advertise public URL")
    c = vps(jump, SV14_IP, SV14_USER, SV14_PASS)
    try:
        env_path = "/opt/vju-lab-portal/infrastructure/sv14/.env.prod"
        # Check if already set
        rc, _ = run(c, f"grep -q '^AUTHENTIK_BASE_URL=' {env_path} 2>/dev/null", check=False, quiet=True)
        if rc == 0:
            run(c, f"sed -i 's|^AUTHENTIK_BASE_URL=.*|AUTHENTIK_BASE_URL=https://{DOMAIN_FULL}/|' {env_path}")
        else:
            run(c, f"echo 'AUTHENTIK_BASE_URL=https://{DOMAIN_FULL}/' >> {env_path}")
        log(f"  set AUTHENTIK_BASE_URL=https://{DOMAIN_FULL}/")
    finally:
        c.close()


def smoke() -> None:
    log("smoke test")
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    for path in ("/", "/-/healthz/live/", "/if/flow/initial-setup/"):
        url = f"https://{DOMAIN_FULL}{path}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read(150).decode(errors="replace")
                log(f"  ✓ {url} → {r.status}  {body[:100]}")
        except urllib.error.HTTPError as e:
            log(f"  ✗ {url} → {e.code} {e.reason}")


def main() -> int:
    cf_dns()
    cf_tunnel()
    j = open_jump()
    try:
        install_nginx_vhost(j)
        update_authentik_env(j)
    finally:
        j.close()
    log("DNS may take ~30s to propagate, sleeping then smoke...")
    time.sleep(20)
    smoke()
    log("Done. Authentik admin login: https://lab-auth.bcse-vju.com/if/admin/")
    log("  user: akadmin   pass: in /opt/vju-lab-portal/infrastructure/sv14/.env.prod (AUTHENTIK_BOOTSTRAP_PASSWORD)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
