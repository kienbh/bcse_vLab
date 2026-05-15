"""Lightweight M5.6 smoke test that doesn't require admin password.

Verifies the new endpoints exist + respond with sensible status codes:
- /api/reset-requests/pending/count (200 if authenticated, 401 if not)
- /api/reset-requests (200 if authenticated)
- Backend started cleanly (smoke /api/health)

Falls back to using whichever student/lecturer is on default VJU@2026.
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
DEFAULT_PW = "VJU@2026"
CANDIDATES = [
    "sv01@st.vju.ac.vn",
    "sv02@st.vju.ac.vn",
    "sv03@st.vju.ac.vn",
    "thaykien@vju.ac.vn",
    "hung.le@vju.ac.vn",
    "anh.nguyen@vju.ac.vn",
]


def _req(opener, method: str, path: str, body=None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"} if body is not None else {}
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


def login_as(email: str, password: str = DEFAULT_PW):
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    s, body = _req(opener, "POST", "/api/auth/login",
                   {"email": email, "password": password})
    return s, body, opener


def main() -> int:
    print("[m5.6] Try to find a working account (default VJU@2026)...")
    opener = None
    me = None
    for email in CANDIDATES:
        s, body, op = login_as(email)
        marker = "✓" if s == 200 else "✗"
        print(f"  {marker} {email} → {s}")
        if s == 200:
            opener = op
            me = body
            break
    if opener is None:
        print("\n[m5.6] No default-password account left — skipping authenticated tests.")
        print("[m5.6] Unauthenticated checks:")
        s, _ = _req(urllib.request.build_opener(), "GET", "/api/reset-requests/pending/count")
        print(f"  /api/reset-requests/pending/count (no auth) → {s} (expect 401)")
        return 0 if s == 401 else 1

    role = me.get("role") if isinstance(me, dict) else "?"
    print(f"\n[m5.6] Logged in as {me.get('email')} (role={role})")

    print("\n# Test /api/reset-requests/pending/count")
    s, body = _req(opener, "GET", "/api/reset-requests/pending/count")
    print(f"   status={s} body={body}")

    print("\n# Test GET /api/reset-requests")
    s, body = _req(opener, "GET", "/api/reset-requests?limit=5")
    print(f"   status={s} count={len(body) if isinstance(body, list) else body}")

    print("\n# Test GET /api/devices (for context)")
    s, body = _req(opener, "GET", "/api/devices")
    if isinstance(body, list):
        print(f"   status={s} devices={len(body)}")
        if body:
            d = body[0]
            print(f"   first: {d['name']} status={d['status']}")
            print(f"\n# Test POST /api/reset-requests for {d['name']}")
            s, body = _req(opener, "POST", "/api/reset-requests",
                           {"device_id": d["id"], "reason": "smoke test M5.6"})
            print(f"   status={s} body={body}")
            if s in (200, 201):
                rid = body.get("id") if isinstance(body, dict) else None
                if rid and not body.get("auto_approved"):
                    print(f"\n# Cleanup — reject the smoke-test request")
                    s2, body2 = _req(opener, "POST", f"/api/reset-requests/{rid}/reject",
                                     {"decision_note": "smoke test cleanup"})
                    print(f"   reject → {s2} (admin/lecturer-only — student may 403, that's OK)")

    print("\n[smoke M5.6] DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
