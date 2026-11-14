"""One rule for what may be shown. A document's facts are shown only when they are understood completely enough to help: the kind is known and the fields that kind needs
are there (an invoice needs who it is from and how much; a ticket needs the date and the place). A reading that only got a kind and a title (`partial`) is not shown as if it
meant something. What is held back is never lost or hidden: it is counted, listed with the reason, and tried again."""

from __future__ import annotations

from typing import Any

REQUIRED: dict[str, tuple[str, ...]] = {
    "invoice": ("party", "total"),
    "receipt": ("party", "total"),
    "payslip": ("period",),
    "annual_statement": ("period",),
    "ticket": ("start_date", "place"),
    "booking": ("start_date", "place"),
    "insurance": ("party",),
    "contract": ("party",),
    "tax": ("party",),
    "medical": ("date",),
}
FIELD = {"party": "who it is from", "total": "the amount", "start_date": "the date", "place": "the place", "date": "the date", "period": "the period"}


def check(facts: dict[str, Any]) -> tuple[bool, list[str]]:
    """(understood, what is missing). `other` and bank statements need nothing more than their kind."""
    if facts.get("partial"):
        return False, ["the details (only the kind was understood)"]
    absent = set(facts.get("absent", []))  # looked for in everything that belongs with the document: it does not state it. That is understood too.
    missing = [FIELD[k] for k in REQUIRED.get(str(facts.get("kind", "other")), ()) if facts.get(k) in (None, "", []) and FIELD[k] not in absent]
    return not missing, missing
