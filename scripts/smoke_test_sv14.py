"""Post-deploy smoke test — hits sv14.bcse-vju.com through Cloudflare.

Usage:
    python scripts/smoke_test_sv14.py
    python scripts/smoke_test_sv14.py --base https://sv14.bcse-vju.com
"""
from __future__ import annotations

import argparse
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def hit(url: str, expect_status: int = 200) -> tuple[bool, str]:
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json"})
    try:
        with urlopen(req, timeout=15) as resp:
            ok = resp.status == expect_status
            body = resp.read(4096).decode(errors="replace")
            return ok, f"{resp.status} | {body[:200]}"
    except HTTPError as e:
        return False, f"HTTPError {e.code}: {e.reason}"
    except URLError as e:
        return False, f"URLError: {e.reason}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://sv14.bcse-vju.com")
    args = ap.parse_args()

    checks = [
        (f"{args.base}/", 200),
        (f"{args.base}/api/health", 200),
        (f"{args.base}/api/ready", 200),
    ]

    failed = 0
    for url, expect in checks:
        ok, info = hit(url, expect)
        marker = "✓" if ok else "✗"
        print(f"  {marker} {url}  →  {info}")
        if not ok:
            failed += 1

    if failed:
        print(f"[smoke] {failed} check(s) failed", file=sys.stderr)
        return 1
    print("[smoke] all good")
    return 0


if __name__ == "__main__":
    sys.exit(main())
