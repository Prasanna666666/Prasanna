"""Typed personal-data records for the Stage 5 domains (Finance, Health, Calendar, Contacts, Notes), as read-only sources behind the same seam as Mail.

A record is stored data with an id, a date, a title and string fields. Each domain renders its records to text deterministically (the exact figures the owner or the source wrote, never a rounded
or model-written form), and a `RecordSource` hands them to the existing encrypted index (`MailIndex`, one store and one key per source type) so every guarantee that already holds for Mail holds here:
nothing is read without a current grant AND the platform permission, passages carry exact spans, a changed record fails closed, a revocation purges the index and what tasks derived from it, and a
restricted domain (Finance, Health; G-021) is only ever opened by a grant for exactly that domain with a `restricted` ceiling.

This module reads no real data: `InMemoryRecords` holds SYNTHETIC fixtures, and the real adapters (Calendar, Contacts, Notes, Photos on macOS; the legacy Finance database through `migration`) are separate,
platform-dependent seams that are not built here.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from .mail import InMemoryMailbox
from .rules import load_rules

_MONEY = re.compile(r"-?\d{1,12}\.\d{2}\Z")
_ID = re.compile(r"[A-Za-z0-9._-]{1,120}\Z")


def _schema() -> dict[str, Any]:
    """The domains, their fields and their typed fields are data in policy-rules.json (`records`), like the source types themselves."""
    return dict(load_rules().raw["records"])


class RecordError(ValueError):
    """A record that does not fit its domain. Carries a code, never the record."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Record:
    record_id: str
    domain: str
    date: str  # ISO 8601 with a zone, or a calendar date
    title: str
    fields: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        schema = _schema().get(self.domain)
        if schema is None:
            raise RecordError("unknown_domain")
        if not _ID.match(self.record_id):
            raise RecordError("bad_id")
        if set(self.fields) - set(schema["fields"]):
            raise RecordError("unknown_field")
        if any(not isinstance(v, str) for v in self.fields.values()):
            raise RecordError("not_text")
        if any(r not in self.fields or not self.fields[r].strip() for r in schema["required"]):
            raise RecordError("missing_field")
        for name in schema.get("money", ()):
            if name in self.fields:
                _check_money(self.fields[name])
        for name in schema.get("numbers", ()):
            if name in self.fields:
                _check_number(self.fields[name])
        for name, allowed in schema.get("kinds", {}).items():
            if name in self.fields and self.fields[name] not in allowed:
                raise RecordError("bad_kind")


def _check_money(text: str) -> Decimal:
    """An amount is written with exactly two decimals and is read back as an exact Decimal: no float is ever involved."""
    if not _MONEY.match(text):
        raise RecordError("bad_amount")
    return Decimal(text)


def _check_number(text: str) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise RecordError("bad_number") from None
    if not value.is_finite():
        raise RecordError("bad_number")
    return value


def render(record: Record) -> str:
    """The text the index stores and the model may later be shown: the record's title, then one `name: value` line per field in the domain's fixed order, exactly as written."""
    lines = [f"record: {record.title}", *(f"{name}: {record.fields[name]}" for name in _schema()[record.domain]["fields"] if name in record.fields)]
    return "\n".join(lines)  # the title leads the body so the passage that holds the figures also matches the words the owner asks with


def as_message(record: Record) -> dict[str, str]:
    """The five stored fields the Mail index takes: the id, a label for where it came from, the date, the title and the rendered text."""
    return {"message_id": record.record_id, "sender": f"{record.domain} record", "date": record.date, "subject": record.title, "body": render(record)}


class InMemoryRecords(InMemoryMailbox):
    """SYNTHETIC records for one domain, behind the Mail seam (`list_page`, `read`). Refuses a record of another domain, so one source can never carry another domain's data."""

    def __init__(self, domain: str, records: Iterable[Record] = ()) -> None:
        self.domain = domain
        self.records: dict[str, Record] = {}
        super().__init__([], order="newest_first")
        for record in records:
            self.put(record)

    def put(self, record: Record) -> None:
        if record.domain != self.domain:
            raise RecordError("wrong_domain")
        self.records[record.record_id] = record
        self.messages[record.record_id] = as_message(record)

    def remove(self, record_id: str) -> None:
        self.records.pop(record_id, None)
        self.messages.pop(record_id, None)
