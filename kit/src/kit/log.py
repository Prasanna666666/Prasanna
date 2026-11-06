"""Operational logging that can never leak your finances: an event name and an error type, never a payment, a file's text, a question or an answer.

One JSON object per line in `<data folder>/orbit.log` (rotated at 1 MB, 3 kept). If the file cannot be written, logging goes quietly to stderr instead."""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_NAME = "finance"


class _Json(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "at": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="seconds"),
            "level": record.levelname.lower(),
            "event": record.getMessage(),
        }
        entry.update(getattr(record, "fields", {}))
        return json.dumps(entry)


def logger() -> logging.Logger:
    log = logging.getLogger(_NAME)
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    log.propagate = False
    try:
        path = Path(os.environ.get("ORBIT_HOME", Path.home() / ".orbit"))
        path.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.handlers.RotatingFileHandler(path / "orbit.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    except OSError:
        handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_Json())
    log.addHandler(handler)
    return log


def event(name: str, level: int = logging.INFO, **fields: str | int | float | bool) -> None:
    """Record that something happened. Pass only counts, names of kinds of things and error types, never content."""
    logger().log(level, name, extra={"fields": fields})


def failed(name: str, exc: BaseException, **fields: str | int | float | bool) -> None:
    """Record a failure that was handled on purpose (the app carried on): which event, and the error's type only (its message may quote private text)."""
    event(name, logging.WARNING, error=type(exc).__name__, **fields)
