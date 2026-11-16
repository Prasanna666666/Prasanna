"""The person's own words. A change that cannot be taken back lightly (a delete, a move of files, an undo) happens only if what the person typed says so:
text from a document, a mail or a model's own idea never counts."""

from __future__ import annotations

import re

DELETE = re.compile(r"\b(delete|remove|erase|clear|get rid|trash|throw away|verwijder|weggooien)\b")
AFFIRM = re.compile(r"\b(yes|yep|yeah|ok|okay|confirm|confirmed|go ahead|do it|proceed|please do|sure|ja|doe maar|akkoord)\b")
UNDO = re.compile(r"\b(undo|put (it|them) back|restore|revert|bring (it|them) back|terug|herstel)\b")


MAX_CONFIRMING_WORDS = 6  # a yes is short: a long message that happens to contain "ok" is a new question, not a confirmation


def says(pattern: re.Pattern[str], text: str) -> bool:
    return bool(pattern.search(text.lower()))


def confirms(text: str) -> bool:
    """True when the person's own message is a short yes. Only what the person typed is ever passed here: a document, a mail or a tool result never is."""
    return says(AFFIRM, text) and len(text.split()) <= MAX_CONFIRMING_WORDS and not says(DELETE, text)
