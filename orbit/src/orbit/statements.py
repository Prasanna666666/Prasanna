"""The transaction record and its stable id. Reading statements is done by the local model (see extract.py), not by format rules here."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Txn:
    day: str  # YYYY-MM-DD
    amount_minor: int  # always positive
    kind: str  # expense | income
    desc: str
    balance_minor: int | None = None


def normalise(desc: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", desc.lower()).split())


def reference(txn: Txn, occurrence: int, scope: str = "") -> str:
    """A stable id for a transaction. The same statement read twice, or two statements that overlap, give the same ids.

    With the account known (`scope`), a payment is its account, date, amount and direction: how a bank words the description differs between a PDF, MT940
    and camt.053 of the same month, and must not make one payment count twice. Without the account, the wording and balance are part of the id."""
    if scope:
        key = f"{scope}|{txn.day}|{txn.amount_minor}|{txn.kind}|{occurrence}"
    else:
        key = f"{txn.day}|{txn.amount_minor}|{txn.kind}|{normalise(txn.desc)}|{txn.balance_minor}|{occurrence}"
    return hashlib.sha1(key.encode()).hexdigest()[:24]  # noqa: S324 - an id, not security


def with_references(txns: list[Txn], scope: str = "") -> list[tuple[str, Txn]]:
    seen: dict[tuple, int] = {}
    out = []
    for t in txns:
        k = (t.day, t.amount_minor, t.kind) if scope else (t.day, t.amount_minor, t.kind, normalise(t.desc), t.balance_minor)
        n = seen.get(k, 0)
        seen[k] = n + 1
        out.append((reference(t, n, scope), t))
    return out
