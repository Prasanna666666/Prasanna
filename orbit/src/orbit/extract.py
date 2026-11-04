"""Read finance files with the local model, so no bank, language or layout has to be coded in advance.

For each file the model first says what it is (bank statement, payslip or other) and, for a payslip, reads its figures. For a statement it reads
the text in small chunks and returns each transaction as plain JSON (ISO date, positive amount with a dot decimal, direction, balance). The model
is local (Ollama) and sees only the file's text. Code then only CHECKS the answer, it never interprets a format:
  - dates must be real and amounts positive;
  - when a line carries a balance, the balances must add up from one transaction to the next. If a transaction's direction contradicts the
    arithmetic, the arithmetic wins (it is exact; the model is not).
Every chunk is saved as it is read, so an interrupted import resumes where it stopped and the same line is never stored twice.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from .statements import Txn

CHUNK_LINES = 18  # small enough for the 4096-token window Orbit shares with Aperture
MAX_LINES = 20_000
SIGNAL = re.compile(r"\d")  # a line with no digit at all cannot hold a date or an amount

KIND_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["bank_statement", "payslip", "other"]},
        "period": {"type": "string"},  # YYYY-MM for a payslip
        "gross": {"type": ["number", "null"]}, "net": {"type": ["number", "null"]}, "tax": {"type": ["number", "null"]},
        "pension": {"type": ["number", "null"]}, "holiday_pay": {"type": ["number", "null"]},
    },
    "required": ["kind"],
}
TXN_SCHEMA = {
    "type": "object",
    "properties": {"transactions": {"type": "array", "items": {
        "type": "object",
        "properties": {"date": {"type": "string"}, "description": {"type": "string"}, "amount": {"type": "number"},
                       "direction": {"type": "string", "enum": ["in", "out"]}, "balance": {"type": ["number", "null"]}},
        "required": ["date", "description", "amount", "direction"]}}},
    "required": ["transactions"],
}
KIND_PROMPT = (
    "You read the start of a personal finance document. It may be in Dutch or English. Say what it is: bank_statement (a list of account "
    "transactions), payslip (a salary slip / loonstrook), or other. For a payslip also give the pay period as YYYY-MM and the amounts "
    "(gross = bruto, net = netto paid out, tax = loonheffing, pension = pensioen, holiday_pay = vakantiegeld) as plain numbers with a dot decimal, "
    "or null when absent. Copy numbers exactly. Never invent."
)
TXN_PROMPT = (
    "You read lines of a bank statement. It may be Dutch or English, from any bank. Dutch numbers write 1.234,56 (dot for thousands, comma for "
    "decimals); the day comes before the month. Return every line that is an actual transaction as JSON: date as YYYY-MM-DD, description (who or what, "
    "short), amount as a POSITIVE number with a dot decimal, direction ('in' = money received: bij / credit / deposit; 'out' = money paid: af / debit / "
    "withdrawal), and balance = the account balance shown after that transaction as a number, or null if the line has none. Skip opening balances, "
    "totals, headings, addresses and page footers. Copy numbers exactly. Never invent a transaction."
)


@dataclass
class Result:
    txns: list[Txn]
    consistent: int = 0  # transactions whose running balance matched the arithmetic
    checked: int = 0
    flipped: int = 0  # direction corrected by the arithmetic


def _ask(client, model: str, system: str, text: str, schema: dict) -> dict:
    msg = client.chat(model, [{"role": "system", "content": system}, {"role": "user", "content": text}], schema=schema)
    try:
        data = json.loads(msg.get("content") or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def classify(client, model: str, name: str, text: str) -> dict:
    """What the file is, and for a payslip its figures. Only the first part of the text is sent to the (local) model."""
    data = _ask(client, model, KIND_PROMPT, f"File name: {name}\n\n{text[:3500]}", KIND_SCHEMA)
    return data if data.get("kind") in ("bank_statement", "payslip", "other") else {"kind": "other"}


def _valid(item: dict) -> Txn | None:
    try:
        day = date.fromisoformat(str(item["date"])[:10])
        amount = float(item["amount"])
    except (KeyError, ValueError, TypeError):
        return None
    if not (1990 <= day.year <= 2100) or not (0 < abs(amount) < 1e9) or item.get("direction") not in ("in", "out"):
        return None
    balance = item.get("balance")
    return Txn(day.isoformat(), round(abs(amount) * 100), "income" if item["direction"] == "in" else "expense",
               " ".join(str(item.get("description", "")).split())[:300],
               round(float(balance) * 100) if isinstance(balance, (int, float)) and not isinstance(balance, bool) else None)


def reconcile(txns: list[Txn], previous_balance: int | None = None) -> Result:
    """Make directions agree with the running balance wherever the statement shows one."""
    out: list[Txn] = []
    res = Result(out)
    last = previous_balance
    for t in txns:
        if t.balance_minor is not None and last is not None:
            signed = t.amount_minor if t.kind == "income" else -t.amount_minor
            res.checked += 1
            if last + signed == t.balance_minor:
                res.consistent += 1
            elif last - signed == t.balance_minor:  # the direction was read backwards: the balance says which way the money moved
                t = Txn(t.day, t.amount_minor, "expense" if t.kind == "income" else "income", t.desc, t.balance_minor)
                res.flipped += 1
                res.consistent += 1
        if t.balance_minor is not None:
            last = t.balance_minor
        out.append(t)
    return res


def read_statement(client, model: str, lines: list[str], on_chunk: Callable[[list[Txn], int, int], None] | None = None) -> Result:
    """Transactions from statement text. `on_chunk(new_transactions, done, total)` is called after every chunk so the caller can save and show progress."""
    useful = [" ".join(str(x).split()) for x in lines[:MAX_LINES] if SIGNAL.search(str(x))]
    chunks = [useful[i:i + CHUNK_LINES] for i in range(0, len(useful), CHUNK_LINES)]
    total = Result([])
    last_balance: int | None = None
    for n, chunk in enumerate(chunks, 1):
        data = _ask(client, model, TXN_PROMPT, "\n".join(chunk), TXN_SCHEMA)
        found = [t for t in (_valid(i) for i in data.get("transactions", []) if isinstance(i, dict)) if t is not None]
        part = reconcile(found, last_balance)
        for t in reversed(part.txns):
            if t.balance_minor is not None:
                last_balance = t.balance_minor
                break
        total.txns += part.txns
        total.checked += part.checked
        total.consistent += part.consistent
        total.flipped += part.flipped
        if on_chunk:
            on_chunk(part.txns, n, len(chunks))
    return total
