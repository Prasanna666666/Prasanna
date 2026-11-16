"""What the Documents server remembers between requests, and where it keeps what the reader wrote."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from kit import db, llm

from . import pictures


def parsed_dir() -> Path:
    return Path(os.environ.get("ATLAS_PARSED", Path.home() / "AtlasParsed"))


def model_client() -> tuple[Any, str]:
    client = llm.OllamaClient(os.environ.get("OLLAMA_HOST") or None)
    return client, client.resolve(os.environ.get("LIBRARY_MODEL", llm.DEFAULT_MODEL))


class State:
    """What the server remembers between requests: the Update that is running, if any."""

    def __init__(self) -> None:
        self.scan: dict[str, Any] = {"running": False, "progress": "", "summary": "", "problems": [], "now": None}
        self.control = "run"  # run | pause | stop: what the person asked of the Update that is running
        self.lock = threading.Lock()
        self._engine: Any = None

    def engine(self):
        """The picture engine over the drive, or None when pictures are not set up."""
        if self._engine is None and pictures.configured():
            self._engine = pictures.build_engine()
        return self._engine

    def picture_text(self):
        engine = self.engine()
        return pictures.text_sources(engine) if engine is not None else None

    def connect(self):
        conn = db.connect(Path(os.environ.get("ATLAS_HOME", Path.home() / ".atlas")) / "library.db", timeout=60)
        return conn
