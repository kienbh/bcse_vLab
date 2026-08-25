"""Health endpoints."""
from datetime import datetime, timezone

from fastapi import APIRouter

from app import __version__
from app.core.config import get_settings

router = APIRouter(tags=["health"])


def _deploy_sha() -> str:
    """Git SHA lúc deploy — file VERSION do deployer ghi (dashboard sv05, A5)."""
    try:
        from pathlib import Path

        return (Path(__file__).resolve().parents[3] / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


@router.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "vju-lab-portal-api",
        "version": __version__,
        "sha": _deploy_sha(),
        "env": get_settings().ENV,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready")
async def ready() -> dict[str, str]:
    return {"status": "ready"}
