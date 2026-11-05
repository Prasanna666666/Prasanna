"""The phrasebook: how people phrase a time, and what each phrasing means (retrieval for the date step).

Two uses, in this order:
1. MATCH - a phrase in the message that fits a known pattern ("the last <N> <unit>", "<N> <unit> ago", "in <month> <year>") gets its meaning
   straight from the phrasebook, exactly and instantly, with no model call.
2. SIMILAR - otherwise the most similar known phrases and their meanings are retrieved and shown to the model as examples, so it decides from
   close precedents instead of guessing.
The phrasebook is data (SEED); the dates themselves are always computed by code (search/dates.py).
"""

from __future__ import annotations

import re
from typing import Any

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "couple": 2,
    "fifteen": 15,
    "twenty": 20,
    "thirty": 30,
}
UNITS = {
    "day": "day",
    "days": "day",
    "week": "week",
    "weeks": "week",
    "month": "month",
    "months": "month",
    "year": "year",
    "years": "year",
}
MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
    )
}
MONTHS.update(
    {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}
)
SEASONS = {"spring", "summer", "autumn", "fall", "winter"}

# pattern -> meaning. <N> is a number, <U> a unit (day/week/month/year). "period" = that one period, "until_now" = from then until today.
PATTERNS: dict[str, dict[str, Any]] = {
    "<N> <U> ago": {"span": "period"},
    "<N> <U> back": {"span": "period"},
    "<N> <U> earlier": {"span": "period"},
    "the last <N> <U>": {"span": "until_now"},
    "last <N> <U>": {"span": "until_now"},
    "the past <N> <U>": {"span": "until_now"},
    "past <N> <U>": {"span": "until_now"},
    "the previous <N> <U>": {"span": "until_now"},
    "previous <N> <U>": {"span": "until_now"},
    "in the last <N> <U>": {"span": "until_now"},
    "in the past <N> <U>": {"span": "until_now"},
    "over the last <N> <U>": {"span": "until_now"},
    "within the last <N> <U>": {"span": "until_now"},
    "during the last <N> <U>": {"span": "until_now"},
}
FIXED: dict[str, dict[str, Any]] = {
    "today": {"relative": "today"},
    "yesterday": {"relative": "yesterday"},
    "this week": {"relative": "this_week"},
    "last week": {"relative": "last_week"},
    "this month": {"relative": "this_month"},
    "last month": {"relative": "last_month"},
    "this year": {"relative": "this_year"},
    "last year": {"relative": "last_year"},
}
# concrete examples shown to the model when no pattern fits (phrase -> meaning)
SEED: list[tuple[str, dict[str, Any]]] = [
    ("the last 3 months", {"ago": 3, "unit": "month", "span": "until_now"}),
    ("the past 2 weeks", {"ago": 2, "unit": "week", "span": "until_now"}),
    ("2 months back", {"ago": 2, "unit": "month", "span": "period"}),
    ("a year ago", {"ago": 1, "unit": "year", "span": "period"}),
    ("recently, in the last few weeks", {"ago": 3, "unit": "week", "span": "until_now"}),
    ("last month", {"relative": "last_month"}),
    ("last year", {"relative": "last_year"}),
    ("this summer", {"season": "summer"}),
    ("last summer", {"season": "summer"}),
    ("winter 2023", {"year": 2023, "season": "winter"}),
    ("in August 2019", {"year": 2019, "month": 8}),
    ("in march", {"month": 3}),
    ("in 2021", {"year": 2021}),
    ("yesterday", {"relative": "yesterday"}),
    ("a couple of months ago", {"ago": 2, "unit": "month", "span": "period"}),
    ("a few months back", {"ago": 3, "unit": "month", "span": "period"}),
    ("earlier this year", {"relative": "this_year"}),
    ("over the past year", {"ago": 1, "unit": "year", "span": "until_now"}),
    ("this weekend", {"relative": "this_week"}),
    ("since last month", {"ago": 1, "unit": "month", "span": "until_now"}),
]
_WORD = re.compile(r"[a-z0-9]+")


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _abstract(words: list[str]) -> tuple[str, int | None, str | None]:
    """The words with the number and unit replaced by <N> and <U>, plus their values."""
    out: list[str] = []
    n: int | None = None
    unit: str | None = None
    for i, w in enumerate(words):
        nxt = words[i + 1] if i + 1 < len(words) else ""
        if w.isdigit() and len(w) <= 3 and nxt in UNITS:
            out.append("<N>")
            n = int(w)
        elif w in NUMBER_WORDS and nxt in UNITS:
            out.append("<N>")
            n = NUMBER_WORDS[w]
        elif w in ("a", "an") and nxt in UNITS:
            out.append("<N>")
            n = 1
        elif w in UNITS and out and out[-1] == "<N>":
            out.append("<U>")
            unit = UNITS[w]
        else:
            out.append(w)
    return " ".join(out), n, unit


def match(text: str) -> tuple[str, dict[str, Any]] | None:
    """A time phrase in the message that fits the phrasebook: (the phrase as written, its meaning), longest phrase first. None if none fits."""
    words = _words(text)
    for size in range(8, 0, -1):
        for start in range(0, len(words) - size + 1):
            window = words[start : start + size]
            template, n, unit = _abstract(window)
            if template in PATTERNS and n is not None and unit is not None:
                return " ".join(window), {"ago": n, "unit": unit, **PATTERNS[template]}
            fixed = " ".join(window)
            if fixed in FIXED:
                return fixed, dict(FIXED[fixed])
    for i, w in enumerate(words):  # "march 2025", "in march", "2019"
        if w in MONTHS and not (w == "may" and i > 0 and words[i - 1] in ("you", "i", "we", "they", "it", "that")):
            year = int(words[i + 1]) if i + 1 < len(words) and words[i + 1].isdigit() and len(words[i + 1]) == 4 else 0
            return (f"{w} {year}" if year else w), ({"month": MONTHS[w], "year": year} if year else {"month": MONTHS[w]})
    for w in words:
        if w.isdigit() and len(w) == 4 and 1990 <= int(w) <= 2099:
            return w, {"year": int(w)}
    return None


def similar(text: str, k: int = 3) -> list[tuple[str, dict[str, Any]]]:
    """The k known phrases most like the message (word overlap after numbers and units are abstracted), for the model to reason from."""
    mine = set(_abstract(_words(text))[0].split()) - {
        "the",
        "a",
        "an",
        "of",
        "in",
        "me",
        "my",
        "show",
        "pics",
        "photos",
        "pictures",
        "from",
        "i",
    }
    scored = []
    for phrase, meaning in SEED:
        theirs = set(_abstract(_words(phrase))[0].split())
        overlap = len(mine & theirs) / max(len(theirs), 1)
        if overlap > 0:
            scored.append((overlap, phrase, meaning))
    scored.sort(key=lambda s: -s[0])
    return [(p, m) for _, p, m in scored[:k]]


def examples_text(text: str) -> str:
    import json

    lines = [f"'{p}' -> {json.dumps({'phrase': p, **m})}" for p, m in similar(text)]
    return ("Similar phrases and what they mean:\n" + "\n".join(lines) + "\n") if lines else ""
