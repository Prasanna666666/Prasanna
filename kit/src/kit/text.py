"""Small text and date helpers every layer needs, written once."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any


def squash(s: str) -> str:
    """The text without any whitespace, to find a quoted figure wherever the document broke its line."""
    return re.sub(r"\s+", "", s)


def clean(text: str) -> str:
    """The text without control characters and broken surrogates, keeping line breaks, tabs and every letter of every script."""
    return "".join(ch for ch in text if ch in "\n\t\r" or unicodedata.category(ch) not in ("Cc", "Cs"))


def day(value: Any) -> date | None:
    """A date from the first ten characters of a value written as YYYY-MM-DD, or None."""
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None
