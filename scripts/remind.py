"""Once a day, a macOS notification for what is due: bills (or anything dated) that are overdue, today, or within 3 days. Reads Atlas's home answer from standard input
and prints the text to show (nothing when there is nothing). Only the titles Atlas already shows on its own home page are used."""

import json
import sys

SOON_DAYS = 3


def due_soon(home: dict) -> list[str]:
    items = (home.get("cards", {}).get("calendar", {}) or {}).get("items", []) or []
    out = []
    for item in items:
        value = str(item.get("value", ""))
        parts = value.split()
        days = (
            int(parts[1])
            if len(parts) == 3 and parts[0] == "in" and parts[1].isdigit()
            else None
        )
        if value in ("overdue", "today") or (days is not None and days <= SOON_DAYS):
            out.append(f"{item.get('label', '')} ({value})")
    return out


if __name__ == "__main__":
    try:
        lines = due_soon(json.load(sys.stdin))
    except ValueError:
        lines = []
    if lines:
        print(
            "; ".join(lines[:3])
            + (f" and {len(lines) - 3} more" if len(lines) > 3 else "")
        )
