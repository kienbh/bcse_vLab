"""Read-only diagnostic: pull backend logs + container state from SV14.

    python scripts/diag.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deploy_lab_portal as dlp  # noqa: E402

CMDS = [
    "docker logs --tail 80 vju-lab-portal-backend-1 2>&1 | "
    "grep -nE 'Traceback|Error|provision|sessions|asyncssh|shell_quote|500' | tail -40",
    "docker exec vju-lab-portal-backend-1 sh -c 'ls -la /app/ssh-keys; echo MOCK=$MOCK_SSH_DEVICES; echo KEYPATH=$BACKEND_SSH_KEY_PATH'",
    "docker exec vju-lab-portal-backend-1 python -c "
    "\"import asyncssh,inspect; print('asyncssh',asyncssh.__version__); "
    "import asyncssh.misc as m; print('has shell_quote:', hasattr(m,'shell_quote'))\"",
]


def main() -> int:
    j = dlp.jump_client()
    try:
        c = dlp.vps_client(j, dlp.SV14_IP, dlp.SV14_USER, dlp.SV14_PASS)
        try:
            for cmd in CMDS:
                print("\n=== $", cmd[:90], "...")
                dlp.sudo_run(c, cmd, dlp.SV14_PASS, check=False, timeout=60)
        finally:
            c.close()
    finally:
        j.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
