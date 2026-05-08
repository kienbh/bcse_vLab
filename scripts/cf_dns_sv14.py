"""Create/update Cloudflare CNAME `sv14.bcse-vju.com` → `bcse-vju.com` (proxied).

Usage:
    python scripts/cf_dns_sv14.py
    python scripts/cf_dns_sv14.py --name sv14            # default
    python scripts/cf_dns_sv14.py --name lab             # if you want lab.bcse-vju.com instead
    python scripts/cf_dns_sv14.py --delete               # remove the record
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

CF_API_TOKEN = os.environ.get(
    "CF_API_TOKEN", "7_RQ60b8dFfUTDzW2699TwbfNxVKBAEvurMKRmfI"
)
CF_ZONE_ID = os.environ.get(
    "CF_ZONE_ID", "bdc4164b6e18e3efefef1f710758bec6"
)
ZONE_NAME = "bcse-vju.com"


def _cf(method: str, path: str, body: dict | None = None) -> dict:
    req = Request(
        f"https://api.cloudflare.com/client/v4{path}",
        method=method,
        headers={
            "Authorization": f"Bearer {CF_API_TOKEN}",
            "Content-Type": "application/json",
        },
        data=json.dumps(body).encode() if body is not None else None,
    )
    try:
        with urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        return json.loads(e.read().decode())


def find_record(name: str) -> dict | None:
    fqdn = f"{name}.{ZONE_NAME}"
    res = _cf("GET", f"/zones/{CF_ZONE_ID}/dns_records?name={fqdn}&type=CNAME")
    if res.get("success") and res.get("result"):
        return res["result"][0]
    return None


def upsert(name: str) -> None:
    fqdn = f"{name}.{ZONE_NAME}"
    body = {
        "type": "CNAME",
        "name": fqdn,
        "content": ZONE_NAME,
        "ttl": 1,             # auto
        "proxied": True,
        "comment": "VJU Hardware Lab Portal — SV14 (ingress via SV08, ADR-0011)",
    }
    existing = find_record(name)
    if existing:
        print(f"[cf] updating {fqdn} (id={existing['id']})")
        res = _cf("PUT", f"/zones/{CF_ZONE_ID}/dns_records/{existing['id']}", body)
    else:
        print(f"[cf] creating {fqdn}")
        res = _cf("POST", f"/zones/{CF_ZONE_ID}/dns_records", body)
    if res.get("success"):
        rec = res["result"]
        print(f"[cf] OK — {rec['name']} → {rec['content']} proxied={rec['proxied']}")
    else:
        print(f"[cf] FAILED: {json.dumps(res, indent=2)}")
        sys.exit(1)


def delete(name: str) -> None:
    rec = find_record(name)
    if not rec:
        print(f"[cf] no record for {name}.{ZONE_NAME}")
        return
    res = _cf("DELETE", f"/zones/{CF_ZONE_ID}/dns_records/{rec['id']}")
    if res.get("success"):
        print(f"[cf] deleted {rec['name']}")
    else:
        print(f"[cf] FAILED: {json.dumps(res, indent=2)}")
        sys.exit(1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="sv14")
    ap.add_argument("--delete", action="store_true")
    args = ap.parse_args()

    if args.delete:
        delete(args.name)
    else:
        upsert(args.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
