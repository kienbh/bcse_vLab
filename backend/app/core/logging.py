"""Loguru-based structured logging."""
import json
import sys
from typing import Any

from loguru import logger

from app.core.config import get_settings


def _serialize_record(record: dict[str, Any]) -> str:
    payload = {
        "ts": record["time"].isoformat(),
        "level": record["level"].name,
        "logger": record["name"],
        "msg": record["message"],
    }
    if record["extra"]:
        payload["ctx"] = record["extra"]
    if record["exception"]:
        payload["exc"] = str(record["exception"])
    return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging() -> None:
    settings = get_settings()
    logger.remove()
    if settings.LOG_FORMAT == "json":
        logger.add(
            sys.stdout,
            level=settings.LOG_LEVEL,
            serialize=False,
            format=lambda r: _serialize_record(r) + "\n",
        )
    else:
        logger.add(sys.stdout, level=settings.LOG_LEVEL, colorize=True)
