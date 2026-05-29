"""Loguru-based structured logging.

Use a SINK function, not a format function. Loguru's `format=` treats the
returned string as a template with {field} placeholders, so JSON output
containing unescaped `{"ts": ...}` triggers KeyError on the literal field
name `"ts"` at every log call. Sinks bypass that substitution pipeline.
"""
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


def _json_sink(message: Any) -> None:
    """Loguru sink — receives a Message object whose `.record` is the dict."""
    line = _serialize_record(message.record)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def configure_logging() -> None:
    settings = get_settings()
    logger.remove()
    if settings.LOG_FORMAT == "json":
        logger.add(_json_sink, level=settings.LOG_LEVEL, format="{message}")
    else:
        logger.add(sys.stdout, level=settings.LOG_LEVEL, colorize=True)
