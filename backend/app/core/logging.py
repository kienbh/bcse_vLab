"""Loguru-based structured logging."""
import json
import sys

from loguru import logger
from loguru import Message

from app.core.config import get_settings


def _json_sink(message: Message) -> None:
    # Custom sink — bypass Loguru's str.format() so JSON braces in the
    # payload don't get parsed as format placeholders (root cause of the
    # `KeyError: '"ts"'` spam observed in prod on every backend boot).
    record = message.record
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
    sys.stdout.write(json.dumps(payload, default=str, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def configure_logging() -> None:
    settings = get_settings()
    logger.remove()
    if settings.LOG_FORMAT == "json":
        logger.add(_json_sink, level=settings.LOG_LEVEL)
    else:
        logger.add(sys.stdout, level=settings.LOG_LEVEL, colorize=True)
