"""What the app is doing right now, in plain words, for the person waiting (and for the log).

`say("Searching your photos")` is called at each stage of a question. While a question runs, the web page shows the latest words under it, and
every stage is logged with the seconds since the question started, so a stall is visible instead of silent.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextvars import ContextVar

log = logging.getLogger("aperture.progress")
SINK: ContextVar[Callable[[str], None] | None] = ContextVar("aperture_progress", default=None)
STARTED: ContextVar[float | None] = ContextVar("aperture_progress_start", default=None)


def begin(sink: Callable[[str], None] | None) -> None:
    SINK.set(sink)
    STARTED.set(time.monotonic())


def say(text: str) -> None:
    started = STARTED.get()
    log.info("stage: %s (+%.1fs)", text, 0.0 if started is None else time.monotonic() - started)
    sink = SINK.get()
    if sink is not None:
        try:
            sink(text)
        except Exception:  # showing progress must never break an answer
            pass
