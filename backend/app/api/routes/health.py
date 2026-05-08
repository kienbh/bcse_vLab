"""Health endpoints."""
from datetime import datetime, timezone

from fastapi import APIRouter

from app import __version__
from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "vju-lab-portal-api",
        "version": __version__,
        "env": get_settings().ENV,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready")
async def ready() -> dict[str, str]:
    return {"status": "ready"}
