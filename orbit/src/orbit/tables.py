"""Statements as TABLES, read by code and proved by arithmetic. The local model never copies a number.

The model is shown the first lines of a file and says only what the LAYOUT is: which column is the date, the description, the money out, the
money in, the balance; how dates are written; how numbers are written. Plain code then reads every line with that layout, so there are no swapped
digits and no invented lines. Then the result is PROVED:
  - every line is a transaction, the continuation of one, a balance line, or ignored text; a line with an amount that is none of these is reported;
  - the running balances must add up from line to line (printed order or exactly reversed); where they do not, nothing from the file is imported.
A file ends as 'verified' (the balances add up), 'unverified' (no balances to check against, so imported but marked) or 'needs_check' (not imported).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation

from .statements import Txn

ROLES = ("date", "description", "debit", "credit", "amount", "direction", "balance", "ignore")
LAYOUT_SCHEMA = {
    "type": "object",
    "properties": {
        "header_line": {"type": "integer"},  # index of the line holding the column titles, -1 if none
        "roles": {"type": "array", "items": {"type": "string", "enum": list(ROLES)}},  # one per cell of the header line, left to right
        "date_format": {"type": "string"},  # Python strptime, e.g. %d-%m-%Y, %d %b %Y, %Y-%m-%d
        "month_names": {"type": "array", "items": {"type": "string"}},  # the 12 month names exactly as printed, or [] when months are numbers
        "decimal": {"type": "string"}, "thousands": {"type": "string"},  # as printed: "," and "." for 1.234,56
        "debit_words": {"type": "array", "items": {"type": "string"}}, "credit_words": {"type": "array", "items": {"type": "string"}},  # words marking direction (Af/Bij, Dr/Cr)
        "date_on_every_row": {"type": "boolean"},
    },
    "required": ["header_line", "roles", "date_format", "decimal"],
}
LAYOUT_PROMPT = (
    "You look at the first lines of a bank statement table (any bank, any language). Cells of a line are separated by ' ⟂ '. Each line is numbered. "
    "Describe ONLY the layout; never copy amounts. header_line = the number of the line with the column titles (-1 if none). roles = for each cell of THAT "
    "line from left to right, one of: date, description, debit (money out), credit (money in), amount (one column for both, possibly with a minus sign), "
    "direction (a column saying Af/Bij, Dr/Cr, debit/credit), balance (the running balance), ignore. date_format = the Python strptime format dates "
    "use (use %b for abbreviated month names and %B for full ones). month_names = the 12 month names as printed, in order, if months are words, else []. "
    "decimal and thousands = the characters used in numbers, e.g. decimal ',' thousands '.' for 1.234,56. debit_words and credit_words = the exact words "
    "that mark direction in a direction column or after an amount. date_on_every_row = true if every transaction line starts with its own date."
)
CURRENCY = re.compile(r"[€$£₹]|\b(?:eur|usd|inr|gbp|rs)\b\.?", re.IGNORECASE)


@dataclass(frozen=True)
class Cell:
    x0: float
    x1: float
    text: str


@dataclass
class Layout:
    header_line: int
    roles: list[str]
    date_format: str
    decimal: str = "."
    thousands: str = ""
    month_names: list[str] = field(default_factory=list)
    debit_words: list[str] = field(default_factory=list)
    credit_words: list[str] = field(default_factory=list)
    date_on_every_row: bool = True


@dataclass
class Parsed:
    txns: list[Txn]
    status: str  # verified | unverified | needs_check
    issues: list[str] = field(default_factory=list)
    checked: int = 0  # balance checkpoints that matched


# ---------------------------------------------------------------------------------------------------------------------------
def table_from_data(data: dict) -> list[list[Cell]]:
    """The cells of every line, from a parsed PDF (with positions) or a CSV (columns stand in for positions)."""
    if isinstance(data.get("table"), list):
        out = []
        for line in data["table"]:
            cells = [Cell(float(c[0]), float(c[1]), str(c[2])) for c in line if isinstance(c, list) and len(c) == 3]
            if cells:
                out.append(cells)
        return out
    if isinstance(data.get("rows"), list):
        return [[Cell(i * 100.0, i * 100.0 + 99, str(c)) for i, c in enumerate(r) if str(c).strip()] for r in data["rows"] if isinstance(r, list) and any(str(c).strip() for c in r)]
    return []


def infer_layout(client, model: str, table: list[list[Cell]]) -> Layout | None:
    """Ask the local model what the columns are. Only a layout comes back; it is checked before use."""
    if not table:
        return None
    shown = "\n".join(f"{i}: " + " ⟂ ".join(c.text for c in line) for i, line in enumerate(table[:45]))
    msg = client.chat(model, [{"role": "system", "content": LAYOUT_PROMPT}, {"role": "user", "content": shown}], schema=LAYOUT_SCHEMA)
    try:
        d = json.loads(msg.get("content") or "{}")
        header = int(d["header_line"])
        roles = [r if r in ROLES else "ignore" for r in d["roles"]]
    except (ValueError, KeyError, TypeError):
        return None
    if not 0 <= header < len(table) or len(roles) != len(table[header]) or "date" not in roles:
        return None
    if not (("debit" in roles or "credit" in roles) or "amount" in roles):
        return None
    words = lambda k: [str(w).strip().lower() for w in d.get(k, []) if str(w).strip()]  # noqa: E731
    return Layout(header, roles, str(d["date_format"]), str(d.get("decimal") or ".")[:1] or ".", str(d.get("thousands") or "")[:1],
                  [str(m).strip().lower() for m in d.get("month_names", [])][:12], words("debit_words"), words("credit_words"), bool(d.get("date_on_every_row", True)))


def parse_date(text: str, layout: Layout) -> str | None:
    s = " ".join(text.replace(",", " ").split()).strip(" .")
    if len(layout.month_names) == 12:
        english = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
        full = "%B" in layout.date_format

        def swap(m: re.Match) -> str:
            word = m.group(0).lower().rstrip(".")
            for i, name in enumerate(layout.month_names):
                if word == name.rstrip(".") or (len(word) >= 3 and name.startswith(word)):
                    return english[i] if full else english[i][:3]
            return m.group(0)

        s = re.sub(r"[A-Za-zÀ-ÿ]+\.?", swap, s)
    fmt = " ".join(layout.date_format.replace(",", " ").split())
    try:
        d = datetime.strptime(s, fmt).date()
    except ValueError:
        return None
    return d.isoformat() if 1990 <= d.year <= 2100 else None


def parse_money(text: str, layout: Layout) -> tuple[int, str | None] | None:
    """(signed minor units, 'dr'|'cr'|None) read with the layout's own number notation. None if the cell is not an amount."""
    s = text.strip()
    if not s:
        return None
    side = None
    low = s.lower()
    for word, tag in [(w, "dr") for w in layout.debit_words] + [(w, "cr") for w in layout.credit_words]:
        if low.endswith(" " + word) or low.startswith(word + " ") or low == word:
            side, s = tag, s[: len(s) - len(word)].strip() if low.endswith(word) else s[len(word):].strip()
            break
    s = CURRENCY.sub("", s).replace("+", "").replace(" ", "").replace(" ", "")
    negative = s.startswith("-") or s.endswith("-") or (s.startswith("(") and s.endswith(")"))
    s = s.strip("()-")
    if layout.thousands:
        s = s.replace(layout.thousands, "")
    if layout.decimal != ".":
        s = s.replace(layout.decimal, ".")
    if not re.fullmatch(r"\d+(\.\d+)?", s):
        return None
    try:
        minor = int((Decimal(s) * 100).to_integral_value())
    except InvalidOperation:
        return None
    return (-minor if negative else minor), side


def money_from_printed(text: str) -> int | None:
    """An amount exactly as printed in a document ('3.500,00', '1,234.56', '€ 61'): the notation is read from the figure itself."""
    s = CURRENCY.sub("", str(text)).replace(" ", "").replace(" ", "").strip("()+-")
    if not re.fullmatch(r"\d[\d.,]*", s):
        return None
    m = re.search(r"[.,](\d{1,2})$", s)
    whole, frac = (s[: m.start()], m.group(1)) if m else (s, "0")
    whole = re.sub(r"[.,]", "", whole)
    return int(whole) * 100 + int(frac.ljust(2, "0")) if whole.isdigit() else None


# ---------------------------------------------------------------------------------------------------------------------------
def _assign(line: list[Cell], columns: list[tuple[float, float, str]]) -> dict[int, str]:
    """Which column each cell of a line falls in (by horizontal overlap; nearest centre if none), cell texts joined per column."""
    out: dict[int, list[str]] = {}
    for c in line:
        best, best_overlap = None, 0.0
        for i, (x0, x1, _) in enumerate(columns):
            overlap = min(c.x1, x1) - max(c.x0, x0)
            if overlap > best_overlap:
                best, best_overlap = i, overlap
        if best is None:
            centre = (c.x0 + c.x1) / 2
            best = min(range(len(columns)), key=lambda i: abs((columns[i][0] + columns[i][1]) / 2 - centre))
        out.setdefault(best, []).append(c.text)
    return {i: " ".join(v) for i, v in out.items()}


def parse_table(table: list[list[Cell]], layout: Layout) -> Parsed:
    columns = [(c.x0, c.x1, role) for c, role in zip(table[layout.header_line], layout.roles, strict=True)]
    role_of = {i: r for i, (_, _, r) in enumerate(columns)}
    header_text = [c.text.strip().lower() for c in table[layout.header_line]]
    issues: list[str] = []
    rows: list[dict] = []  # day, amount (signed or None), kind, desc, balance
    day = None
    for n, line in enumerate(table):
        if n <= layout.header_line or [c.text.strip().lower() for c in line] == header_text:
            continue  # titles, and the titles repeated on every page
        cols = _assign(line, columns)
        text = {r: " ".join(v for i, v in cols.items() if role_of[i] == r).strip() for r in ROLES}
        d = parse_date(text["date"], layout) if text["date"] else None
        debit = parse_money(text["debit"], layout) if text["debit"] else None
        credit = parse_money(text["credit"], layout) if text["credit"] else None
        amount = parse_money(text["amount"], layout) if text["amount"] else None
        balance = parse_money(text["balance"], layout) if text["balance"] else None
        has_money = any(x is not None and x[0] != 0 for x in (debit, credit, amount))
        if d is None and not has_money and balance is None:
            if text["description"] and rows and not text["date"]:
                rows[-1]["desc"] += " " + text["description"]  # a description continued on the next line
            continue
        if d is not None and not has_money:
            if balance is not None:
                rows.append({"day": d, "amount": None, "kind": None, "desc": text["description"], "balance": balance[0], "checkpoint": True})  # e.g. an opening balance
            continue
        if has_money:
            if d is None and not layout.date_on_every_row and day:
                d = day  # this statement prints a date once for several lines
            if d is None:
                issues.append(f"line {n} has an amount but no date")
                continue
            day = d
            kind, minor = None, None
            if debit and debit[0]:
                kind, minor = "expense", abs(debit[0])
            elif credit and credit[0]:
                kind, minor = "income", abs(credit[0])
            elif amount and amount[0]:
                minor = abs(amount[0])
                words = text["direction"].strip().lower()
                side = amount[1] or ("dr" if words in layout.debit_words else "cr" if words in layout.credit_words else None)
                kind = "expense" if (amount[0] < 0 or side == "dr") else "income" if side == "cr" else None
            rows.append({"day": d, "amount": minor, "kind": kind, "desc": text["description"], "balance": balance[0] if balance else None})
        elif d is not None and text["description"] == "" and balance is None:
            issues.append(f"line {n} has a date but nothing else")
    txns, status, checked = _prove(rows, issues)
    return Parsed(txns, status, issues, checked)


def _score(seq: list[dict]) -> int:
    """Walk the lines in this order: +1 for every balance that follows from the one before, -1 for every one that does not."""
    running, score = None, 0
    for r in seq:
        if r.get("checkpoint"):
            if running is not None:
                score += 1 if running == r["balance"] else -1
            running = r["balance"]
        elif r["amount"] is not None:
            options = [r["amount"], -r["amount"]] if r["kind"] is None else [r["amount"] if r["kind"] == "income" else -r["amount"]]
            if running is not None and r["balance"] is not None:
                score += 1 if any(running + o == r["balance"] for o in options) else -1
            running = r["balance"] if r["balance"] is not None else (running + options[0] if running is not None and len(options) == 1 else None)
    return score


def _prove(rows: list[dict], issues: list[str]) -> tuple[list[Txn], str, int]:
    """Put the lines in their true order, settle unknown directions with the balances, and make sure the balances add up.
    Returns (transactions, status, balance checks that matched)."""
    ordered = rows[::-1] if _score(rows[::-1]) > _score(rows) else rows  # a newest-first statement prints its balances in reverse
    running, matched, broken = None, 0, 0
    out: list[Txn] = []
    for r in ordered:
        if r.get("checkpoint"):
            if running is not None:
                matched, broken = (matched + 1, broken) if running == r["balance"] else (matched, broken + 1)
            running = r["balance"]
            continue
        if r["amount"] is None:
            continue
        kind = r["kind"]
        if kind is None and running is not None and r["balance"] is not None:
            kind = "income" if running + r["amount"] == r["balance"] else "expense" if running - r["amount"] == r["balance"] else None
        if kind is None:
            issues.append(f"cannot tell whether {r['day']} {r['amount'] / 100:.2f} is money in or out")
            running = r["balance"]
            continue
        signed = r["amount"] if kind == "income" else -r["amount"]
        if r["balance"] is not None:
            if running is not None:
                matched, broken = (matched + 1, broken) if running + signed == r["balance"] else (matched, broken + 1)
            running = r["balance"]
        elif running is not None:
            running += signed
        out.append(Txn(r["day"], r["amount"], kind, " ".join(r["desc"].split())[:300], r["balance"]))
    if broken:
        issues.append(f"the balances do not add up at {broken} place(s)")
    if not out and not issues:
        issues.append("no transactions were found")
    if issues:
        return out, "needs_check", matched
    return (out, "verified", matched) if matched >= 1 else (out, "unverified", 0)
