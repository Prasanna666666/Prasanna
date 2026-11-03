"""Time and date from the local clock. No network, ever."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ..module import Module, S, Tool


def current_time(conn, a):
    tz = a.get("timezone") or "Asia/Kolkata"
    try:
        now = datetime.now(ZoneInfo(tz))
    except Exception as e:
        raise ValueError(f"unknown timezone {tz!r} (use e.g. Asia/Kolkata, Europe/London)") from e
    return {"timezone": tz, "iso": now.isoformat(timespec="minutes"), "weekday": now.strftime("%A")}


MODULE = Module("clock", (), (
    Tool("current_time", "Current local time in an IANA timezone (from the computer's clock).",
         {"timezone": S("e.g. Asia/Kolkata, America/New_York")}, current_time),
))
