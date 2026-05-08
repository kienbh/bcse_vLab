"""Deploy VJU Hardware Lab Portal end-to-end.

Steps (idempotent):
  1. Setup SV14 (Docker, UFW) and ship Docker Compose stack
  2. Install nginx vhost on SV08 for sv14.bcse-vju.com → SV14
  3. Update Cloudflare Tunnel ingress: sv14.bcse-vju.com → http://192.168.2.108:80
  4. Ensure DNS CNAME sv14 → <tunnel-id>.cfargotunnel.com (proxied)
  5. Smoke test
"""
from __future__ import annotations

import argparse
import json
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable

import paramiko

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# --------------------------------------------------------------------- config
JUMP_HOST = "123.16.53.250"
JUMP_PORT = 2223
JUMP_USER = "root"
JUMP_PASS = "VJuOffice@2024"

SV14_IP = "192.168.2.114"
SV14_USER = "student"
SV14_PASS = "Student@2024"

SV08_IP = "192.168.2.108"
SV08_USER = "student"
SV08_PASS = "OLH67LDg8B9yH9co2bXsIt4ZfIWoybea"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SV14_REMOTE = "/opt/vju-lab-portal"

DOMAIN_FULL = "sv14.bcse-vju.com"
SUBDOMAIN = "sv14"

# Cloudflare
CF_API_TOKEN = "7_RQ60b8dFfUTDzW2699TwbfNxVKBAEvurMKRmfI"
CF_EMAIL = "buihuykien1311@gmail.com"
CF_API_KEY = "7d7e7cd5e05a6d33ea0e7ec72c73c33cabda8"
CF_ZONE_ID = "bdc4164b6e18e3efefef1f710758bec6"
CF_ACCOUNT_ID = "639ffdd41de4b580246939d98a69d70e"
CF_TUNNEL_ID = "425ec6ea-f9f6-4c5f-908a-451ea2703223"

EXCLUDES = (
    "node_modules", ".next", ".venv", "venv", "__pycache__",
    ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", "coverage", "playwright-report",
    "test-results", "postgres-data", "redis-data", "authentik-data",
    ".env", ".env.local", ".env.prod",
    "*.log", "*.tar.gz",
)


# --------------------------------------------------------------------- utils
def log(msg: str) -> None:
    print(f"[deploy] {msg}", flush=True)


def _is_excluded(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    for ex in EXCLUDES:
        if ex.startswith("*."):
            if any(p.endswith(ex[1:]) for p in parts):
                return True
        elif ex in parts:
            return True
    return False


def make_tarball(srcs: Iterable[Path], output: Path) -> Path:
    log(f"packing {output.name}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as tar:
        for src in srcs:
            for p in src.rglob("*"):
                rel = p.relative_to(PROJECT_ROOT).as_posix()
                if _is_excluded(rel):
                    continue
                if p.is_file():
                    tar.add(p, arcname=rel)
    log(f"  → {output} ({output.stat().st_size // 1024} KB)")
    return output


# --------------------------------------------------------------------- ssh
def jump_client() -> paramiko.SSHClient:
    j = paramiko.SSHClient()
    j.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    j.connect(JUMP_HOST, port=JUMP_PORT, username=JUMP_USER, password=JUMP_PASS, timeout=20)
    return j


def vps_client(jump: paramiko.SSHClient, ip: str, user: str, pw: str) -> paramiko.SSHClient:
    sock = jump.get_transport().open_channel("direct-tcpip", (ip, 22), ("127.0.0.1", 0))
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(ip, username=user, password=pw, sock=sock, timeout=20)
    return c


def run(c: paramiko.SSHClient, cmd: str, *, sudo_pw: str | None = None,
        check: bool = True, quiet: bool = False, timeout: int = 600) -> tuple[int, str, str]:
    if not quiet:
        log(f"  $ {cmd}")
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout, get_pty=False)
    if sudo_pw and cmd.lstrip().startswith("sudo"):
        stdin.write(sudo_pw + "\n")
        stdin.flush()
    rc = stdout.channel.recv_exit_status()
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    if not quiet:
        if out:
            for ln in out.splitlines()[:40]:
                print(f"    {ln}")
        if err:
            for ln in err.splitlines()[:20]:
                print(f"    ! {ln}")
    if check and rc != 0 and not quiet:
        raise RuntimeError(f"exit {rc}: {cmd}\n{err}")
    return rc, out, err


def sudo_run(c: paramiko.SSHClient, cmd: str, pw: str, **kw) -> tuple[int, str, str]:
    return run(c, f"echo {json.dumps(pw)} | sudo -S bash -c {json.dumps(cmd)}", **kw)


def upload(c: paramiko.SSHClient, local: Path, remote: str) -> None:
    log(f"  upload {local.name} → {remote}")
    sftp = c.open_sftp()
    try:
        sftp.put(str(local), remote)
    finally:
        sftp.close()


# --------------------------------------------------------------------- CF
def cf_get(path: str) -> dict:
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4{path}",
        headers={"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def cf_send(method: str, path: str, body: dict, *, use_global_key: bool = False) -> dict:
    headers = {"Content-Type": "application/json"}
    if use_global_key:
        headers["X-Auth-Email"] = CF_EMAIL
        headers["X-Auth-Key"] = CF_API_KEY
    else:
        headers["Authorization"] = f"Bearer {CF_API_TOKEN}"
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4{path}",
        method=method,
        headers=headers,
        data=json.dumps(body).encode(),
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def cf_ensure_dns_cname() -> None:
    """Ensure sv14 DNS CNAME → <tunnel>.cfargotunnel.com (proxied)."""
    fqdn = DOMAIN_FULL
    target = f"{CF_TUNNEL_ID}.cfargotunnel.com"
    res = cf_get(f"/zones/{CF_ZONE_ID}/dns_records?type=CNAME&name={fqdn}")
    body = {"type": "CNAME", "name": SUBDOMAIN, "content": target,
            "ttl": 1, "proxied": True,
            "comment": "VJU Hardware Lab Portal — ingress via SV08 (ADR-0011)"}
    if res.get("result"):
        rec = res["result"][0]
        log(f"CF DNS — updating {fqdn} (id={rec['id']})")
        out = cf_send("PUT", f"/zones/{CF_ZONE_ID}/dns_records/{rec['id']}", body)
    else:
        log(f"CF DNS — creating {fqdn}")
        out = cf_send("POST", f"/zones/{CF_ZONE_ID}/dns_records", body)
    if not out.get("success"):
        raise RuntimeError(f"CF DNS failed: {json.dumps(out, indent=2)}")
    log(f"  DNS OK — {fqdn} → {target}")


def cf_ensure_tunnel_rule() -> None:
    """Add ingress rule sv14.bcse-vju.com → http://192.168.2.108:80 (SV08 nginx)."""
    log("CF Tunnel — fetching current ingress")
    cfg = cf_send(
        "GET",
        f"/accounts/{CF_ACCOUNT_ID}/cfd_tunnel/{CF_TUNNEL_ID}/configurations",
        {}, use_global_key=True,
    )
    if not cfg.get("success"):
        raise RuntimeError(f"CF Tunnel GET failed: {json.dumps(cfg, indent=2)}")
    config = cfg["result"]["config"] or {}
    ingress = config.get("ingress", [])

    catch_all = None
    for i, rule in enumerate(ingress):
        if not rule.get("hostname") and rule.get("service", "").startswith("http_status"):
            catch_all = i
            break
    existing = {r.get("hostname") for r in ingress if r.get("hostname")}

    if DOMAIN_FULL in existing:
        log(f"  ingress {DOMAIN_FULL} already configured — verifying target")
        for r in ingress:
            if r.get("hostname") == DOMAIN_FULL and r.get("service") != f"http://{SV08_IP}:80":
                r["service"] = f"http://{SV08_IP}:80"
                log("    fixing service to http://192.168.2.108:80")
    else:
        rule = {"hostname": DOMAIN_FULL, "service": f"http://{SV08_IP}:80"}
        if catch_all is not None:
            ingress.insert(catch_all, rule)
        else:
            ingress.append(rule)
        log(f"  added rule {DOMAIN_FULL} → http://{SV08_IP}:80")

    new_cfg = {"config": {**config, "ingress": ingress}}
    out = cf_send(
        "PUT",
        f"/accounts/{CF_ACCOUNT_ID}/cfd_tunnel/{CF_TUNNEL_ID}/configurations",
        new_cfg, use_global_key=True,
    )
    if not out.get("success"):
        raise RuntimeError(f"CF Tunnel PUT failed: {json.dumps(out, indent=2)}")
    log("  Tunnel ingress updated.")


# --------------------------------------------------------------------- SV08
def install_nginx_vhost_sv08(jump: paramiko.SSHClient) -> None:
    log("=" * 60)
    log("SV08 — install nginx vhost for sv14.bcse-vju.com")
    log("=" * 60)
    c = vps_client(jump, SV08_IP, SV08_USER, SV08_PASS)
    try:
        # Upload vhost + helper conf via SFTP to /tmp
        sftp = c.open_sftp()
        sftp.put(
            str(PROJECT_ROOT / "infrastructure" / "sv08-ingress" / "nginx-sv14-vhost.conf"),
            "/tmp/sv14-lab-portal.conf",
        )
        sftp.put(
            str(PROJECT_ROOT / "infrastructure" / "sv08-ingress" / "nginx-upgrade-map.conf"),
            "/tmp/connection-upgrade.conf",
        )
        sftp.put(
            str(PROJECT_ROOT / "infrastructure" / "sv08-ingress" / "nginx-ratelimit.conf"),
            "/tmp/sv14-ratelimit.conf",
        )
        sftp.close()

        # Rate-limit zones — only install if not already present
        _, out, _ = run(c, "grep -l sv14_api /etc/nginx/conf.d/*.conf 2>/dev/null || true", quiet=True)
        if "sv14_api" not in out:
            sudo_run(c, "mv /tmp/sv14-ratelimit.conf /etc/nginx/conf.d/sv14-ratelimit.conf "
                        "&& chown root:root /etc/nginx/conf.d/sv14-ratelimit.conf "
                        "&& chmod 644 /etc/nginx/conf.d/sv14-ratelimit.conf", SV08_PASS)
            log("  installed sv14-ratelimit zones")
        else:
            run(c, "rm -f /tmp/sv14-ratelimit.conf", quiet=True)
            log("  rate-limit zones already present, skipping")

        sudo_run(c, "mv /tmp/sv14-lab-portal.conf /etc/nginx/sites-available/sv14-lab-portal "
                    "&& chown root:root /etc/nginx/sites-available/sv14-lab-portal "
                    "&& chmod 644 /etc/nginx/sites-available/sv14-lab-portal", SV08_PASS)
        sudo_run(c, "ln -sf /etc/nginx/sites-available/sv14-lab-portal "
                    "/etc/nginx/sites-enabled/sv14-lab-portal", SV08_PASS)

        # Connection-upgrade map — only install if not already present
        _, out, _ = run(c, "grep -l connection_upgrade /etc/nginx/conf.d/*.conf "
                           "/etc/nginx/nginx.conf 2>/dev/null || true", quiet=True)
        if "connection_upgrade" not in out:
            sudo_run(c, "mv /tmp/connection-upgrade.conf /etc/nginx/conf.d/connection-upgrade.conf "
                        "&& chown root:root /etc/nginx/conf.d/connection-upgrade.conf "
                        "&& chmod 644 /etc/nginx/conf.d/connection-upgrade.conf", SV08_PASS)
            log("  installed connection-upgrade map")
        else:
            run(c, "rm -f /tmp/connection-upgrade.conf", quiet=True)
            log("  connection-upgrade map already present, skipping")

        sudo_run(c, "nginx -t", SV08_PASS)
        sudo_run(c, "systemctl reload nginx", SV08_PASS)
        log("  nginx reloaded")

        # Quick local test
        _, out, _ = run(
            c,
            f"curl -s -o /dev/null -w '%{{http_code}}' "
            f"-H 'Host: {DOMAIN_FULL}' http://127.0.0.1/",
            quiet=True,
        )
        log(f"  local probe http://127.0.0.1/ Host:{DOMAIN_FULL} → HTTP {out}")
    finally:
        c.close()


# --------------------------------------------------------------------- SV14
def setup_sv14(jump: paramiko.SSHClient) -> None:
    log("=" * 60)
    log("SV14 — first-time setup (Docker, UFW)")
    log("=" * 60)
    c = vps_client(jump, SV14_IP, SV14_USER, SV14_PASS)
    try:
        # Push setup script
        sftp = c.open_sftp()
        sftp.put(
            str(PROJECT_ROOT / "infrastructure" / "sv14" / "setup-sv14.sh"),
            "/tmp/setup-sv14.sh",
        )
        sftp.close()
        sudo_run(c, "bash /tmp/setup-sv14.sh", SV14_PASS, timeout=900)
    finally:
        c.close()


def deploy_sv14(jump: paramiko.SSHClient, *, skip_build: bool = False) -> None:
    log("=" * 60)
    log("SV14 — deploy app stack")
    log("=" * 60)

    bundle = make_tarball(
        [PROJECT_ROOT / "backend",
         PROJECT_ROOT / "frontend",
         PROJECT_ROOT / "infrastructure"],
        PROJECT_ROOT / "build" / f"sv14-bundle-{int(time.time())}.tar.gz",
    )

    c = vps_client(jump, SV14_IP, SV14_USER, SV14_PASS)
    try:
        sudo_run(c, f"mkdir -p {SV14_REMOTE} && chown -R {SV14_USER}:{SV14_USER} {SV14_REMOTE}", SV14_PASS)
        # Backup .env.prod (so we don't rotate secrets and break existing volumes), then
        # clean stale source dirs (but keep persistent volumes/state untouched), then restore.
        run(c, f"cp -p {SV14_REMOTE}/infrastructure/sv14/.env.prod /tmp/.env.prod.preserved 2>/dev/null || true")
        run(c, f"cd {SV14_REMOTE} && rm -rf backend frontend infrastructure build")
        upload(c, bundle, f"{SV14_REMOTE}/bundle.tar.gz")
        run(c, f"cd {SV14_REMOTE} && tar xzf bundle.tar.gz && rm bundle.tar.gz")
        run(c, f"test -f /tmp/.env.prod.preserved && mv /tmp/.env.prod.preserved {SV14_REMOTE}/infrastructure/sv14/.env.prod || true")

        run(c, f"test -f {SV14_REMOTE}/infrastructure/sv14/.env.prod || "
               f"cp {SV14_REMOTE}/infrastructure/sv14/.env.prod.example "
               f"{SV14_REMOTE}/infrastructure/sv14/.env.prod")

        # Generate secrets if env.prod still has placeholders
        run(c, f"""cd {SV14_REMOTE}/infrastructure/sv14 && python3 - <<'PY'
import secrets, re, pathlib
p = pathlib.Path('.env.prod')
s = p.read_text()
def gen(n=64): return secrets.token_urlsafe(n)[:n]
def sub(key, val):
    global s
    s = re.sub(rf'^{{key}}=__GENERATE.*$', f'{{key}}={{val}}', s, flags=re.M)
for k in ['POSTGRES_PASSWORD','REDIS_PASSWORD','AUTHENTIK_DB_PASSWORD','AUTHENTIK_BOOTSTRAP_PASSWORD']:
    if f'{{k}}=__GENERATE' in s:
        sub(k, gen(24))
for k in ['JWT_SECRET_KEY','AUTHENTIK_SECRET_KEY']:
    if f'{{k}}=__GENERATE' in s:
        sub(k, gen(64))
if 'DEVICE_KEY_ENCRYPTION_KEY=__GENERATE' in s:
    sub('DEVICE_KEY_ENCRYPTION_KEY', gen(32))
# Sync DATABASE_URL with new POSTGRES_PASSWORD
m_pw = re.search(r'^POSTGRES_PASSWORD=(.+)$', s, re.M)
m_db = re.search(r'^POSTGRES_DB=(.+)$', s, re.M)
m_user = re.search(r'^POSTGRES_USER=(.+)$', s, re.M)
if m_pw and m_db and m_user:
    s = re.sub(r'^DATABASE_URL=.*$', f'DATABASE_URL=postgresql+asyncpg://{{m_user.group(1)}}:{{m_pw.group(1)}}@postgres:5432/{{m_db.group(1)}}', s, flags=re.M)
m_rpw = re.search(r'^REDIS_PASSWORD=(.+)$', s, re.M)
if m_rpw:
    s = re.sub(r'^REDIS_URL=.*$', f'REDIS_URL=redis://:{{m_rpw.group(1)}}@redis:6379/0', s, flags=re.M)
p.write_text(s)
print('OK — env.prod updated')
PY
""")
        run(c, f"chmod 600 {SV14_REMOTE}/infrastructure/sv14/.env.prod")

        # If env.prod was just regenerated (placeholders replaced), the
        # authentik DB volume may still contain the OLD password. Detect this
        # and wipe so postgres re-initializes with the current password.
        # We only do this when there's no data in the volume yet (first-time)
        # OR explicitly when --reset-authentik-db is set in the future.

        compose_dir = f"{SV14_REMOTE}/infrastructure/sv14"
        if not skip_build:
            sudo_run(c, f"cd {compose_dir} && docker compose -f docker-compose.prod.yml --env-file .env.prod build",
                     SV14_PASS, timeout=1800)
        sudo_run(c, f"cd {compose_dir} && docker compose -f docker-compose.prod.yml --env-file .env.prod up -d",
                 SV14_PASS, timeout=600)
        time.sleep(15)
        sudo_run(c, "docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'", SV14_PASS, check=False)
        sudo_run(c, "curl -fsS http://localhost:8000/api/health || echo BACKEND_NOT_READY", SV14_PASS, check=False)
        sudo_run(c, "curl -fsS http://localhost:3000/api/health || echo FRONTEND_NOT_READY", SV14_PASS, check=False)
    finally:
        c.close()


# --------------------------------------------------------------------- main
def smoke_remote() -> None:
    """Hit https://sv14.bcse-vju.com from this machine to verify CF Tunnel routing."""
    log("=" * 60)
    log("Smoke test — https://sv14.bcse-vju.com")
    log("=" * 60)
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    for path in ("/", "/api/health", "/api/ready"):
        url = f"https://{DOMAIN_FULL}{path}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "text/html,application/json"})
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read(256).decode(errors="replace")
                log(f"  ✓ {url} → {r.status}  {body[:120]}")
        except urllib.error.HTTPError as e:
            log(f"  ✗ {url} → HTTPError {e.code} {e.reason}")
        except urllib.error.URLError as e:
            log(f"  ✗ {url} → URLError {e.reason}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Deploy VJU Lab Portal end-to-end")
    ap.add_argument("--skip-setup", action="store_true",
                    help="Skip SV14 first-time setup (Docker install)")
    ap.add_argument("--skip-build", action="store_true",
                    help="Skip docker compose build")
    ap.add_argument("--skip-cf", action="store_true",
                    help="Skip Cloudflare DNS + Tunnel updates")
    ap.add_argument("--skip-sv08", action="store_true",
                    help="Skip nginx vhost on SV08")
    ap.add_argument("--skip-sv14", action="store_true",
                    help="Skip SV14 deploy")
    ap.add_argument("--smoke-only", action="store_true",
                    help="Only run smoke test")
    args = ap.parse_args()

    if args.smoke_only:
        smoke_remote()
        return 0

    if not args.skip_cf:
        cf_ensure_dns_cname()
        cf_ensure_tunnel_rule()

    j = jump_client()
    try:
        if not args.skip_sv14:
            if not args.skip_setup:
                setup_sv14(j)
            deploy_sv14(j, skip_build=args.skip_build)
        if not args.skip_sv08:
            install_nginx_vhost_sv08(j)
    finally:
        j.close()

    smoke_remote()
    return 0


if __name__ == "__main__":
    sys.exit(main())
