"""Deterministic date resolution.

The LLM only *labels* a date expression (year / month / season / relative
keyword); this module turns it into an exact range.  LLMs are unreliable at
calendar arithmetic, code is not.

Seasons are meteorological, northern hemisphere: spring = Mar-May,
summer = Jun-Aug, autumn = Sep-Nov, winter = Dec-Feb.  "Winter 2019" is the
winter that *starts* in December 2019.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

SEASON_START_MONTH = {"spring": 3, "summer": 6, "autumn": 9, "winter": 12}
RELATIVE = (
    "today", "yesterday", "this_week", "last_week", "this_month", "last_month", "this_year", "last_year",
)  # fmt: skip


@dataclass(frozen=True)
class DateSpec:
    year: int = 0
    month: int = 0
    season: str = "none"
    relative: str = "none"
    start: str = ""  # explicit ISO dates, inclusive
    end: str = ""

    @property
    def is_empty(self) -> bool:
        return not (self.year or self.month or self.season != "none" or self.relative != "none" or self.start or self.end)


def _month_start(year: int, month: int) -> date:
    return date(year + (month - 1) // 12, (month - 1) % 12 + 1, 1)


def _parse(text: str) -> date | None:
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def resolve(spec: DateSpec, today: date) -> tuple[date, date] | None:
    """``[start, end)`` for the spec, or ``None`` when it is empty/invalid."""
    if spec.is_empty:
        return None
    if spec.start or spec.end:
        start, end = _parse(spec.start), _parse(spec.end)
        if start is None and end is None:
            return None
        start = start or date(1900, 1, 1)
        end_excl = (end + timedelta(days=1)) if end else date(2999, 1, 1)
        return (start, end_excl) if start < end_excl else None
    if spec.relative in RELATIVE:
        return _relative(spec.relative, today)
    year = spec.year if 1800 <= spec.year <= 2999 else 0
    month = spec.month if 1 <= spec.month <= 12 else 0
    if spec.season in SEASON_START_MONTH:
        first = SEASON_START_MONTH[spec.season]
        if not year:  # most recent such season that has started
            year = today.year if _month_start(today.year, first) <= today else today.year - 1
        begin = _month_start(year, first)
        return begin, _month_start(year, first + 3)
    if month and not year:  # most recent past occurrence of that month
        year = today.year if _month_start(today.year, month) <= today else today.year - 1
    if year and month:
        return _month_start(year, month), _month_start(year, month + 1)
    if year:
        return date(year, 1, 1), date(year + 1, 1, 1)
    return None


def _relative(keyword: str, today: date) -> tuple[date, date]:
    if keyword == "today":
        return today, today + timedelta(days=1)
    if keyword == "yesterday":
        return today - timedelta(days=1), today
    week_start = today - timedelta(days=today.weekday())
    if keyword == "this_week":
        return week_start, week_start + timedelta(days=7)
    if keyword == "last_week":
        return week_start - timedelta(days=7), week_start
    if keyword == "this_month":
        return _month_start(today.year, today.month), _month_start(today.year, today.month + 1)
    if keyword == "last_month":
        return _month_start(today.year, today.month - 1), _month_start(today.year, today.month)
    if keyword == "this_year":
        return date(today.year, 1, 1), date(today.year + 1, 1, 1)
    return date(today.year - 1, 1, 1), date(today.year, 1, 1)  # last_year


def describe(spec: DateSpec, today: date) -> str:
    rng = resolve(spec, today)
    if rng is None:
        return ""
    start, end = rng
    return f"{start.isoformat()} to {(end - timedelta(days=1)).isoformat()}"
