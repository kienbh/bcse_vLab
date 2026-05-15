"""Verify all M5.6-touched HTTPS routes exist + respond correctly."""
import sys
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = "https://sv14.bcse-vju.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

CHECKS = [
    # (path, method, expected_unauth_status, note)
    ("/api/reset-requests/pending/count", "GET", (401, 403), "auth-required count"),
    ("/api/reset-requests", "GET", (401, 403), "auth-required list"),
    ("/api/events/stream", "GET", (401, 403), "SSE stream needs auth"),
    ("/admin/reset-queue", "GET", (200,), "page (client-side AuthGate)"),
    ("/api/devices/00000000-0000-0000-0000-000000000000/availability", "GET", (401, 403, 404), "availability endpoint exists"),
]

failed = 0
for path, method, expected, note in CHECKS:
    req = urllib.request.Request(BASE + path, method=method, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        status = resp.status
    except urllib.error.HTTPError as e:
        status = e.code
    ok = status in expected
    marker = "✓" if ok else "✗"
    print(f"  {marker} {method} {path}  →  {status}  ({note}; expected one of {expected})")
    if not ok:
        failed += 1

print(f"\n{'OK' if failed == 0 else 'FAIL'}: {len(CHECKS) - failed}/{len(CHECKS)} routes responded as expected.")
sys.exit(1 if failed else 0)
