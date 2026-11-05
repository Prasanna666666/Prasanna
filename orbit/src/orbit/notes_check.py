"""Your own calculations, checked. Reads the notes you imported (Apple Notes), finds blocks like

    Asian games 2026        <- title
    Tickets: 634.1          <- lines: label, amount (refunds negative)
    Flights: 1179.31
    Total: 2438.36          <- the total you wrote

and (1) checks the arithmetic inside the note itself, to the cent, and (2) compares the note with what the app computed for the same event.
Plain code, exact integer arithmetic: the notes are not trusted, and neither is the app until the two agree.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from .tables import money_from_printed
from .verify import Finding

MARKS = "✅✔✓☑✔️"
AMOUNT_LINE = re.compile(r"^(?P<label>[^:=\n]{1,60}?)\s*[:=]\s*(?P<amt>[-−–]?\s*(?:€|EUR|₹|Rs\.?)?\s*\d[\d.,]*)\s*(?:EUR|€)?\s*$", re.IGNORECASE)
TOTAL = re.compile(r"^(total|totaal|sum|grand total|net)\b", re.IGNORECASE)


@dataclass
class Block:
    title: str
    note: str
    items: list[tuple[str, int]] = field(default_factory=list)
    total: int | None = None


def _clean(line: str) -> str:
    return " ".join(line.translate({ord(c): None for c in MARKS}).split()).strip()


def _amount(text: str) -> int | None:
    t = text.strip()
    minor = money_from_printed(t)
    if minor is None:
        return None
    return -minor if t.startswith(("-", "−", "–")) else minor


def blocks_of(title: str, body: str) -> list[Block]:
    """Every titled group of 'label: amount' lines in a note. A section header like 'Shows:' or 'Cancelled:' is not a title."""
    out: list[Block] = []
    current: Block | None = None
    for raw in body.replace("\r", "").split("\n"):
        line = _clean(raw)
        if not line:
            current = None
            continue
        m = AMOUNT_LINE.match(line)
        amount = _amount(m.group("amt")) if m else None
        if m and amount is not None:
            if current is None:
                continue  # an amount with no title above it: nothing to check it against
            label = m.group("label").strip()
            if TOTAL.match(label):
                current.total = amount
            else:
                current.items.append((label, amount))
        elif line.endswith(":"):
            current = None  # a section header
        else:
            current = Block(line, title)
            out.append(current)
    return [b for b in out if b.items or b.total is not None]


def _notes(conn) -> list[tuple[str, str]]:
    return [(r["title"] or "(untitled)", r["body"]) for r in conn.execute("SELECT title, body FROM notes")]


def notes_arithmetic(conn) -> list[Finding]:
    """Do the lines of each calculation in your notes add up to the total you wrote?"""
    out = []
    for title, body in _notes(conn):
        for b in blocks_of(title, body):
            if b.total is None or not b.items:
                continue
            added = sum(a for _, a in b.items)
            if added == b.total:
                out.append(Finding("notes arithmetic", "ok", b.title, f"in your note '{title}': the lines add up to {added / 100:.2f}, as the total says"))
            else:
                out.append(
                    Finding(
                        "notes arithmetic",
                        "fail",
                        b.title,
                        f"in your note '{title}': the lines add up to {added / 100:.2f} but you wrote {b.total / 100:.2f} (difference {(b.total - added) / 100:.2f})",
                    )
                )
    return out


def _match(name: str, events: list[dict]) -> dict | None:
    key = name.lower().strip()
    best, score = None, 0.0
    for e in events:
        s = difflib.SequenceMatcher(None, key, e["name"].lower()).ratio()
        if s > score:
            best, score = e, s
    return best if score >= 0.85 else None


def notes_vs_app(conn) -> list[Finding]:
    """Compare each calculation in your notes with the event of the same name in the app: every line and the total."""
    from .modules import events as events_module

    app = events_module.list_events(conn)
    out = []
    for title, body in _notes(conn):
        for b in blocks_of(title, body):
            if len(b.items) < 1:
                continue
            ev = _match(b.title, app)
            if ev is None:
                out.append(Finding("notes ↔ app", "warn", b.title, f"your note '{title}' has '{b.title}', but the app has no event with that name (yet)"))
                continue
            theirs = {lbl.lower(): amt for lbl, amt in b.items}
            ours = {ln["sub"].lower(): round(ln["amount"] * 100) for ln in ev["lines"]}
            problems = []
            for lbl, amt in theirs.items():
                if lbl not in ours:
                    problems.append(f"'{lbl}' {amt / 100:.2f} is in your note but not in the app")
                elif ours[lbl] != amt:
                    problems.append(f"'{lbl}': note {amt / 100:.2f}, app {ours[lbl] / 100:.2f}")
            for lbl, amt in ours.items():
                if lbl not in theirs:
                    problems.append(f"'{lbl}' {amt / 100:.2f} is in the app but not in your note")
            total = round(ev["total"] * 100)
            if b.total is not None and b.total != total:
                problems.append(f"total: note {b.total / 100:.2f}, app {total / 100:.2f}")
            out.append(
                Finding("notes ↔ app", "ok", ev["name"], f"your note '{title}' and the app agree on every line and the total ({total / 100:.2f})")
                if not problems
                else Finding("notes ↔ app", "fail", ev["name"], "; ".join(problems[:4]))
            )
    return out
