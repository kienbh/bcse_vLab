"""Read-only: diagnose the /term/ 301 redirect loop on SV14 wetty only."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deploy_lab_portal as dlp  # noqa: E402

CMDS = [
    "docker logs --tail 25 vju-lab-portal-wetty-1 2>&1 | tail -25",
    "docker inspect -f '{{.Config.Cmd}}' vju-lab-portal-wetty-1",
    "curl -s -o /dev/null -D - http://localhost:3001/ 2>&1 | head -10",
    "curl -s -o /dev/null -D - http://localhost:3001/term/ 2>&1 | head -10",
    "curl -s -o /dev/null -D - http://localhost:3001/wetty/ 2>&1 | head -8",
]


def main() -> int:
    j = dlp.jump_client()
    try:
        c = dlp.vps_client(j, dlp.SV14_IP, dlp.SV14_USER, dlp.SV14_PASS)
        try:
            for cmd in CMDS:
                print("\n=== $", cmd[:80])
                dlp.sudo_run(c, cmd, dlp.SV14_PASS, check=False, timeout=40)
        finally:
            c.close()
    finally:
        j.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
