"""Formats that can be recognised exactly, without a model: a bank's own data standards and the ECB's exchange-rate file.

Each recogniser says what a document is from its structure. Whoever needs the content (Finance imports the transactions) reads it with its own code."""

from __future__ import annotations

import re


def bank_standard(text: str) -> str | None:
    """`mt940` (SWIFT) or `camt053` (ISO 20022 XML) when the text is one of those, else None."""
    head = text[:4000]
    if re.search(r"^:20:", head, re.MULTILINE) and (":60F:" in text or ":60M:" in text or ":61:" in text):
        return "mt940"
    if "<BkToCstmrStmt" in text[:20000] or "<Stmt>" in text[:20000]:
        return "camt053"
    return None


def exchange_rate_file(rows: object) -> bool:
    """The European Central Bank's eurofxref CSV: a first row that starts with Date and lists currencies such as USD."""
    return (
        bool(rows)
        and isinstance(rows, list)
        and isinstance(rows[0], list)
        and len(rows[0]) > 3
        and str(rows[0][0]).strip() == "Date"
        and "USD" in [str(c).strip() for c in rows[0]]
    )
