"""Smoke test for ADR-0013 / M5.8 gateway endpoints.

Doesn't need credentials of a real user — only checks:
  1. `/api/gateway/auth` rejects requests without the shared-secret header.
  2. `/api/gateway/auth` with the correct secret and a bogus username/password
     returns `{ok: false}` (i.e. wired up, scanning DB, finding nothing).
  3. `/api/gateway/resolve-target` requires the secret.

If you want to test the user-facing flow end-to-end, log into the web UI,
book a slot, click "Get SSH access", and `ssh -p 2222 vlab@ssh.bcse-vju.com`.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def post(url: str, body: dict, *, headers: dict | None = None, timeout: int = 10):
    req = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://sv14.bcse-vju.com", help="Backend base URL")
    ap.add_argument("--secret", help="GATEWAY_SHARED_SECRET (skip the secret-required tests if absent)")
    args = ap.parse_args()

    base = args.base.rstrip("/")
    print(f"--> {base}")
    ok = True

    # 1. /api/gateway/auth without header → 401
    status, body = post(
        f"{base}/api/gateway/auth",
        {"username": "vlab", "password": "x", "client_ip": "127.0.0.1"},
    )
    expect = status == 401
    print(f"[{'PASS' if expect else 'FAIL'}] no secret → {status} (want 401) :: {body[:120]}")
    ok = ok and expect

    if not args.secret:
        print("(skipping authenticated tests — pass --secret to run)")
        return 0 if ok else 1

    # 2. /api/gateway/auth with valid secret + bogus creds → 200 {ok:false}
    status, body = post(
        f"{base}/api/gateway/auth",
        {"username": "vlab", "password": "zzzz-zzzz-zzzz", "client_ip": "127.0.0.1"},
        headers={"X-Gateway-Secret": args.secret},
    )
    expect = status == 200 and '"ok":false' in body.replace(" ", "")
    print(f"[{'PASS' if expect else 'FAIL'}] valid secret + bogus pw → {status} :: {body[:160]}")
    ok = ok and expect

    # 3. /api/gateway/resolve-target without header → 401
    status, body = post(
        f"{base}/api/gateway/resolve-target",
        {"username": "vlab", "client_ip": "127.0.0.1"},
    )
    expect = status == 401
    print(f"[{'PASS' if expect else 'FAIL'}] resolve-target no secret → {status} (want 401) :: {body[:120]}")
    ok = ok and expect

    # 4. /api/gateway/resolve-target with secret but no active session → 404
    status, body = post(
        f"{base}/api/gateway/resolve-target",
        {"username": "vlab", "client_ip": "127.0.0.1"},
        headers={"X-Gateway-Secret": args.secret},
    )
    expect = status == 404
    print(f"[{'PASS' if expect else 'FAIL'}] resolve-target no recent auth → {status} (want 404) :: {body[:160]}")
    ok = ok and expect

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
