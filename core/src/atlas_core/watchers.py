"""Proactive watchers and notifications (Stage 6): they observe and tell the owner; they never act.

A watcher looks at records the Core already holds (a bill due soon, a conflict in the calendar, an unusual transaction) and produces a Notification. A notification carries a kind, a record id and a priority
and NO content (no amount, no title, no name): it is safe to hand to the operating system's notification centre, which the owner's other devices and the lock screen can read. The text the owner sees is
fetched from the Core after the owner opens it, through the normal guarded path. Quiet hours hold non-urgent notifications; the same event is never delivered twice; and a watcher has no way to call the
Action Gateway: at most it names an action the owner may choose to take.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

QUIET_START, QUIET_END = time(22, 0), time(7, 0)
URGENT = "urgent"
DAYS_AHEAD_FOR_BILL = 3


@dataclass(frozen=True)
class Notification:
    kind: str  # bill_due | calendar_conflict | possible_duplicate | unusual_transaction | custom
    record_id: str
    priority: str  # normal | urgent
    dedupe_key: str
    suggested_action: str | None = None  # the NAME of an action the owner may take; never an executed one


def _quiet(now: datetime) -> bool:
    t = now.timetz().replace(tzinfo=None)
    return t >= QUIET_START or t < QUIET_END


def bills_due(items: Iterable[tuple[str, datetime]], now: datetime) -> list[Notification]:
    """`items`: (record id, due moment). Due within three days, not already past by more than a day. Overdue-by-today is urgent."""
    out = []
    for record_id, due in items:
        delta = due - now
        if timedelta(days=-1) <= delta <= timedelta(days=DAYS_AHEAD_FOR_BILL):
            out.append(
                Notification("bill_due", record_id, URGENT if delta <= timedelta(0) else "normal", f"bill_due:{record_id}:{due.date()}", "finance.review_bill")
            )
    return out


def calendar_conflicts(events: Iterable[tuple[str, datetime, datetime]]) -> list[Notification]:
    """Pairs of events whose time ranges overlap (touching ends do not overlap)."""
    ordered = sorted(events, key=lambda e: (e[1], e[0]))
    out = []
    for i, (id_a, _, end_a) in enumerate(ordered):
        for id_b, start_b, _ in ordered[i + 1 :]:
            if start_b >= end_a:
                break
            first, second = sorted((id_a, id_b))
            out.append(Notification("calendar_conflict", second, "normal", f"conflict:{first}:{second}", "calendar.edit"))
    return out


MIN_PHONE_DIGITS = 7


def _phone(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits[-9:] if len(digits) >= MIN_PHONE_DIGITS else ""  # the last nine digits: +31 6 1234 5678 and 06 12345678 are one number


def record_duplicates(domain: str, records: Iterable[tuple[str, str, dict[str, str]]]) -> list[Notification]:
    """Pairs of the owner's own records that look like one thing recorded twice (UC-L23): contacts sharing an email address (without case) or a phone
    number (by its digits), and calendar events with the same title (without case or spacing) and the same start. Reported for the owner to decide;
    nothing is merged or removed, so both originals stay as they are."""
    keys: dict[str, list[str]] = defaultdict(list)
    for record_id, title, fields in records:
        if domain == "contacts":
            email = fields.get("email", "").strip().casefold()
            for key in (f"email:{email}" if email else "", f"phone:{_phone(fields.get('phone', ''))}" if _phone(fields.get("phone", "")) else ""):
                if key:
                    keys[key].append(record_id)
        elif domain == "calendar" and fields.get("starts", "").strip():
            keys[f"event:{' '.join(title.casefold().split())}:{fields['starts'].strip()}"].append(record_id)
    pairs = sorted({tuple(sorted((a, b))) for ids in keys.values() for i, a in enumerate(sorted(set(ids))) for b in sorted(set(ids))[i + 1 :]})
    return [Notification("possible_duplicate", second, "normal", f"duplicate:{first}:{second}", f"{domain}.archive") for first, second in pairs]


class Notifier:
    """Delivers through an injected `deliver` (the OS notification centre on a Mac). Holds quiet-hours notifications until morning and never delivers one event twice."""

    def __init__(self, deliver: Callable[[Notification], None], clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._deliver, self._clock = deliver, clock
        self._seen: set[str] = set()
        self.held: list[Notification] = []

    def offer(self, notification: Notification) -> str:
        if notification.dedupe_key in self._seen:
            return "duplicate"
        if _quiet(self._clock()) and notification.priority != URGENT:
            if all(h.dedupe_key != notification.dedupe_key for h in self.held):
                self.held.append(notification)
            return "held"
        self._seen.add(notification.dedupe_key)
        self._deliver(notification)
        return "delivered"

    def release_held(self) -> int:
        """Called when quiet hours end: delivers what was held, once each."""
        if _quiet(self._clock()):
            return 0
        pending, self.held = self.held, []
        for n in pending:
            if n.dedupe_key not in self._seen:
                self._seen.add(n.dedupe_key)
                self._deliver(n)
        return len(pending)


def push_payload(notification: Notification) -> dict[str, str]:
    """What may leave the Mac for a push service (Stage 8): a kind and a record id, nothing else. The phone fetches the text from the Core, over the authenticated channel, after the owner opens it."""
    return {"k": notification.kind, "id": notification.record_id}
