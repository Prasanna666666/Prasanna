"""Pause and stop: the two flags the person sets, and the wait that honours them."""

from __future__ import annotations

import os
import time
from pathlib import Path

PAUSE = ".pause"  # while it exists the reader waits where it is; remove it and it carries on


STOP = ".stop"  # while it exists the round in progress ends at the next safe point


GENTLE_SECONDS = float(
    os.environ.get("LIBRARY_GENTLE_SECONDS", "0")
)  # a short rest after every batch, so the computer stays responsive while a big mailbox is read
MAX_NESTING = 2  # how deep a package inside a package inside a mail is opened


class Halted(Exception):
    """The person pressed Stop while the reader was still looking through the folders."""


CHECK_EVERY = 200  # files looked at between two looks at Pause and Stop


def halted(out: Path) -> bool:
    """Wait while paused; true when stopped. Called often during the walks through the folders, so Pause and Stop work there too, not only between batches."""
    while (out / PAUSE).exists() and not (out / STOP).exists():
        time.sleep(1)
    return (out / STOP).exists()
