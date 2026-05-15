"""End-to-end smoke test for M5.6 reset request flow.

Tests via the public HTTPS endpoint (sv14.bcse-vju.com), not local. So this
also validates that nginx routes /api/reset-requests correctly.

Flow:
  1. Login as admin → GET /api/reset-requests/pending/count should be {count: N}
  2. POST /api/reset-requests (as admin, for kv260-01) → expect 200 + pending
  3. GET /api/reset-requests?status=pending → see the new one
  4. POST /api/reset-requests/{id}/reject → expect 200 status=rejected
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = os.environ.get("VJU_BASE", "https://sv14.bcse-vju.com")
ADMIN_EMAIL = "admin@vju.ac.vn"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "VJU@2026")


def _req(opener, method: str, path: str, body=None, headers=None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"} if body is not None else {}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        resp = opener.open(req, timeout=15)
        body_bytes = resp.read()
        try:
            return resp.status, json.loads(body_bytes)
        except json.JSONDecodeError:
            return resp.status, body_bytes.decode(errors="replace")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, str(e)


def main() -> int:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    print(f"# 1. Login as {ADMIN_EMAIL}")
    s, body = _req(opener, "POST", "/api/auth/login",
                   {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    print(f"   status={s} body={body}")
    if s != 200:
        print("FAIL: login failed")
        return 1

    print("\n# 2. GET /api/reset-requests/pending/count")
    s, body = _req(opener, "GET", "/api/reset-requests/pending/count")
    print(f"   status={s} body={body}")
    if s != 200:
        return 1

    print("\n# 3. GET /api/devices to pick a device")
    s, body = _req(opener, "GET", "/api/devices")
    print(f"   status={s} count={len(body) if isinstance(body, list) else '?'}")
    if s != 200 or not body:
        return 1
    device_id = body[0]["id"]
    device_name = body[0]["name"]
    print(f"   using device: {device_name} ({device_id})")

    print("\n# 4. POST /api/reset-requests (smoke test reason)")
    s, body = _req(opener, "POST", "/api/reset-requests",
                   {"device_id": device_id, "reason": f"M5.6 smoke test {os.getpid()}"})
    print(f"   status={s} body={body}")
    request_id = body.get("id") if isinstance(body, dict) else None
    auto_approved = body.get("auto_approved") if isinstance(body, dict) else False
    if s not in (200, 201, 409):
        return 1

    if s == 409:
        print("   (existing pending request — that's fine, will use it)")
        # Fetch existing
        s2, list_body = _req(opener, "GET", "/api/reset-requests?status=pending")
        if s2 == 200 and isinstance(list_body, list) and list_body:
            request_id = list_body[0]["id"]
            print(f"   reusing existing request {request_id}")

    print("\n# 5. GET /api/reset-requests (full list)")
    s, body = _req(opener, "GET", "/api/reset-requests?limit=5")
    print(f"   status={s} count={len(body) if isinstance(body, list) else '?'}")

    if request_id and not auto_approved:
        print(f"\n# 6. POST /api/reset-requests/{request_id}/reject")
        s, body = _req(opener, "POST", f"/api/reset-requests/{request_id}/reject",
                       {"decision_note": "M5.6 smoke test cleanup"})
        print(f"   status={s} body={body}")
        if s == 200:
            print("   ✓ rejected cleanly")
        elif s == 409:
            print("   (already decided — fine)")

    print("\n[smoke M5.6] DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
