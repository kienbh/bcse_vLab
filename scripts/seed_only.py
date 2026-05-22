"""Fast path: re-run ONLY the DB seed + smoke demo (no rebuild/redeploy).

Use this when the backend/frontend code is already deployed on SV14 but the
seed didn't run (e.g. the earlier image didn't ship scripts/). It copies the
freshly-deployed seed.py into the running container and runs it, then runs the
automated student-session smoke test.

    python scripts/seed_only.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deploy_lab_portal as dlp  # noqa: E402
from demo_setup import run_seed, smoke_demo, log  # noqa: E402


def main() -> int:
    log("Fast seed + smoke (no redeploy)")
    run_seed()
    time.sleep(4)
    smoke_demo()
    log("=" * 60)
    log("DONE. Portal: https://sv14.bcse-vju.com/login")
    log("  sv01@st.vju.ac.vn  /  VJU@2026  (or Demo@2026vju if already changed)")
    log("  then: https://sv14.bcse-vju.com/devices/fpga")
    return 0


if __name__ == "__main__":
    sys.exit(main())
