"""Amounts exactly as printed in a document."""

from __future__ import annotations

import re

CURRENCY = re.compile(r"[€$£₹]|\b(?:eur|usd|inr|gbp|rs)\b\.?", re.IGNORECASE)


def money_from_printed(text: str) -> int | None:
    """An amount exactly as printed in a document ('3.500,00', '1,234.56', '€ 61'): the notation is read from the figure itself."""
    s = CURRENCY.sub("", str(text)).replace(" ", "").replace(" ", "").strip("()+-")
    if not re.fullmatch(r"\d[\d.,]*", s):
        return None
    m = re.search(r"[.,](\d{1,2})$", s)
    whole, frac = (s[: m.start()], m.group(1)) if m else (s, "0")
    whole = re.sub(r"[.,]", "", whole)
    return int(whole) * 100 + int(frac.ljust(2, "0")) if whole.isdigit() else None
