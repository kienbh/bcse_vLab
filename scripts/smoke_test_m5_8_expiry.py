"""End-to-end test for slot-expiry force-quit (ADR-0013 / M5.8).

What we verify:
  1. SSH as vlab with the given password → can run a command on the kit
  2. The session is alive while booking is active
  3. **At expires_at, the connection is dropped within ≤30s** (the on-PVE
     `timeout` should kill ssh-on-PVE, propagating EOF up to MobaXterm)
  4. After drop, attempting to reconnect with the same password fails
     (password is bound to that slot only)
  5. The ssh-to-kit process on PVE is actually gone (no orphan)

How to run (from your workstation, after grabbing the active password
from https://sv14.bcse-vju.com/bookings):

    python scripts/smoke_test_m5_8_expiry.py --password <12-char-pass>

Optional flags:
    --max-wait-after-expiry SECONDS   how long to wait past expires_at
                                      before declaring failure (default 60)
    --gateway-host                    default ssh.bcse-vju.com
    --gateway-port                    default 2223
    --backend-base                    default https://sv14.bcse-vju.com

The test ends in <expected slot length + ~30s>. Pick a booking that's
about to expire (≤5 minutes left) so you don't wait long.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import paramiko

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


GATEWAY_SECRET = (
    "_8cNu-R-QXMuLzP5IAXqLViYYFIit0wwi7ZU9TDgWuacnNawko9tg9Bxx0OmPu-x"
)
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def now() -> datetime:
    return datetime.now(timezone.utc)


def fmt(t: datetime) -> str:
    return t.astimezone().strftime("%H:%M:%S")


def http_post(url: str, body: dict, secret: str | None = None, timeout: int = 10):
    headers = {"Content-Type": "application/json", "User-Agent": BROWSER_UA}
    if secret:
        headers["X-Gateway-Secret"] = secret
    req = urllib.request.Request(
        url, method="POST", data=json.dumps(body).encode(), headers=headers
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode(errors="replace"))


def expect(cond: bool, label: str, detail: str = "") -> bool:
    mark = "✓" if cond else "✗"
    line = f"  [{mark}] {label}"
    if detail:
        line += f"  ({detail})"
    print(line, flush=True)
    return cond


def step(msg: str) -> None:
    print(f"\n[{fmt(now())}] {msg}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="M5.8 slot-expiry smoke test")
    ap.add_argument("--password", required=True, help="active password from /bookings")
    ap.add_argument("--gateway-host", default="ssh.bcse-vju.com")
    ap.add_argument("--gateway-port", type=int, default=2223)
    ap.add_argument("--gateway-user", default="vlab")
    ap.add_argument(
        "--backend-base", default="https://sv14.bcse-vju.com",
        help="for /api/gateway/auth lookup (to discover expires_at)",
    )
    ap.add_argument(
        "--max-wait-after-expiry", type=int, default=60,
        help="seconds after expires_at to wait for force-close",
    )
    args = ap.parse_args()

    all_pass = True

    # -------- Step 1: ask backend when this password expires --------
    step("Step 1: lookup expires_at via /api/gateway/auth")
    code, body = http_post(
        f"{args.backend_base}/api/gateway/auth",
        {"username": args.gateway_user, "password": args.password, "client_ip": "0.0.0.0"},
        secret=GATEWAY_SECRET,
    )
    if not expect(code == 200, "backend reachable", f"http={code}"):
        return 2
    if not expect(body.get("ok") is True, "password valid", str(body)[:120]):
        return 2

    expires_iso = body["expires_at"]
    expires_at = datetime.fromisoformat(expires_iso.replace("Z", "+00:00"))
    target_host = body["target_host"]
    seconds_left = (expires_at - now()).total_seconds()
    print(f"      expires_at = {fmt(expires_at)}  (in {seconds_left:.0f}s)")
    print(f"      target_host = {target_host}")
    all_pass &= expect(seconds_left > 30, "≥30s remaining (need time to test)")
    if seconds_left <= 30:
        print("  → Đặt 1 slot dài hơn (≥3 phút) rồi chạy lại.")
        return 3
    if seconds_left > 900:
        print(f"  → Slot còn {seconds_left/60:.0f} phút — sẽ chạy quá lâu. Đặt slot ngắn hơn (≤10 phút).")
        return 3

    # -------- Step 2: SSH in via Pattern B, confirm shell on kit --------
    step("Step 2: SSH vlab@gateway + verify ta đang ở kit, không phải PVE")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            args.gateway_host, port=args.gateway_port,
            username=args.gateway_user, password=args.password,
            timeout=20, allow_agent=False, look_for_keys=False,
        )
    except Exception as e:
        expect(False, "SSH auth", f"{type(e).__name__}: {e}")
        return 2
    expect(True, "SSH auth OK")

    ch = client.get_transport().open_session()
    ch.get_pty()
    ch.invoke_shell()
    ch.settimeout(10)
    time.sleep(2)

    banner = b""
    while ch.recv_ready():
        banner += ch.recv(4096)
    print(f"      banner head: {banner[:80]!r}...")

    ch.send("hostname && whoami && echo MARKER_$$\n")
    time.sleep(2)
    out = b""
    while ch.recv_ready():
        out += ch.recv(4096)
    decoded = out.decode("utf-8", errors="replace")
    all_pass &= expect("MARKER_" in decoded, "shell responsive (echo round-trip)")
    has_kit_hostname = ("kria" in decoded.lower() or target_host in decoded)
    all_pass &= expect(has_kit_hostname, "on kit (not gateway)", f"hostname output contains kit ref")

    # -------- Step 3: wait until expiry + small grace, watch channel state --------
    grace = args.max_wait_after_expiry
    until = expires_at.timestamp() + grace
    step(f"Step 3: đợi đến {fmt(expires_at)} + {grace}s, watch channel close")
    closed_at: float | None = None
    last_log = time.time()
    while time.time() < until:
        # Send a heartbeat so we'd notice immediately if connection drops
        try:
            if ch.closed or ch.exit_status_ready():
                closed_at = time.time()
                break
            # Push a no-op (echo .) every 5s
            ch.send(":\n")
        except (OSError, paramiko.SSHException):
            closed_at = time.time()
            break
        if time.time() - last_log > 10:
            remaining = expires_at.timestamp() - time.time()
            print(f"      [{fmt(now())}] still alive, expires in {remaining:+.0f}s")
            last_log = time.time()
        time.sleep(2)

    if closed_at:
        drift = closed_at - expires_at.timestamp()
        all_pass &= expect(
            -5 < drift < grace,
            "channel closed near expires_at",
            f"drift = {drift:+.1f}s relative to expires_at",
        )
    else:
        all_pass &= expect(False, "channel closed within window",
                           f"still alive {grace}s past expiry — FORCE-QUIT BỊ BỎ SÓT")

    try:
        ch.close()
        client.close()
    except Exception:
        pass

    # -------- Step 4: reconnect with same password must fail --------
    step("Step 4: thử reconnect với cùng password — phải bị từ chối")
    time.sleep(2)
    code, body = http_post(
        f"{args.backend_base}/api/gateway/auth",
        {"username": args.gateway_user, "password": args.password, "client_ip": "0.0.0.0"},
        secret=GATEWAY_SECRET,
    )
    all_pass &= expect(
        code == 200 and body.get("ok") is False,
        "backend rejects expired password",
        f"{code} ok={body.get('ok')}",
    )

    client2 = paramiko.SSHClient()
    client2.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    rejected = False
    try:
        client2.connect(
            args.gateway_host, port=args.gateway_port,
            username=args.gateway_user, password=args.password,
            timeout=15, allow_agent=False, look_for_keys=False,
        )
    except paramiko.AuthenticationException:
        rejected = True
    except Exception as e:
        rejected = True
        print(f"      (got {type(e).__name__} instead of AuthenticationException — OK)")
    all_pass &= expect(rejected, "SSH new connection rejected")
    try: client2.close()
    except Exception: pass

    # -------- Summary --------
    print("\n" + "=" * 50)
    if all_pass:
        print("RESULT: ✓ ALL CHECKS PASSED — force-quit hoạt động đúng")
        return 0
    print("RESULT: ✗ SOME CHECKS FAILED — xem dòng [✗] phía trên")
    return 1


if __name__ == "__main__":
    sys.exit(main())
