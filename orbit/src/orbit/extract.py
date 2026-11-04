"""What kind of finance file is this, and what are its key facts? The local model reads; code verifies.

The model says what a file is (bank statement, payslip, invoice, receipt, tax, insurance, contract, other) and quotes its key amounts EXACTLY AS
PRINTED. Code then accepts an amount only if that exact text appears in the document, and reads the number from the printed text itself. So an amount
the model made up, or mis-copied, is dropped instead of stored. Bank statements are not read here: see tables.py (layout by the model, figures by code).
"""

from __future__ import annotations

import json
import re

from .tables import money_from_printed

KINDS = ("bank_statement", "payslip", "invoice", "receipt", "tax", "insurance", "contract", "other")
MONEY_FIELDS = ("total", "vat", "gross", "net", "tax", "pension", "holiday_pay")
_STR = {"type": ["string", "null"]}
KIND_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": list(KINDS)},
        "title": {"type": "string"}, "summary": {"type": "string"},
        "party": {"type": "string"},  # who it is from / to: the shop, supplier, employer, insurer, tax office ...
        "date": {"type": "string"}, "due_date": {"type": "string"}, "reference": {"type": "string"},  # YYYY-MM-DD; invoice / policy / case number
        "currency": {"type": "string"},
        "period": {"type": "string"},  # YYYY-MM for a payslip
        **{f: _STR for f in MONEY_FIELDS},  # each amount exactly as printed in the document, e.g. "3.500,00"
    },
    "required": ["kind"],
}
KIND_PROMPT = (
    "You read the start of a personal finance document. It may be in Dutch or English. Say what it is: bank_statement (a list of account "
    "transactions), payslip (salary slip / loonstrook), invoice (factuur), receipt (bon / kassabon), tax (belasting: aanslag, aangifte), insurance "
    "(verzekering: polis, premie), contract (agreement, lease, loan), or other. Then give: title (a few words), summary (one short sentence), party "
    "(who it is from or to: shop, supplier, employer, insurer, tax office), date and due_date as YYYY-MM-DD, reference (invoice / policy / case "
    "number), currency (EUR, INR ...). Give each amount EXACTLY AS PRINTED in the document, as text, character for character (for example \"3.500,00\"): "
    "total and vat for invoices and receipts; for a payslip also period as YYYY-MM and gross = bruto, net = netto paid out, tax = loonheffing, "
    "pension = pensioen, holiday_pay = vakantiegeld. Leave out or use null what is not there. Never invent or recalculate."
)


def _ask(client, model: str, system: str, text: str, schema: dict) -> dict:
    msg = client.chat(model, [{"role": "system", "content": system}, {"role": "user", "content": text}], schema=schema)
    try:
        data = json.loads(msg.get("content") or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def verify_amounts(info: dict, text: str) -> dict:
    """Keep an amount only if it appears in the document exactly as quoted; replace the quote by the number read from it."""
    haystack = _squash(text)
    checked = dict(info)
    dropped = []
    for f in MONEY_FIELDS:
        quoted = info.get(f)
        if quoted in (None, ""):
            checked[f] = None
            continue
        minor = money_from_printed(str(quoted)) if _squash(str(quoted)) in haystack else None
        checked[f] = minor / 100 if minor is not None else None
        if minor is None:
            dropped.append(f)
    checked["unverified_fields"] = dropped
    return checked


def classify(client, model: str, name: str, text: str) -> dict:
    """What the file is and its key facts. Only the first part of the text goes to the (local) model; every amount is verified against the text."""
    data = _ask(client, model, KIND_PROMPT, f"File name: {name}\n\n{text[:3500]}", KIND_SCHEMA)
    if data.get("kind") not in KINDS:
        return {"kind": "other"}
    return verify_amounts(data, text[:3500])
