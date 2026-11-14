"""Which bank payment settles which matter. The model reads the matter and the payments around its date and says which payment, if any, is for it and whether it covers all or
part of it, quoting the payment's own words. Then the numbers are checked exactly: a payment counts as full only if its amount is exactly one the matter states. The model is slow,
so this runs in the background, a few matters at a time, and the answers are remembered; the calendar uses what is known and does not wait."""

from __future__ import annotations

import hashlib
import json
import re
import threading
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

WINDOW_BEFORE, WINDOW_AFTER, MAX_PAYMENTS = 60, 90, 25
CENT = 0.005
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"payment": {"type": "integer"}, "relation": {"type": "string", "enum": ["full", "part", "none"]}, "quote": {"type": "string"}},
    "required": ["relation"],
}
PROMPT = (
    "Below is a matter in someone's papers that is still open, and numbered bank payments from around its date. Say which payment, if any, is for this matter: "
    "full if it pays all of it, part if it pays only a part, none if no payment is for it. Give the number of the payment and copy from that payment the exact words "
    "that show it is for this matter. Never guess."
)


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        return None


def number(value: Any) -> float | None:
    """An amount as the matter states it ("1.234,50", "60,50 EUR", 12.5)."""
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


def _around(matter: dict[str, Any], payments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The payments near the matter's dates, the closest first."""
    days = [d for x in (matter.get("due"), *(i.get("value") for i in matter.get("dates", []))) if (d := _day(x))]
    if not days:
        return []
    lo, hi = min(days) - timedelta(days=WINDOW_BEFORE), max(days) + timedelta(days=WINDOW_AFTER)
    near = [p for p in payments if p.get("direction") == "expense" and (w := _day(p.get("date"))) and lo <= w <= hi]
    mid = min(days)
    return sorted(near, key=lambda p: abs(((_day(p["date"]) or mid) - mid).days))[:MAX_PAYMENTS]


def key_of(matter: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps({k: matter.get(k) for k in ("id", "title", "what", "status", "due", "amounts", "dates")}, sort_keys=True, default=str).encode()
    ).hexdigest()[:20]


def judge(pick: Callable[..., dict[str, Any] | None], matter: dict[str, Any], payments: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The settlement of one matter: {"relation", "amount", "date"} with everything verified, or None when the model could not answer (to be tried again)."""
    near = _around(matter, payments)
    if not near:
        return {"relation": "none"}
    asked = "\n".join(f"{n}. {p['date']} {p['amount']:.2f} {p.get('text', '')}" for n, p in enumerate(near, 1))
    about = f"{matter.get('title', '')}: {matter.get('what', '')}. Amounts: " + ", ".join(str(a.get("value")) for a in matter.get("amounts", []))
    data = pick(PROMPT, f"MATTER: {about}\n\nPAYMENTS:\n{asked}", SCHEMA)
    if data is None:
        return None
    n, rel = data.get("payment"), data.get("relation")
    if rel not in ("full", "part") or not isinstance(n, int) or not 1 <= n <= len(near):
        return {"relation": "none"}
    pay = near[n - 1]
    q = _norm(data.get("quote"))
    if len(q) < 3 or q not in _norm(pay.get("text")):
        return {"relation": "none"}  # no real words of the payment to show it: not accepted
    exact = any(abs(pay["amount"] - a) < CENT for x in matter.get("amounts", []) if (a := number(x.get("value"))) is not None)
    return {"relation": "full" if rel == "full" and exact else "part", "amount": pay["amount"], "date": pay["date"]}


class Settler:
    """Remembers each matter's settlement and fills in the missing ones in the background, a few per round."""

    def __init__(self, pick: Callable[..., dict[str, Any] | None] | None = None) -> None:
        self.pick = pick
        self._known: dict[str, dict[str, Any]] = {}
        self._busy = threading.Lock()

    def known(self, matters: list[dict[str, Any]]) -> dict[Any, dict[str, Any]]:
        return {m["id"]: self._known[key_of(m)] for m in matters if m.get("open") and key_of(m) in self._known}

    def working(self) -> bool:
        return self._busy.locked()

    def start(self, matters: list[dict[str, Any]], payments: list[dict[str, Any]]) -> None:
        """Every open matter without an answer is judged in the background, one at a time (the model is shared); what failed is asked again the next time."""
        todo = [m for m in matters if m.get("open") and key_of(m) not in self._known]
        if todo and self.pick is not None and self._busy.acquire(blocking=False):
            threading.Thread(target=self._run, args=(todo, payments), daemon=True).start()

    def _run(self, todo: list[dict[str, Any]], payments: list[dict[str, Any]]) -> None:
        try:
            for m in todo:
                if self.pick is not None and (result := judge(self.pick, m, payments)) is not None:
                    self._known[key_of(m)] = result
        finally:
            self._busy.release()
