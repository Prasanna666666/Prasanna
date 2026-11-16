"""The same cross-check for every app. Each app hands Atlas plain dated items (a payment from Finance, a trip from Travel, anything another app adds); every open item that the
documents describe is compared with what the other apps know around its dates. The model reads the item and the nearby items of every kind and says which one, if any, belongs to it
and how, quoting that item's own words; the code then verifies the quote and the numbers. A payment counts as full only if its amount is exactly one the item states. Nothing here
is about one app: a new kind of item from a new app is compared the same way. The model is slow, so this runs in the background, one item at a time, and the answers are remembered."""

from __future__ import annotations

import hashlib
import json
import re
import threading
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from kit.text import day

WINDOW_BEFORE, WINDOW_AFTER, MAX_CANDIDATES = 60, 90, 25
CENT = 0.005
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"item": {"type": "integer"}, "relation": {"type": "string", "enum": ["full", "part", "related", "none"]}, "quote": {"type": "string"}},
    "required": ["relation"],
}
PROMPT = (
    "Below is something still open in someone's papers, and numbered items from their other apps around its dates (bank payments, trips, and so on). Say which item, if any, "
    "belongs to it. For a payment: full if it pays all of it, part if it pays only a part. For anything else that is about the same thing: related. none if no item belongs to it. "
    "Give the number of the item and copy from that item the exact words that show it belongs. Never guess."
)


def number(value: Any) -> float | None:
    """An amount as the item states it ("1.234,50", "60,50 EUR", 12.5)."""
    m = re.search(r"\d[\d.,]*", str(value))
    if not m:
        return None
    s = m.group(0).rstrip(".,")
    s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).casefold().strip()


def _text(item: dict[str, Any]) -> str:
    """The words an item carries: what its app wrote about it."""
    return " ".join(str(item.get(k) or "") for k in ("text", "title", "place")).strip()


def _around(matter: dict[str, Any], others: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The items of every other app near the matter's dates, the closest first. (Income is not something a bill is paid with.)"""
    days = [d for x in (matter.get("due"), *(i.get("value") for i in matter.get("dates", []))) if (d := day(x))]
    if not days:
        return []
    lo, hi = min(days) - timedelta(days=WINDOW_BEFORE), max(days) + timedelta(days=WINDOW_AFTER)
    near = [o for o in others if o.get("direction") != "income" and (w := day(o.get("date"))) and lo <= w <= hi]
    mid = min(days)
    return sorted(near, key=lambda o: abs(((day(o["date"]) or mid) - mid).days))[:MAX_CANDIDATES]


def key_of(matter: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps({k: matter.get(k) for k in ("id", "title", "what", "status", "due", "amounts", "dates")}, sort_keys=True, default=str).encode()
    ).hexdigest()[:20]


def _line(n: int, item: dict[str, Any]) -> str:
    amount = f" {item['amount']:.2f}" if isinstance(item.get("amount"), int | float) else ""
    return f"{n}. [{item.get('kind', 'item')}] {item.get('date', '')}{amount} {_text(item)}"


def judge(pick: Callable[..., dict[str, Any] | None], matter: dict[str, Any], others: list[dict[str, Any]]) -> dict[str, Any] | None:
    """How one open item relates to what the other apps know: {"relation": full | part | related | none, ...what it relates to}, everything verified, or None when the model
    could not answer (to be tried again)."""
    near = _around(matter, others)
    if not near:
        return {"relation": "none"}
    about = f"{matter.get('title', '')}: {matter.get('what', '')}. Amounts: " + ", ".join(str(a.get("value")) for a in matter.get("amounts", []))
    asked = "\n".join(_line(n, o) for n, o in enumerate(near, 1))
    data = pick(PROMPT, f"OPEN ITEM: {about}\n\nITEMS FROM OTHER APPS:\n{asked}", SCHEMA)
    if data is None:
        return None
    n, rel = data.get("item"), data.get("relation")
    if rel not in ("full", "part", "related") or not isinstance(n, int) or not 1 <= n <= len(near):
        return {"relation": "none"}
    item = near[n - 1]
    quote = _norm(data.get("quote"))
    if len(quote) < 3 or quote not in _norm(_text(item)):
        return {"relation": "none"}  # no real words of the item to show it belongs: not accepted
    base = {"kind": item.get("kind", "item"), "title": _text(item)[:80], "date": item.get("date", "")}
    if item.get("kind") != "payment" or not isinstance(item.get("amount"), int | float):
        return {**base, "relation": "related"}
    exact = any(abs(item["amount"] - a) < CENT for x in matter.get("amounts", []) if (a := number(x.get("value"))) is not None)
    return {**base, "relation": "full" if rel == "full" and exact else "part", "amount": item["amount"]}


class Crosschecker:
    """Remembers how each open item relates to the other apps' items and fills in the missing ones in the background."""

    def __init__(self, pick: Callable[..., dict[str, Any] | None] | None = None) -> None:
        self.pick = pick
        self._known: dict[str, dict[str, Any]] = {}
        self._busy = threading.Lock()

    def known(self, matters: list[dict[str, Any]]) -> dict[Any, dict[str, Any]]:
        return {m["id"]: self._known[key_of(m)] for m in matters if m.get("open") and key_of(m) in self._known}

    def working(self) -> bool:
        return self._busy.locked()

    def start(self, matters: list[dict[str, Any]], others: list[dict[str, Any]]) -> None:
        """Every open item without an answer is compared in the background, one at a time (the model is shared); what failed is asked again the next time."""
        todo = [m for m in matters if m.get("open") and key_of(m) not in self._known]
        if todo and self.pick is not None and self._busy.acquire(blocking=False):
            threading.Thread(target=self._run, args=(todo, others), daemon=True).start()

    def _run(self, todo: list[dict[str, Any]], others: list[dict[str, Any]]) -> None:
        try:
            for m in todo:
                if self.pick is not None and (result := judge(self.pick, m, others)) is not None:
                    self._known[key_of(m)] = result
        finally:
            self._busy.release()
