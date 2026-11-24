"""Reading the legacy Finance database into Atlas records, without touching it (Stage 5; UC-L18).

The rules, in the order they are applied:

1. **Inventory first.** Size, SHA-256, table row counts, and the number and exact sum (in minor units) of the transactions, before anything is read or written.
2. **The original is never opened.** The file's bytes are copied to a private scratch folder and every read is from that copy; afterwards the original's hash is compared with the inventory and a
   difference is an error. (Opening a database can change it, for example by switching it to WAL mode; a copy cannot.)
3. **Dry run.** The whole mapping is computed and checked (counts, sums, skipped rows with their codes) before a single record is written.
4. **Reconcile.** After the import the sink is read back: the record count, the expense and income sums and an order-independent hash of every record must equal what the original holds, row for row.
5. **No destructive step exists.** Nothing in this module deletes, moves or rewrites an original, and `retire_original` always refuses: retiring the legacy database is a separate, owner-approved action
   with its own acceptance, and rollback of an import is deleting the new records (the original was never changed).

It maps only the legacy `transactions` table (money, dates, categories, notes); other legacy tables are inventoried and reported as not migrated. It reads no key from the environment: an encrypted
legacy copy needs its key passed in.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from kit.db import EncryptionError, connect

from .backup import sha256_file
from .records import Record, RecordError
from .rules import load_rules

MONEY_DOMAIN = next(name for name, schema in load_rules().raw["records"].items() if schema.get("money"))
ID_PREFIX = "legacy-tx-"


class MigrationError(Exception):
    """A migration step was refused. Carries only a code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class Sink(Protocol):
    """Where migrated records go (a record source that accepts writes). `records` is read back to reconcile."""

    @property
    def records(self) -> dict[str, Record]: ...

    def put(self, record: Record) -> None: ...


@dataclass(frozen=True)
class Inventory:
    sha256: str
    size: int
    tables: dict[str, int]
    transactions: int
    expense_minor: int
    income_minor: int


@dataclass
class Plan:
    records: list[Record] = field(default_factory=list)
    skipped: list[tuple[int, str]] = field(default_factory=list)  # (legacy row id, code); never the row's content
    expense_minor: int = 0
    income_minor: int = 0


@dataclass(frozen=True)
class Reconciliation:
    ok: bool
    problems: tuple[str, ...]
    migrated: int
    skipped: int


@contextmanager
def _scratch_copy(source: Path, key: str | None) -> Iterator[sqlite3.Connection]:
    """A connection to a private COPY of the database. The original is only read, as bytes, to make the copy."""
    with tempfile.TemporaryDirectory(prefix="atlmig") as scratch:
        copy = Path(scratch) / "legacy.db"
        shutil.copyfile(source, copy)
        if key:
            try:
                conn = connect(copy, key)
            except EncryptionError:
                raise MigrationError("wrong_key") from None
        else:
            conn = sqlite3.connect(str(copy))
            conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()


def _tables(conn: sqlite3.Connection) -> dict[str, int]:
    try:
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {n: int(conn.execute(f'SELECT count(*) FROM "{n}"').fetchone()[0]) for n in names}
    except sqlite3.DatabaseError:
        raise MigrationError("not_a_database") from None


def inventory(source: Path, key: str | None = None) -> Inventory:
    if not source.is_file():
        raise MigrationError("missing_source")
    with _scratch_copy(source, key) as conn:
        tables = _tables(conn)
        count, expense, income = 0, 0, 0
        if "transactions" in tables:
            for row in conn.execute("SELECT kind, amount_minor FROM transactions"):
                count += 1
                if row["kind"] == "expense":
                    expense += int(row["amount_minor"])
                elif row["kind"] == "income":
                    income += int(row["amount_minor"])
    return Inventory(sha256_file(source), source.stat().st_size, tables, count, expense, income)


def _record(row: sqlite3.Row) -> Record:
    minor = int(row["amount_minor"])
    note = str(row["note"] or "")
    fields = {"amount": f"{Decimal(minor) / 100:.2f}", "currency": "EUR", "kind": str(row["kind"]), "category": str(row["category"] or "other")}
    if note.strip():
        fields["note"] = note
    return Record(f"{ID_PREFIX}{int(row['id'])}", MONEY_DOMAIN, str(row["day"]), f"Transaction {row['day']} {fields['category']}", fields)


def dry_run(source: Path, key: str | None = None) -> Plan:
    """The whole mapping, computed and checked, with nothing written anywhere."""
    plan = Plan()
    with _scratch_copy(source, key) as conn:
        if "transactions" not in _tables(conn):
            raise MigrationError("no_transactions_table")
        for row in conn.execute("SELECT id, day, amount_minor, kind, category, note FROM transactions ORDER BY id"):
            try:
                record = _record(row)
            except (RecordError, ValueError, TypeError):
                plan.skipped.append((int(row["id"]), "unmappable"))
                continue
            plan.records.append(record)
            if record.fields["kind"] == "expense":
                plan.expense_minor += int(row["amount_minor"])
            else:
                plan.income_minor += int(row["amount_minor"])
    return plan


def _digest(records: list[Record]) -> str:
    """Order-independent hash of records (id, date, title and every field)."""
    lines = sorted(f"{r.record_id}|{r.date}|{r.title}|" + "|".join(f"{k}={v}" for k, v in sorted(r.fields.items())) for r in records)
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def reconcile(before: Inventory, plan: Plan, sink: Sink) -> Reconciliation:
    """Read the sink back and compare it with the original's inventory and with the plan, row for row."""
    problems: list[str] = []
    imported = [r for r in sink.records.values() if r.record_id.startswith(ID_PREFIX)]
    if len(imported) + len(plan.skipped) != before.transactions or plan.skipped:
        problems.append("count_mismatch")
    expense = sum(int(Decimal(r.fields["amount"]) * 100) for r in imported if r.fields["kind"] == "expense")
    income = sum(int(Decimal(r.fields["amount"]) * 100) for r in imported if r.fields["kind"] == "income")
    if expense != before.expense_minor or income != before.income_minor:
        problems.append("sum_mismatch")
    if _digest(imported) != _digest(plan.records):
        problems.append("content_mismatch")
    return Reconciliation(not problems, tuple(problems), len(imported), len(plan.skipped))


def migrate(source: Path, sink: Sink, key: str | None = None) -> Reconciliation:
    """Inventory, dry run, write, reconcile. The original must be byte-for-byte unchanged afterwards; the first mismatch raises and leaves the sink for the caller to roll back by deleting what it holds."""
    before = inventory(source, key)
    plan = dry_run(source, key)
    if plan.skipped:
        raise MigrationError("unmappable_rows")  # nothing is written when any row cannot be carried over exactly: the owner decides what to do with them first
    existing = set(sink.records)  # what was there before: a rollback never touches it
    written: list[str] = []
    try:
        for record in plan.records:
            sink.put(record)
            written.append(record.record_id)
        if sha256_file(source) != before.sha256:
            raise MigrationError("original_changed")
        outcome = reconcile(before, plan, sink)
    except BaseException as error:
        _roll_back(sink, [i for i in written if i not in existing])  # no partial import is left behind, whatever went wrong or whenever it was interrupted
        if isinstance(error, MigrationError | KeyboardInterrupt | SystemExit):
            raise
        raise MigrationError("import_rolled_back") from error
    if not outcome.ok:
        _roll_back(sink, [i for i in written if i not in existing])
    return outcome


def _roll_back(sink: Sink, ids: list[str]) -> None:
    remove = getattr(sink, "remove", None)
    for record_id in reversed(ids):
        if remove is not None:
            remove(record_id)


def retire_original(source: Path, *, approval: object = None) -> None:
    """Retiring the legacy database is a separate, owner-approved, separately accepted action. This function never does it."""
    del source, approval
    raise MigrationError("retirement_is_a_separate_approved_action")
