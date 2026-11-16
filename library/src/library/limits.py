"""The limits of reading, declared in `limits.json` (or the file `LIBRARY_LIMITS` points to). Each document records the version of the limits it was read under and which of them cut something
out of it, so a change here finds the documents that were read with something left out and has them read again: no code changes for that."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

PACKAGED = Path(__file__).with_name("limits.json")
DEFAULTS = {
    "max_ocr_pages": 100_000,
    "ocr_budget_seconds": 10**9,
    "max_rows": 5_000_000,
    "max_text_chars": 50_000_000,
    "max_pages": 100_000,
    "line_chars": 5000,
}


def _raw() -> dict:
    try:
        data = json.loads(Path(os.environ.get("LIBRARY_LIMITS", str(PACKAGED))).read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def get(name: str) -> int:
    value = _raw().get(name, DEFAULTS[name])
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else DEFAULTS[name]


def version() -> str:
    """A short fingerprint of the limits in force: it changes whenever one of the numbers does."""
    numbers = {k: get(k) for k in sorted(DEFAULTS)}
    return hashlib.sha256(json.dumps(numbers).encode()).hexdigest()[:12]
