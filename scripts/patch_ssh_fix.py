"""Hot-patch the asyncssh.misc.shell_quote bug into the running backend
(no full rebuild) and re-run the SSH provisioning demo end-to-end.

    python scripts/patch_ssh_fix.py
"""
from __future__ import annotations

import io
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import paramiko

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deploy_lab_portal as dlp  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
LOCAL_SSH_MGR = REPO / "backend" / "app" / "services" / "ssh_manager.py"
BASE = "https://sv14.bcse-vju.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
SV_EMAIL = "sv01@st.vju.ac.vn"
PWS = ["VJU@2026", "Demo@2026vju"]


def log(m: str) -> None:
    print(f"[patch] {m}", flush=True)


def hot_patch() -> None:
    log("STEP 1 — upload fixed ssh_manager.py + restart backend")
    j = dlp.jump_client()
    try:
        c = dlp.vps_client(j, dlp.SV14_IP, dlp.SV14_USER, dlp.SV14_PASS)
        try:
            sftp = c.open_sftp()
            sftp.put(str(LOCAL_SSH_MGR), "/tmp/ssh_manager.py")
            sftp.close()
            dlp.sudo_run(
                c,
                "cp /tmp/ssh_manager.py "
                "/opt/vju-lab-portal/backend/app/services/ssh_manager.py && "
                "docker cp /tmp/ssh_manager.py "
                "vju-lab-portal-backend-1:/app/app/services/ssh_manager.py && "
                "docker restart vju-lab-portal-backend-1",
                dlp.SV14_PASS, check=False, timeout=90,
            )
        finally:
            c.close()
    finally:
        j.close()
    # wait for backend health
    for _ in range(30):
        time.sleep(3)
        try:
            req = urllib.request.Request(BASE + "/api/health", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.status == 200:
                    log("  backend healthy again")
                    return
        except Exception:
            pass
    log("  ! backend did not report healthy in 90s — continuing anyway")


class Client:
    def __init__(self) -> None:
        self.cookie: str | None = None

    def req(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(BASE + path, data=data, method=method)
        r.add_header("Content-Type", "application/json")
        r.add_header("User-Agent", UA)
        if self.cookie:
            r.add_header("Cookie", self.cookie)
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                sc = resp.headers.get_all("Set-Cookie") or []
                if sc:
                    self.cookie = "; ".join(x.split(";")[0] for x in sc)
                return resp.status, resp.read().decode(errors="replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(errors="replace")


def run_demo() -> None:
    log("STEP 2 — re-run student session (provision + real ephemeral SSH)")
    cl = Client()

    me = None
    for pw in PWS:
        st, b = cl.req("POST", "/api/auth/login", {"email": SV_EMAIL, "password": pw})
        if st == 200:
            me = json.loads(b)
            log(f"  login OK (pw={pw})")
            break
    if not me:
        log(f"  ! login failed: {b[:200]}")
        return
    if me.get("must_change_password"):
        cl.req("POST", "/api/auth/change-password",
               {"current_password": "VJU@2026", "new_password": "Demo@2026vju"})
        log("  forced password change → Demo@2026vju")

    st, b = cl.req("GET", "/api/devices")
    devs = json.loads(b)
    kv = next((d for d in devs if d["name"] == "kv260-lab01"), None)
    if not kv:
        log("  ! kv260-lab01 missing")
        return
    log(f"  kv260-lab01 id={kv['id']} ip={kv.get('internal_ip')}")

    # reuse an existing usable booking if present, else create one
    now = datetime.now(timezone.utc)
    st, b = cl.req("GET", "/api/bookings")
    bookings = json.loads(b) if st == 200 else []
    booking = None
    for bk in bookings:
        if bk.get("device_id") != kv["id"]:
            continue
        if str(bk.get("status", "")).lower() not in ("scheduled", "active"):
            continue
        try:
            end = datetime.fromisoformat(bk["end_time"].replace("Z", "+00:00"))
        except Exception:
            continue
        if end > now:
            booking = bk
            log(f"  reusing existing booking {bk['id']} (status={bk['status']})")
            break
    if booking is None:
        start = now + timedelta(minutes=1)
        end = start + timedelta(hours=2)
        st, b = cl.req("POST", "/api/bookings", {
            "device_id": kv["id"],
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "notes": "SSH fix verification",
        })
        log(f"  create booking → {st}")
        if st not in (200, 201):
            log(f"  ! booking failed: {b[:200]}")
            return
        booking = json.loads(b)

    st, b = cl.req("POST", f"/api/sessions/provision/{booking['id']}")
    log(f"  provision → {st}")
    if st != 200:
        log(f"  ! provision still failing: {b[:300]}")
        return
    sess = json.loads(b)
    log(f"  session_id={sess['session_id']} mocked={sess['mocked']}")
    log(f"  wetty_url={sess['wetty_url']}")

    try:
        key = paramiko.Ed25519Key.from_private_key(io.StringIO(sess["private_key"]))
        tc = paramiko.SSHClient()
        tc.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        tc.connect(sess["ssh_host"], port=sess["ssh_port"], username=sess["ssh_user"],
                   pkey=key, timeout=15, allow_agent=False, look_for_keys=False)
        _, o, _ = tc.exec_command(
            "hostname; whoami; cat /proc/device-tree/model; "
            "sudo -n xmutil listapps 2>/dev/null | head -4 || true; echo EPHEMERAL_OK")
        out = o.read().decode()
        tc.close()
        if "EPHEMERAL_OK" in out:
            log("  ================ EPHEMERAL KEY SSH SUCCESS ================")
            for ln in out.strip().splitlines():
                log(f"    {ln}")
        else:
            log(f"  ! ran but no marker: {out[:200]}")
    except Exception as e:
        log(f"  ! ephemeral SSH test failed: {e}")


def main() -> int:
    hot_patch()
    time.sleep(3)
    run_demo()
    log("=" * 60)
    log("Browser demo:")
    log(f"  {BASE}/login  →  {SV_EMAIL} / Demo@2026vju")
    log(f"  {BASE}/devices/fpga  → card kv260-lab01 → Đặt lịch / Kết nối")
    return 0


if __name__ == "__main__":
    sys.exit(main())
