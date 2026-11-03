"""Small date helpers shared by modules."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta


def parse(value: str) -> date:
    """Accept 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM' and return the date part."""
    return datetime.fromisoformat(value.strip()).date() if "T" in value else date.fromisoformat(value.strip())


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


def next_occurrence(due: str, recurrence: str) -> str | None:
    """Next due value after `due` for daily/weekly/monthly/yearly; keeps any time-of-day."""
    if recurrence in ("", "none"):
        return None
    d = parse(due)
    nd = {
        "daily": d + timedelta(days=1),
        "weekly": d + timedelta(weeks=1),
        "monthly": add_months(d, 1),
        "yearly": add_months(d, 12),
    }.get(recurrence)
    if nd is None:
        raise ValueError(f"unknown recurrence: {recurrence}")
    return nd.isoformat() + (due[10:] if "T" in due else "")


def month_bounds(month: str) -> tuple[str, str]:
    """'2026-11' -> ('2026-11-01', '2026-12-01') (end exclusive)."""
    y, m = int(month[:4]), int(month[5:7])
    start = date(y, m, 1)
    return start.isoformat(), add_months(start, 1).isoformat()
