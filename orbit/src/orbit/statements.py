"""Turn bank/UPI/card statements (CSV rows or PDF text lines) into transactions. Pure functions: no files, no network.

Banks format statements differently, so nothing here is tied to one bank: the header row is recognised by the words in it
(Date, Narration/Description/Particulars, Debit/Withdrawal, Credit/Deposit, Amount, Dr/Cr, Balance), dates are read
day-first (the Indian convention) in the usual formats, and amounts may carry commas, currency marks, brackets or Dr/Cr.
Anything that is not clearly a transaction row (opening balance, totals, page footers) is skipped, never guessed.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d.%m.%y", "%d %b %Y", "%d-%b-%Y", "%d/%b/%Y", "%d %b %y",
                "%d-%b-%y", "%d %B %Y", "%d-%B-%Y", "%Y-%m-%d", "%Y/%m/%d", "%b %d, %Y", "%d %b, %Y")
YEARS = range(1990, 2100)

COLUMNS = {
    "date": ("transaction date", "txn date", "tran date", "posting date", "date", "value date", "value dt"),
    "desc": ("narration", "transaction remarks", "transaction details", "particulars", "description", "details", "remarks", "merchant"),
    "debit": ("withdrawal amt", "withdrawals", "withdrawal", "debit amount", "debit", "paid out", "money out", "dr amount"),
    "credit": ("deposit amt", "deposits", "deposit", "credit amount", "credit", "paid in", "money in", "cr amount"),
    "amount": ("transaction amount", "amount (inr)", "amount(inr)", "amount in inr", "amount"),
    "type": ("dr/cr", "cr/dr", "debit/credit", "transaction type", "txn type", "type"),
    "balance": ("closing balance", "running balance", "available balance", "balance"),
}


@dataclass(frozen=True)
class Txn:
    day: str  # YYYY-MM-DD
    amount_minor: int  # always positive
    kind: str  # expense | income
    desc: str
    balance_minor: int | None = None


# ---- values -----------------------------------------------------------------------------------------------------------
def parse_date(text: str) -> str | None:
    s = " ".join(str(text).replace(",", ", ").split()).strip(" ,")
    for fmt in DATE_FORMATS:
        try:
            d = datetime.strptime(s, fmt).date()
        except ValueError:
            continue
        if d.year in YEARS:
            return d.isoformat()
    return None


_NUM = re.compile(r"^\(?-?\d[\d,]*(\.\d+)?\)?$")


def parse_amount(text: str) -> tuple[int, str | None] | None:
    """(signed minor units, 'dr'|'cr'|None) from '1,234.50', '(500.00)', '-75', 'Rs. 1,000 Cr', '₹250.00 Dr'. None if it is not an amount."""
    s = str(text).strip()
    if not s:
        return None
    side = None
    m = re.search(r"\b(dr|cr)\.?\s*$", s, re.IGNORECASE) or re.match(r"^(dr|cr)\.?\s", s, re.IGNORECASE)
    if m:
        side = m.group(1).lower()
        s = (s[: m.start()] + s[m.end():]).strip()
    s = re.sub(r"(?i)\b(rs|inr|usd|eur)\b\.?", "", s)
    s = s.replace("₹", "").replace("$", "").replace("€", "").replace(" ", " ").replace(" ", "")
    if not _NUM.match(s):
        return None
    negative = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    try:
        value = Decimal(s.strip("()-").replace(",", ""))
    except InvalidOperation:
        return None
    minor = int((value * 100).to_integral_value())
    return (-minor if negative else minor), side


def normalise(desc: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", desc.lower()).split())


def reference(txn: Txn, occurrence: int) -> str:
    """A stable id for a transaction. The same statement imported twice, or two statements that overlap, give the same ids."""
    key = f"{txn.day}|{txn.amount_minor}|{txn.kind}|{normalise(txn.desc)}|{txn.balance_minor}|{occurrence}"
    return hashlib.sha1(key.encode()).hexdigest()[:24]


def with_references(txns: list[Txn]) -> list[tuple[str, Txn]]:
    seen: dict[tuple, int] = {}
    out = []
    for t in txns:
        k = (t.day, t.amount_minor, t.kind, normalise(t.desc), t.balance_minor)
        n = seen.get(k, 0)
        seen[k] = n + 1
        out.append((reference(t, n), t))
    return out


# ---- CSV rows ---------------------------------------------------------------------------------------------------------
def _map_header(cells: list[str]) -> dict[str, int] | None:
    low = [re.sub(r"\s+", " ", str(c).strip().lower()) for c in cells]
    found: dict[str, int] = {}
    for field, names in COLUMNS.items():
        for name in names:  # earlier names are the stronger match
            hit = next((i for i, c in enumerate(low) if c == name and i not in found.values()), None)
            if hit is None:
                hit = next((i for i, c in enumerate(low) if name in c and i not in found.values() and len(c) < 40), None)
            if hit is not None:
                found[field] = hit
                break
    if "date" in found and ("amount" in found or "debit" in found or "credit" in found):
        return found
    return None


def from_rows(rows: list[list[str]]) -> list[Txn]:
    """Transactions from the rows of a CSV statement (header located within the first 40 rows)."""
    start, cols = None, None
    for i, row in enumerate(rows[:40]):
        cols = _map_header(row)
        if cols:
            start = i
            break
    if start is None or cols is None:
        return []
    out: list[Txn] = []
    for row in rows[start + 1:]:
        def cell(name: str, row: list[str] = row) -> str:
            i = cols.get(name)
            return row[i].strip() if i is not None and i < len(row) else ""

        day = parse_date(cell("date"))
        if day is None:
            continue
        desc = " ".join(cell("desc").split())
        debit, credit, amount = (parse_amount(cell(n)) for n in ("debit", "credit", "amount"))
        balance = parse_amount(cell("balance"))
        kind = minor = None
        if debit and debit[0] and (not credit or not credit[0]):
            kind, minor = "expense", abs(debit[0])
        elif credit and credit[0] and (not debit or not debit[0]):
            kind, minor = "income", abs(credit[0])
        elif amount and amount[0]:
            side = amount[1] or {"dr": "dr", "debit": "dr", "d": "dr", "cr": "cr", "credit": "cr", "c": "cr"}.get(cell("type").lower().strip())
            if side == "dr":
                kind = "expense"
            elif side == "cr":
                kind = "income"
            else:
                kind = "expense" if amount[0] < 0 else "income"
            minor = abs(amount[0])
        if kind and minor:
            out.append(Txn(day, minor, kind, desc, balance[0] if balance else None))
    return out


# ---- PDF / text lines -------------------------------------------------------------------------------------------------
_DATE_AT_START = re.compile(r"^\s*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{1,2}[ \-/][A-Za-z]{3,9}[ \-/,]*\d{2,4}|\d{4}-\d{2}-\d{2})\s+(.*)$")
_MONEY = re.compile(r"(?<![\w/.-])\(?-?(?:Rs\.?|INR|₹)?\s?\d[\d,]*\.\d{2}\)?(?:\s?(?:Cr|Dr|CR|DR))?(?![\w/])")
_INCOME_WORDS = re.compile(r"\b(salary|credit|credited|refund|interest|received|deposit|cashback|reversal)\b", re.IGNORECASE)


def from_lines(lines: list[str]) -> list[Txn]:
    """Transactions from statement text, one visual line per entry: 'DATE description amount [balance]'."""
    out: list[Txn] = []
    previous_balance: int | None = None
    for line in lines:
        m = _DATE_AT_START.match(line)
        if not m:
            continue
        day = parse_date(m.group(1))
        if day is None:
            continue
        rest = m.group(2)
        amounts = list(_MONEY.finditer(rest))
        if not amounts:
            continue
        values = [parse_amount(a.group(0)) for a in amounts]
        if any(v is None for v in values):
            continue
        desc = " ".join(rest[: amounts[0].start()].split())
        if len(values) >= 2:
            (amount, side), balance = values[-2], values[-1][0]
        else:
            (amount, side), balance = values[0], None
        if amount == 0:
            continue
        if side == "dr" or amount < 0:
            kind = "expense"
        elif side == "cr":
            kind = "income"
        elif balance is not None and previous_balance is not None:
            kind = "income" if balance > previous_balance else "expense"  # the running balance says which way the money moved
        else:
            kind = "income" if _INCOME_WORDS.search(desc) else "expense"
        if balance is not None:
            previous_balance = balance
        out.append(Txn(day, abs(amount), kind, desc, balance))
    return out


def from_document(data: dict) -> list[Txn]:
    """Transactions from a parsed document: structured rows (CSV) or reconstructed lines (PDF/text)."""
    rows = data.get("rows")
    if isinstance(rows, list) and rows:
        found = from_rows([[str(c) for c in r] for r in rows if isinstance(r, list)])
        if found:
            return found
    lines = data.get("lines")
    if isinstance(lines, list):
        return from_lines([str(x) for x in lines])
    return []


def span(txns: list[Txn]) -> tuple[date, date] | None:
    days = sorted(date.fromisoformat(t.day) for t in txns)
    return (days[0], days[-1]) if days else None
