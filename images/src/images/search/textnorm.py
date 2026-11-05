"""Text normalisation shared by every text-matching engine."""

from __future__ import annotations

import re
import unicodedata

_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def fold(text: str) -> str:
    """Lower-case and strip accents: ``"Zürich"`` -> ``"zurich"``."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.casefold()


def tokens(text: str, min_len: int = 1) -> list[str]:
    """Folded alphanumeric tokens of ``text``."""
    return [t for t in _WORD.findall(fold(text)) if len(t) >= min_len]


def like_escape(text: str) -> str:
    """Escape ``%``/``_``/``\\`` for use with ``LIKE ? ESCAPE '\\'``."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def index_text(*parts: str) -> str:
    """Searchable form stored in the database: folded tokens, space-separated,
    with a leading space so ``LIKE '% word%'`` matches word *starts* only."""
    return " " + " ".join(tokens(" ".join(p for p in parts if p))) + " "
