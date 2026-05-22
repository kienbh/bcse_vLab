"""Ship the locally-updated seed.py to SV14, run it, and verify BOTH real
KV260s end-to-end (book + provision + real ephemeral SSH).

    python scripts/sync_seed.py
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
LOCAL_SEED = REPO / "backend" / "scripts" / "seed.py"
BASE = "https://sv14.bcse-vju.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36"


def log(m: str) -> None:
    print(f"[sync] {m}", flush=True)


def ship_and_seed() -> None:
    log("STEP 1 — upload updated seed.py to SV14 + run it in the container")
    j = dlp.jump_client()
    try:
        c = dlp.vps_client(j, dlp.SV14_IP, dlp.SV14_USER, dlp.SV14_PASS)
        try:
            sftp = c.open_sftp()
            sftp.put(str(LOCAL_SEED), "/tmp/seed.py")
            sftp.close()
            dlp.sudo_run(
                c,
                "cp /tmp/seed.py /opt/vju-lab-portal/backend/scripts/seed.py && "
                "docker exec vju-lab-portal-backend-1 mkdir -p /app/scripts && "
                "docker cp /tmp/seed.py vju-lab-portal-backend-1:/app/scripts/seed.py && "
                "docker exec -e PYTHONPATH=/app -w /app "
                "vju-lab-portal-backend-1 python /app/scripts/seed.py",
                dlp.SV14_PASS, check=False, timeout=120,
            )
        finally:
            c.close()
    finally:
        j.close()


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


def verify_device(student_email: str, device_name: str) -> None:
    log(f"--- verify {device_name} as {student_email} ---")
    cl = Client()
    me = None
    for pw in ("VJU@2026", f"Demo@2026vju"):
        st, b = cl.req("POST", "/api/auth/login",
                       {"email": student_email, "password": pw})
        if st == 200:
            me = json.loads(b)
            break
    if not me:
        log(f"  ! login failed: {b[:160]}")
        return
    if me.get("must_change_password"):
        cl.req("POST", "/api/auth/change-password",
               {"current_password": "VJU@2026", "new_password": "Demo@2026vju"})
        log("  forced password change → Demo@2026vju")

    st, b = cl.req("GET", "/api/devices")
    devs = json.loads(b)
    dev = next((d for d in devs if d["name"] == device_name), None)
    if not dev:
        log(f"  ! {device_name} not in /api/devices — seed didn't add it")
        return
    log(f"  {device_name} id={dev['id']} ip={dev.get('internal_ip')}")

    st, b = cl.req("GET", f"/api/devices/{dev['id']}/live-status")
    ls = json.loads(b) if st == 200 else {}
    log(f"  live-status reachable={ls.get('reachable')} latency_ms={ls.get('latency_ms')}")

    # reuse a usable booking if any, else create one
    now = datetime.now(timezone.utc)
    st, b = cl.req("GET", "/api/bookings")
    booking = None
    for bk in (json.loads(b) if st == 200 else []):
        if bk.get("device_id") == dev["id"] and str(bk.get("status", "")).lower() in ("scheduled", "active"):
            try:
                if datetime.fromisoformat(bk["end_time"].replace("Z", "+00:00")) > now:
                    booking = bk
                    log(f"  reuse booking {bk['id']} ({bk['status']})")
                    break
            except Exception:
                pass
    if booking is None:
        start = now + timedelta(minutes=1)
        st, b = cl.req("POST", "/api/bookings", {
            "device_id": dev["id"],
            "start_time": start.isoformat(),
            "end_time": (start + timedelta(hours=2)).isoformat(),
            "notes": f"verify {device_name}",
        })
        log(f"  create booking → {st}")
        if st not in (200, 201):
            log(f"  ! booking failed: {b[:200]}")
            return
        booking = json.loads(b)

    st, b = cl.req("POST", f"/api/sessions/provision/{booking['id']}")
    log(f"  provision → {st}")
    if st != 200:
        log(f"  ! provision failed: {b[:200]}")
        return
    sess = json.loads(b)
    log(f"  mocked={sess['mocked']} ssh_host={sess['ssh_host']}")
    try:
        key = paramiko.Ed25519Key.from_private_key(io.StringIO(sess["private_key"]))
        tc = paramiko.SSHClient()
        tc.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        tc.connect(sess["ssh_host"], port=sess["ssh_port"], username=sess["ssh_user"],
                   pkey=key, timeout=15, allow_agent=False, look_for_keys=False)
        _, o, _ = tc.exec_command(
            "hostname; cat /proc/device-tree/model; ip -4 -br addr show | awk '/UP/{print $3}'; echo OK_$(hostname)")
        out = o.read().decode()
        tc.close()
        if "OK_" in out:
            log(f"  ✓ EPHEMERAL SSH OK → {device_name} @ {sess['ssh_host']}")
            for ln in out.strip().splitlines():
                log(f"      {ln}")
        else:
            log(f"  ! no marker: {out[:160]}")
    except Exception as e:
        log(f"  ! ephemeral SSH failed: {e}")


def main() -> int:
    ship_and_seed()
    time.sleep(4)
    log("STEP 2 — verify both real KV260s")
    verify_device("sv01@st.vju.ac.vn", "kv260-lab01")
    verify_device("sv02@st.vju.ac.vn", "kv260-lab02")
    log("=" * 60)
    log("Browser: https://sv14.bcse-vju.com/devices/fpga (both kits should be live)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
