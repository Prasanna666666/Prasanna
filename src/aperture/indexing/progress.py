"""Scan progress file (polled by the UI) and single-instance lock."""

from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path
from typing import Any

from ..config import Paths


class ProgressReporter:
    """Throttled, atomic writer of ``progress.json``."""

    def __init__(self, paths: Paths) -> None:
        self._file = paths.progress_file
        self._last = 0.0
        self.state: dict[str, Any] = {
            "state": "starting",
            "stage": "",
            "total": 0,
            "done": 0,
            "errors": 0,
            "current": "",
            "message": "",
            "eta": None,
            "started": time.time(),
            "pid": os.getpid(),
        }

    def update(self, force: bool = False, **fields: Any) -> None:
        self.state.update(fields)
        now = time.time()
        if force or now - self._last > 0.7:
            self._last = now
            self.state["updated"] = now
            tmp = self._file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.state))
            os.replace(tmp, self._file)


def read_progress(paths: Paths) -> dict[str, Any] | None:
    try:
        data = json.loads(paths.progress_file.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


class ScanLock:
    """PID-file lock so only one scan runs at a time."""

    def __init__(self, paths: Paths) -> None:
        self._file: Path = paths.scan_pid

    def running(self) -> bool:
        try:
            os.kill(int(self._file.read_text().strip()), 0)
        except (OSError, ValueError):
            return False
        return True

    def acquire(self) -> bool:
        if self.running():
            return False
        self._file.write_text(str(os.getpid()))
        return True

    def release(self) -> None:
        self._file.unlink(missing_ok=True)

    def stop(self) -> None:
        """Ask a running scan to finish its current files and exit cleanly."""
        try:
            os.kill(int(self._file.read_text().strip()), signal.SIGTERM)
        except (OSError, ValueError):
            pass
