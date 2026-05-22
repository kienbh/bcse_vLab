"""One-shot demo bring-up for the VJU Hardware Lab Portal.

Run from the repo root on a machine with LAN access to 192.168.2.0/24:

    python scripts/demo_setup.py

Steps (each idempotent, safe to re-run):
  1. Install the portal-admin public key into every real lab KV260 (lab01..05)
     so the backend can push per-session ephemeral keys. Convention:
     FPGA 00X @ 192.168.2.X ↔ user ubuntu00X.
  2. Deploy the updated code + compose to SV14 (reuses deploy_lab_portal.py).
  3. Run the DB seed inside the backend container — creates the real
     kv260-lab01..05 devices, the BCSE-LAB-DEMO-2026 class, 10 enrolled students
     and the class→device assignments (24/7 access).
  4. Smoke test: /api/health + login as sv01 + list devices + book a slot
     + provision an SSH session + prove the ephemeral key actually logs in
     to lab01.

Nothing here rotates secrets or touches postgres data. To reverse the key
install on a kit:  ssh ubuntu00X@<ip>  then
  sed -i '/portal-admin@vju-lab/d' ~/.ssh/authorized_keys
"""
from __future__ import annotations

import io
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import paramiko

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deploy_lab_portal as dlp  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
SECRET_DIR = REPO / "infrastructure" / "sv14" / "secrets"
PRIV = SECRET_DIR / "portal_admin_ed25519"
PUB = SECRET_DIR / "portal_admin_ed25519.pub"

# (ip, ssh_user) — must match backend/scripts/seed.py real devices block.
# IPs are the router's current DHCP leases for each board.
KV260_FLEET: list[tuple[str, str]] = [
    ("192.168.2.93",  "ubuntu001"),
    ("192.168.2.100", "ubuntu002"),
    ("192.168.2.121", "ubuntu003"),
    ("192.168.2.146", "ubuntu004"),
    ("192.168.2.147", "ubuntu005"),
]
KV260_PASS = "abc135"
# lab01 is the device the smoke test books against.
KV260_IP, KV260_USER = KV260_FLEET[0]

PUBLIC = "https://sv14.bcse-vju.com"
DEMO_SV_EMAIL = "sv01@st.vju.ac.vn"
DEMO_DEFAULT_PW = "VJU@2026"
DEMO_NEW_PW = "Demo@2026vju"


def log(msg: str) -> None:
    print(f"[demo] {msg}", flush=True)


# ---------------------------------------------------------------- step 1
def _install_one(ip: str, user: str) -> None:
    pub = PUB.read_text().strip()
    # Try key-auth first — idempotent re-runs skip the password handshake.
    k = paramiko.Ed25519Key.from_private_key(io.StringIO(PRIV.read_text()))
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    used_key = False
    try:
        c.connect(ip, username=user, pkey=k, timeout=10,
                  allow_agent=False, look_for_keys=False)
        used_key = True
    except Exception:
        c.connect(ip, username=user, password=KV260_PASS, timeout=15,
                  allow_agent=False, look_for_keys=False)
    sftp = c.open_sftp()
    try:
        sftp.mkdir(".ssh")
    except OSError:
        pass
    sftp.chmod(".ssh", 0o700)
    ak = ".ssh/authorized_keys"
    existing = ""
    try:
        with sftp.open(ak, "r") as f:
            existing = f.read().decode()
    except IOError:
        pass
    if "portal-admin@vju-lab" in existing:
        log(f"  {user}@{ip}: pubkey present — skip ({'key-auth' if used_key else 'password'})")
    else:
        with sftp.open(ak, "a") as f:
            f.write(pub + "\n")
        log(f"  {user}@{ip}: pubkey appended")
    sftp.chmod(ak, 0o600)
    sftp.close()
    c.close()

    # verify key-auth
    v = paramiko.SSHClient()
    v.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    v.connect(ip, username=user, pkey=k, timeout=15,
              allow_agent=False, look_for_keys=False)
    _, out, _ = v.exec_command("hostname; cat /proc/device-tree/model; echo KEYAUTH_OK")
    txt = out.read().decode()
    v.close()
    if "KEYAUTH_OK" not in txt:
        raise SystemExit(f"{user}@{ip}: key-auth verification FAILED")
    log(f"  {user}@{ip}: ✓ {txt.replace(chr(10), ' ').strip()}")


def install_kv260_key() -> None:
    log("STEP 1 — install portal-admin pubkey on KV260 fleet")
    for ip, user in KV260_FLEET:
        _install_one(ip, user)


# ---------------------------------------------------------------- step 2
def deploy_code() -> None:
    log("STEP 2 — deploy code + compose to SV14")
    j = dlp.jump_client()
    try:
        dlp.deploy_sv14(j, skip_build=False)
    finally:
        j.close()


# ---------------------------------------------------------------- step 3
def run_seed() -> None:
    log("STEP 3 — run DB seed inside backend container")
    j = dlp.jump_client()
    try:
        c = dlp.vps_client(j, dlp.SV14_IP, dlp.SV14_USER, dlp.SV14_PASS)
        try:
            # The backend image may predate the Dockerfile fix that copies
            # scripts/. Copy the freshly-deployed seed.py straight into the
            # running container so a full rebuild isn't required just to seed.
            dlp.sudo_run(
                c,
                "docker exec vju-lab-portal-backend-1 mkdir -p /app/scripts && "
                "docker cp /opt/vju-lab-portal/backend/scripts/seed.py "
                "vju-lab-portal-backend-1:/app/scripts/seed.py",
                dlp.SV14_PASS, check=False, timeout=60,
            )
            dlp.sudo_run(
                c,
                "docker exec -e PYTHONPATH=/app -w /app "
                "vju-lab-portal-backend-1 python /app/scripts/seed.py",
                dlp.SV14_PASS, check=False, timeout=120,
            )
        finally:
            c.close()
    finally:
        j.close()


# ---------------------------------------------------------------- step 4
def _req(method: str, path: str, session: dict, body=None):
    import json
    import urllib.request

    url = f"{PUBLIC}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header(
        "User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    )
    if session.get("cookie"):
        req.add_header("Cookie", session["cookie"])
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            sc = r.headers.get_all("Set-Cookie") or []
            if sc:
                session["cookie"] = "; ".join(x.split(";")[0] for x in sc)
            raw = r.read().decode(errors="replace")
            return r.status, raw
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def smoke_demo() -> None:
    import json

    log("STEP 4 — automated student session demo")
    s: dict = {}

    st, body = _req("GET", "/api/health", s)
    log(f"  health → {st} {body[:80]}")

    st, body = _req(
        "POST", "/api/auth/login", s,
        {"email": DEMO_SV_EMAIL, "password": DEMO_DEFAULT_PW},
    )
    if st != 200:
        # maybe password already changed on a previous run
        st, body = _req(
            "POST", "/api/auth/login", s,
            {"email": DEMO_SV_EMAIL, "password": DEMO_NEW_PW},
        )
    log(f"  login {DEMO_SV_EMAIL} → {st}")
    me = json.loads(body) if st == 200 else {}
    if st != 200:
        log(f"  ! login failed: {body[:200]}")
        return

    if me.get("must_change_password"):
        st, body = _req(
            "POST", "/api/auth/change-password", s,
            {"current_password": DEMO_DEFAULT_PW, "new_password": DEMO_NEW_PW},
        )
        log(f"  forced password change → {st}")

    st, body = _req("GET", "/api/devices", s)
    devs = json.loads(body) if st == 200 else []
    kv = next((d for d in devs if d["name"] == "kv260-lab01"), None)
    log(f"  devices → {st}, found kv260-lab01: {bool(kv)}")
    if not kv:
        log("  ! kv260-lab01 not seeded — aborting demo")
        return

    st, body = _req("GET", f"/api/devices/{kv['id']}/live-status", s)
    log(f"  live-status → {st} {body[:160]}")

    start = datetime.now(timezone.utc) + timedelta(minutes=1)
    end = start + timedelta(hours=2)
    st, body = _req(
        "POST", "/api/bookings", s,
        {
            "device_id": kv["id"],
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "notes": "Automated demo session",
        },
    )
    log(f"  create booking → {st} {body[:200]}")
    if st not in (200, 201):
        return
    booking = json.loads(body)

    # wait until inside the 5-min grace window then provision
    time.sleep(3)
    st, body = _req("POST", f"/api/sessions/provision/{booking['id']}", s)
    log(f"  provision session → {st}")
    if st != 200:
        log(f"  ! provision failed: {body[:200]}")
        return
    sess = json.loads(body)
    log(f"  wetty_url = {sess['wetty_url']}  mocked={sess['mocked']}")

    # Prove the ephemeral private key actually logs into the KV260
    try:
        key = paramiko.Ed25519Key.from_private_key(io.StringIO(sess["private_key"]))
        tc = paramiko.SSHClient()
        tc.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        tc.connect(
            sess["ssh_host"], port=sess["ssh_port"], username=sess["ssh_user"],
            pkey=key, timeout=15, allow_agent=False, look_for_keys=False,
        )
        _, o, _ = tc.exec_command(
            "hostname; whoami; sudo -n xmutil listapps 2>/dev/null | head -3 || true; echo EPHEMERAL_OK"
        )
        out = o.read().decode()
        tc.close()
        if "EPHEMERAL_OK" in out:
            log("  ✓ EPHEMERAL KEY SSH SUCCESS:")
            for ln in out.strip().splitlines():
                log(f"      {ln}")
        else:
            log(f"  ! ephemeral SSH ran but no marker: {out[:200]}")
    except Exception as e:
        log(f"  ! ephemeral key SSH test failed (mocked={sess['mocked']}): {e}")


def main() -> int:
    if not PRIV.exists() or not PUB.exists():
        raise SystemExit(f"keypair missing in {SECRET_DIR} — generate it first")
    install_kv260_key()
    deploy_code()
    log("waiting 20s for containers to settle...")
    time.sleep(20)
    run_seed()
    time.sleep(5)
    smoke_demo()
    log("=" * 60)
    log("DONE. Open the portal:")
    log(f"  {PUBLIC}/login   →  {DEMO_SV_EMAIL} / {DEMO_DEFAULT_PW}")
    log(f"  then go to {PUBLIC}/devices/fpga")
    return 0


if __name__ == "__main__":
    sys.exit(main())
