"""Which currency a statement is in, from what it prints. Code only: ISO codes and symbols are counted; if it is not clear, the answer is 'unknown'."""

from __future__ import annotations

import re

CODES = ("EUR", "INR", "USD", "GBP", "CHF", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF", "CAD", "AUD", "NZD", "JPY", "CNY", "SGD", "AED", "ZAR", "TRY", "BRL")
SYMBOLS = {"€": "EUR", "₹": "INR", "£": "GBP"}


def detect(text: str) -> str:
    """The statement's currency: the code or symbol it prints, if one clearly dominates. '' when it says nothing or says two things."""
    counts: dict[str, int] = {}
    for code in CODES:
        n = len(re.findall(rf"(?<![A-Za-z]){code}(?![A-Za-z])", text))
        if n:
            counts[code] = counts.get(code, 0) + n
    for symbol, code in SYMBOLS.items():
        n = text.count(symbol)
        if n:
            counts[code] = counts.get(code, 0) + n
    n = len(re.findall(r"(?<![A-Za-z])Rs\.?(?![A-Za-z])", text))
    if n:
        counts["INR"] = counts.get("INR", 0) + n
    if not counts:
        return ""
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    if len(ranked) > 1 and ranked[1][1] * 3 > ranked[0][1]:  # two currencies both clearly present: do not guess
        return ""
    return ranked[0][0]
