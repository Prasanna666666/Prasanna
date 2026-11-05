"""The one place the app asks what day it is, so tests (and a reader of the code) can see where time comes in."""

from __future__ import annotations

from datetime import date


def today() -> date:
    return date.today()  # noqa: DTZ011 - the local calendar day is exactly what is wanted
