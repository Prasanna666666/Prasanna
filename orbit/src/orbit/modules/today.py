"""The daily briefing: what needs attention now, drawn from every other module."""

from __future__ import annotations

from datetime import date

from ..module import Module, Tool
from . import money, people, tasks


def briefing_for(conn, today: date) -> dict:
    return {
        "date": today.isoformat(),
        "tasks_due": tasks.overdue_and_today(conn, today),
        "upcoming_dates": people.upcoming(conn, today, 14),
        "money": money.summary(conn, {"month": today.strftime("%Y-%m")}),
    }


def daily_briefing(conn, a):
    return briefing_for(conn, date.today())


MODULE = Module("today", (), (Tool("daily_briefing", "Overdue and due-today tasks, birthdays in the next 14 days, "
                                   "and this month's spending. Use for 'what's on today' or 'brief me'.", {}, daily_briefing),))
