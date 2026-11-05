"""Which documents are worth the model's time.

The model decides what a document IS (invoice, ticket, booking, medical report, payslip ...). This only decides whether it is worth asking, so that a
mailbox with thousands of newsletters does not cost a model call each. A mail attachment (a PDF, a scan, a spreadsheet) always is; the text of an
email is when it shows an amount of money together with a word of the kinds of documents people keep. Anything the model then calls `other` is
remembered as read, so each is looked at once.
"""

from __future__ import annotations

import re

MIN_TEXT = 40  # an attachment with no readable text (an empty scan, a banner) has nothing to say
ATTACHMENT_KINDS = frozenset({"pdf", "image", "sheet", "doc", "csv"})
AMOUNT = re.compile(r"(?:€|\$|£|₹|\b(?:eur|usd|gbp|inr|rs\.?)\s?)\s?\d[\d.,]*\d|\b\d{1,3}(?:[.,]\d{3})*[.,]\d{2}\b", re.IGNORECASE)
TERMS = frozenset(
    [
        "invoice",
        "invoices",
        "factuur",
        "factuurnummer",
        "rekening",
        "bon",
        "receipt",
        "payment",
        "payments",
        "betaling",
        "betalingen",
        "betaald",
        "paid",
        "ticket",
        "tickets",
        "boarding",
        "booking",
        "bookings",
        "reservation",
        "reservering",
        "boeking",
        "itinerary",
        "hotel",
        "flight",
        "vlucht",
        "policy",
        "polis",
        "premie",
        "verzekering",
        "insurance",
        "payslip",
        "loonstrook",
        "salaris",
        "tax",
        "belasting",
        "aanslag",
        "appointment",
        "afspraak",
        "prescription",
        "recept",
        "uitslag",
        "statement",
        "afschrift",
        "contract",
        "lease",
        "huur",
        "order",
        "bestelling",
        "confirmation",
        "bevestiging",
        "subscription",
        "abonnement",
        "refund",
        "terugbetaling",
    ]
)


def worth_reading(name: str, kind: str, text: str) -> bool:
    """Is this document worth asking the model about?"""
    if kind in ATTACHMENT_KINDS:  # a PDF, scan, sheet or Word file: worth reading when it has text (mail attachments and loose files alike)
        return len(text.strip()) >= MIN_TEXT
    if not AMOUNT.search(text):
        return False
    return any(word in TERMS for word in re.findall(r"[^\W\d_]+", text.lower()))
