"""Exact readers for the bank data standards: MT940 (SWIFT) and camt.053 (ISO 20022 XML). No model, no guessing: these formats have defined fields.

Banks such as ABN AMRO let you download transactions as MT940 or camt.053. Every transaction, the opening balance and the closing balance are explicit,
so the proof is exact: opening + the transactions = closing, to the cent. Files that fail are reported, never trusted.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET  # noqa: S405 - input is checked for DTDs/entities first (see read_camt)
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
    if re.search(r"^:20:", head, re.M) and (":60F:" in text or ":60M:" in text or ":61:" in text):
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


def read_mt940(text: str) -> list[Statement]:
    """One Statement per :20: block."""
    fields: list[tuple[str, str]] = []
    for raw in text.replace("\r", "").split("\n"):
        m = re.match(r"^:(\d{2}[A-Z]?):(.*)$", raw)
        if m:
            fields.append((m.group(1), m.group(2)))
        elif fields and raw.strip() and not raw.startswith("-}") and not raw.startswith("{"):
            fields[-1] = (fields[-1][0], fields[-1][1] + "\n" + raw)
    out: list[Statement] = []
    cur: Statement | None = None
    last_txn_desc = None
    for tag, value in fields:
        if tag == "20":
            cur = Statement()
            out.append(cur)
            last_txn_desc = None
        elif cur is None:
            continue
        elif tag == "25":
            cur.account = value.strip().split("/")[0][:40]
        elif tag in ("60F", "60M"):
            cur.opening, cur.currency, _ = _balance(value)
            if cur.opening is None:
                cur.issues.append("the opening balance could not be read")
        elif tag in ("62F", "62M"):
            cur.closing, _, _ = _balance(value)
            if cur.closing is None:
                cur.issues.append("the closing balance could not be read")
        elif tag == "61":
            m = re.match(r"(\d{6})(\d{4})?(R?[DC])[A-Z]?([\d,]+)N", value.strip())
            if not m:
                cur.issues.append("a transaction line could not be read")
                continue
            amt = _amount(m.group(4))
            if amt is None or amt <= 0:
                cur.issues.append("a transaction amount could not be read")
                continue
            vd = date(2000 + int(m.group(1)[:2]), int(m.group(1)[2:4]), int(m.group(1)[4:6]))
            day = vd
            if m.group(2):  # the booking date is given as month and day; the year follows the value date
                try:
                    day = date(vd.year, int(m.group(2)[:2]), int(m.group(2)[2:]))
                    if (day - vd).days > 200:
                        day = day.replace(year=vd.year - 1)
                    elif (vd - day).days > 200:
                        day = day.replace(year=vd.year + 1)
                except ValueError:
                    day = vd
            mark = m.group(3)
            income = mark in ("C", "RD")  # RD = a debit that was reversed: money comes back; RC = a credit reversed: money goes out
            cur.txns.append(Txn(day.isoformat(), amt, "income" if income else "expense", ""))
            last_txn_desc = len(cur.txns) - 1
        elif tag == "86" and last_txn_desc is not None:
            t = cur.txns[last_txn_desc]
            cur.txns[last_txn_desc] = Txn(t.day, t.amount_minor, t.kind, " ".join(value.replace("/", " ").split())[:300])
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


def read_camt(text: str) -> list[Statement]:
    """camt.053 XML. Files with a DTD or entities are refused outright (they are how XML files attack readers)."""
    if re.search(r"<!DOCTYPE|<!ENTITY", text, re.I):
        return [Statement(issues=["the file contains XML entity definitions, which are refused for safety"])]
    try:
        root = ET.fromstring(text)  # noqa: S314 - DTD/entities were rejected above
    except ET.ParseError:
        return [Statement(issues=["the XML could not be read"])]

    def local(e) -> str:
        return e.tag.split("}")[-1]

    def child(e, *names):
        for n in names:
            found = next((c for c in e if local(c) == n), None)
            if found is None:
                return None
            e = found
        return e

    def txt(e, *names) -> str:
        c = child(e, *names)
        return (c.text or "").strip() if c is not None else ""

    def signed(amt_el, ind: str) -> int | None:
        amt = _amount(amt_el.text or "") if amt_el is not None else None
        return None if amt is None else (amt if ind == "CRDT" else -amt)

    out: list[Statement] = []
    for stmt in (e for e in root.iter() if local(e) == "Stmt"):
        s = Statement(account=(txt(stmt, "Acct", "Id", "IBAN") or txt(stmt, "Acct", "Id", "Othr", "Id"))[:40], currency=txt(stmt, "Acct", "Ccy"))
        for bal in (e for e in stmt if local(e) == "Bal"):
            code = txt(bal, "Tp", "CdOrPrtry", "Cd")
            value = signed(child(bal, "Amt"), txt(bal, "CdtDbtInd"))
            if code in ("OPBD", "PRCD"):
                s.opening = value
            elif code == "CLBD":
                s.closing = value
        for n in (e for e in stmt if local(e) == "Ntry"):
            amt = _amount((child(n, "Amt").text or "") if child(n, "Amt") is not None else "")
            day = txt(n, "BookgDt", "Dt") or txt(n, "BookgDt", "DtTm")[:10] or txt(n, "ValDt", "Dt")
            try:
                date.fromisoformat(day[:10])
            except ValueError:
                s.issues.append("an entry has no readable date")
                continue
            if amt is None or amt <= 0:
                s.issues.append("an entry has no readable amount")
                continue
            income = txt(n, "CdtDbtInd") == "CRDT"
            if txt(n, "RvslInd").lower() == "true":
                income = not income  # a reversal moves the money the other way
            parts = [x.text.strip() for x in n.iter() if local(x) in ("Nm", "Ustrd", "AddtlNtryInf") and x.text and x.text.strip()]
            s.txns.append(Txn(day[:10], amt, "income" if income else "expense", " ".join(parts)[:300]))
        _prove(s)
        out.append(s)
    return out or [Statement(issues=["no statement was found in the file"])]
