"""Exact readers for the bank data standards: MT940 (SWIFT) and camt.053 (ISO 20022 XML). No model, no guessing: these formats have defined fields.

Banks such as ABN AMRO let you download transactions as MT940 or camt.053. Every transaction, the opening balance and the closing balance are explicit,
so the proof is exact: opening + the transactions = closing, to the cent. Files that fail are reported, never trusted.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from .statements import Txn


@dataclass
class Statement:
    account: str = ""
    currency: str = ""
    opening: int | None = None  # signed minor units (money owed counts negative)
    closing: int | None = None
    first_day: str = ""
    last_day: str = ""
    txns: list[Txn] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.issues:
            return "needs_check"
        return "verified" if self.opening is not None and self.closing is not None else "unverified"


def sniff(text: str) -> str | None:
    head = text[:4000]
    if re.search(r"^:20:", head, re.MULTILINE) and (":60F:" in text or ":60M:" in text or ":61:" in text):
        return "mt940"
    if "<BkToCstmrStmt" in text[:20000] or "<Stmt>" in text[:20000]:
        return "camt053"
    return None


def _amount(text: str) -> int | None:
    try:
        return int((Decimal(text.replace(",", ".")) * 100).to_integral_value())
    except InvalidOperation:
        return None


def _balance(value: str) -> tuple[int | None, str, str]:
    """':60F:C200101EUR1234,56' -> (signed minor units, currency, date)."""
    m = re.match(r"([CD])(\d{6})([A-Z]{3})([\d,]+)", value.strip())
    if not m:
        return None, "", ""
    amt = _amount(m.group(4))
    if amt is None:
        return None, "", ""
    d = date(2000 + int(m.group(2)[:2]), int(m.group(2)[2:4]), int(m.group(2)[4:6])).isoformat()
    return (amt if m.group(1) == "C" else -amt), m.group(3), d


def _mt940_fields(text: str) -> list[tuple[str, str]]:
    """Split a MT940 message into (tag, value) pairs; continuation lines belong to the field above them."""
    fields: list[tuple[str, str]] = []
    for raw in text.replace("\r", "").split("\n"):
        m = re.match(r"^:(\d{2}[A-Z]?):(.*)$", raw)
        if m:
            fields.append((m.group(1), m.group(2)))
        elif fields and raw.strip() and not raw.startswith("-}") and not raw.startswith("{"):
            fields[-1] = (fields[-1][0], fields[-1][1] + "\n" + raw)
    return fields


def _mt940_booking_day(value_date: date, month_day: str | None) -> date:
    """The booking date is given as month and day only; the year follows the value date (a booking can fall just before or after New Year)."""
    if not month_day:
        return value_date
    try:
        day = date(value_date.year, int(month_day[:2]), int(month_day[2:]))
    except ValueError:
        return value_date
    if (day - value_date).days > 200:
        return day.replace(year=value_date.year - 1)
    if (value_date - day).days > 200:
        return day.replace(year=value_date.year + 1)
    return day


def _mt940_transaction(cur: Statement, value: str) -> bool:
    """Add the :61: line to the statement. False when it could not be read (the problem is recorded)."""
    m = re.match(r"(\d{6})(\d{4})?(R?[DC])[A-Z]?([\d,]+)N", value.strip())
    if not m:
        cur.issues.append("a transaction line could not be read")
        return False
    amt = _amount(m.group(4))
    if amt is None or amt <= 0:
        cur.issues.append("a transaction amount could not be read")
        return False
    value_date = date(2000 + int(m.group(1)[:2]), int(m.group(1)[2:4]), int(m.group(1)[4:6]))
    day = _mt940_booking_day(value_date, m.group(2))
    income = m.group(3) in ("C", "RD")  # RD = a debit that was reversed: money comes back; RC = a credit reversed: money goes out
    cur.txns.append(Txn(day.isoformat(), amt, "income" if income else "expense", ""))
    return True


def _mt940_balance(cur: Statement, tag: str, value: str) -> None:
    if tag in ("60F", "60M"):
        cur.opening, cur.currency, _ = _balance(value)
        if cur.opening is None:
            cur.issues.append("the opening balance could not be read")
    else:
        cur.closing, _, _ = _balance(value)
        if cur.closing is None:
            cur.issues.append("the closing balance could not be read")


def read_mt940(text: str) -> list[Statement]:
    """One Statement per :20: block."""
    out: list[Statement] = []
    cur: Statement | None = None
    last_txn: int | None = None  # index of the transaction a following :86: line describes
    for tag, value in _mt940_fields(text):
        if tag == "20":
            cur = Statement()
            out.append(cur)
            last_txn = None
        elif cur is None:
            continue
        elif tag == "25":
            cur.account = value.strip().split("/")[0][:40]
        elif tag in ("60F", "60M", "62F", "62M"):
            _mt940_balance(cur, tag, value)
        elif tag == "61":
            last_txn = len(cur.txns) - 1 if _mt940_transaction(cur, value) else last_txn
        elif tag == "86" and last_txn is not None:
            t = cur.txns[last_txn]
            cur.txns[last_txn] = Txn(t.day, t.amount_minor, t.kind, " ".join(value.replace("/", " ").split())[:300])
    for s in out:
        _prove(s)
    return out


def _prove(s: Statement) -> None:
    if s.txns:
        days = sorted(t.day for t in s.txns)
        s.first_day, s.last_day = days[0], days[-1]
    if s.opening is not None and s.closing is not None:
        total = sum(t.amount_minor if t.kind == "income" else -t.amount_minor for t in s.txns)
        if s.opening + total != s.closing:
            s.issues.append(f"opening balance and transactions do not add up to the closing balance (off by {abs(s.opening + total - s.closing) / 100:.2f})")
    elif not s.txns:
        s.issues.append("no transactions were found")


def _local(e: ET.Element) -> str:
    return e.tag.split("}")[-1]


def _child(e: ET.Element | None, *names: str) -> ET.Element | None:
    for n in names:
        if e is None:
            return None
        e = next((c for c in e if _local(c) == n), None)
    return e


def _txt(e: ET.Element, *names: str) -> str:
    c = _child(e, *names)
    return (c.text or "").strip() if c is not None else ""


def _signed(amt_el: ET.Element | None, ind: str) -> int | None:
    amt = _amount(amt_el.text or "") if amt_el is not None else None
    return None if amt is None else (amt if ind == "CRDT" else -amt)


def _camt_balances(stmt: ET.Element, s: Statement) -> None:
    for bal in (e for e in stmt if _local(e) == "Bal"):
        code = _txt(bal, "Tp", "CdOrPrtry", "Cd")
        value = _signed(_child(bal, "Amt"), _txt(bal, "CdtDbtInd"))
        if code in ("OPBD", "PRCD"):
            s.opening = value
        elif code == "CLBD":
            s.closing = value


def _camt_entry(n: ET.Element, s: Statement) -> None:
    amt_el = _child(n, "Amt")
    amt = _amount((amt_el.text or "") if amt_el is not None else "")
    day = _txt(n, "BookgDt", "Dt") or _txt(n, "BookgDt", "DtTm")[:10] or _txt(n, "ValDt", "Dt")
    try:
        date.fromisoformat(day[:10])
    except ValueError:
        s.issues.append("an entry has no readable date")
        return
    if amt is None or amt <= 0:
        s.issues.append("an entry has no readable amount")
        return
    income = _txt(n, "CdtDbtInd") == "CRDT"
    if _txt(n, "RvslInd").lower() == "true":
        income = not income  # a reversal moves the money the other way
    parts = [x.text.strip() for x in n.iter() if _local(x) in ("Nm", "Ustrd", "AddtlNtryInf") and x.text and x.text.strip()]
    s.txns.append(Txn(day[:10], amt, "income" if income else "expense", " ".join(parts)[:300]))


def read_camt(text: str) -> list[Statement]:
    """camt.053 XML. Files with a DTD or entities are refused outright (they are how XML files attack readers)."""
    if re.search(r"<!DOCTYPE|<!ENTITY", text, re.IGNORECASE):
        return [Statement(issues=["the file contains XML entity definitions, which are refused for safety"])]
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return [Statement(issues=["the XML could not be read"])]
    out: list[Statement] = []
    for stmt in (e for e in root.iter() if _local(e) == "Stmt"):
        s = Statement(account=(_txt(stmt, "Acct", "Id", "IBAN") or _txt(stmt, "Acct", "Id", "Othr", "Id"))[:40], currency=_txt(stmt, "Acct", "Ccy"))
        _camt_balances(stmt, s)
        for n in (e for e in stmt if _local(e) == "Ntry"):
            _camt_entry(n, s)
        _prove(s)
        out.append(s)
    return out or [Statement(issues=["no statement was found in the file"])]
