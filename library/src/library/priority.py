"""The order the apps are served in: the order they are declared in (`apps.py`; `LIBRARY_PRIORITY` overrides it), then the other named folders, then loose files, then mail.
The reader takes the folders in this order, the model identifies the files in this order, and the groups of an app are read as soon as all of that app's files are in:
the person has a finished Finance before Health is started, not a little of everything."""

from __future__ import annotations

import os
import re

from . import apps

LOOSE, MAIL = "", "mail"


def order() -> list[str]:
    """The named apps, first served first (letters, digits, - and _ only: the names go into queries)."""
    override = os.environ.get("LIBRARY_PRIORITY")
    if override is None:
        return apps.names()
    names = (re.sub(r"[^a-z0-9_-]", "", n.strip().lower()) for n in override.split(","))
    return [n for n in names if n]


def rank(area: str) -> int:
    """Where an area comes in the order: the named apps by their place, other folders next, loose files, then mail and pictures last."""
    names = order()
    if area in names:
        return names.index(area)
    return len(names) + (1 if area == LOOSE else 2 if area in (MAIL, "pictures") else 0)


def tiers() -> list[str]:
    """The same order as conditions for a query: each named app, then other folders, then loose files, then mail and pictures."""
    names = order()
    listed = ", ".join(f"'{n}'" for n in [*names, LOOSE, MAIL, "pictures"])
    return [*(f"area='{n}'" for n in names), f"area NOT IN ({listed})", "area=''", "area IN ('mail', 'pictures')"]
