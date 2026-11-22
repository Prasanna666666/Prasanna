"""Stage 5, UC-L18: importing the legacy Finance database. The original is never opened or changed, nothing is written before a clean dry run, the import reconciles row for row, and nothing here can delete."""

from __future__ import annotations

import re
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from kit.db import connect

from atlas_core import migration
from atlas_core.migration import MigrationError, dry_run, inventory, migrate, reconcile, retire_original
from atlas_core.records import InMemoryRecords, Record

pytestmark = pytest.mark.criterion(15)
SCHEMA = (
    "CREATE TABLE transactions (id INTEGER PRIMARY KEY, day TEXT NOT NULL, amount_minor INTEGER NOT NULL, kind TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'other', note TEXT NOT NULL DEFAULT '');"
    "CREATE TABLE budgets (category TEXT PRIMARY KEY, monthly_minor INTEGER NOT NULL);"
)
ROWS = [
    (1, "2026-10-15", 41230, "expense", "rent", "October"),
    (2, "2026-10-16", 10, "expense", "tea", ""),
    (3, "2026-10-17", 20, "expense", "tea", ""),
    (4, "2026-10-01", 300000, "income", "salary", "Employer"),
]


def legacy(path: Path, rows=ROWS, key: str | None = None) -> Path:
    if key:
        conn = connect(path, key)
        conn.executescript(SCHEMA)
    else:
        conn = sqlite3.connect(str(path))
        conn.executescript(SCHEMA)
    conn.executemany("INSERT INTO transactions VALUES (?,?,?,?,?,?)", rows)
    conn.execute("INSERT INTO budgets VALUES ('tea', 500)")
    conn.commit()
    conn.close()
    for sidecar in (path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
        sidecar.unlink(missing_ok=True)
    return path


def test_the_inventory_counts_and_sums_before_anything_is_read_or_written(tmp_path):
    inv = inventory(legacy(tmp_path / "finance.db"))
    assert inv.tables == {"budgets": 1, "transactions": 4} and inv.transactions == 4 and (inv.expense_minor, inv.income_minor) == (41260, 300000)
    assert len(inv.sha256) == 64 and inv.size > 0


def test_the_import_reconciles_row_for_row_and_the_original_is_byte_for_byte_unchanged(tmp_path):
    source = legacy(tmp_path / "finance.db")
    before_bytes, before_mtime = source.read_bytes(), source.stat().st_mtime_ns
    sink = InMemoryRecords("finance")
    result = migrate(source, sink)
    assert result.ok and result.problems == () and (result.migrated, result.skipped) == (4, 0)
    assert source.read_bytes() == before_bytes and source.stat().st_mtime_ns == before_mtime  # the original was never opened for writing
    assert not list(tmp_path.glob("*-wal")) and not list(tmp_path.glob("*-shm"))
    rent = sink.records["legacy-tx-1"]
    assert (
        rent.fields["amount"] == "412.30"
        and rent.fields["kind"] == "expense"
        and rent.fields["note"] == "October"
        and Decimal(rent.fields["amount"]) * 100 == 41230
    )


def test_a_dry_run_writes_nothing_and_reports_what_would_happen(tmp_path):
    plan = dry_run(legacy(tmp_path / "finance.db"))
    assert len(plan.records) == 4 and plan.skipped == [] and (plan.expense_minor, plan.income_minor) == (41260, 300000)


def test_a_row_that_cannot_be_carried_over_exactly_stops_the_import_before_anything_is_written(tmp_path):
    source = legacy(tmp_path / "finance.db", [*ROWS, (5, "2026-10-18", 500, "transfer", "x", "")])  # a kind Atlas does not carry
    sink = InMemoryRecords("finance")
    plan = dry_run(source)
    assert plan.skipped == [(5, "unmappable")] and len(plan.records) == 4
    with pytest.raises(MigrationError) as e:
        migrate(source, sink)
    assert e.value.code == "unmappable_rows" and sink.records == {}  # and the report carries the row's id, never its content


def test_reconciliation_catches_a_changed_a_missing_and_an_extra_record(tmp_path):
    source = legacy(tmp_path / "finance.db")
    inv, plan = inventory(source), dry_run(source)
    sink = InMemoryRecords("finance")
    migrate(source, sink)
    assert reconcile(inv, plan, sink).ok
    sink.records["legacy-tx-1"] = Record(
        "legacy-tx-1",
        "finance",
        "2026-10-15",
        "Transaction 2026-10-15 rent",
        {"amount": "412.31", "currency": "EUR", "kind": "expense", "category": "rent", "note": "October"},
    )
    assert reconcile(inv, plan, sink).problems == ("sum_mismatch", "content_mismatch")
    sink.remove("legacy-tx-2")
    assert "count_mismatch" in reconcile(inv, plan, sink).problems


def test_an_encrypted_legacy_copy_needs_its_key_and_a_wrong_key_is_a_code(tmp_path):
    source = legacy(tmp_path / "finance.db", key="ab" * 32)
    assert inventory(source, "ab" * 32).transactions == 4
    with pytest.raises(MigrationError) as e:
        inventory(source, "cd" * 32)
    assert e.value.code == "wrong_key"
    with pytest.raises(MigrationError) as e2:
        inventory(tmp_path / "missing.db")
    assert e2.value.code == "missing_source"
    (tmp_path / "junk.db").write_bytes(b"not a database at all" * 50)
    with pytest.raises(MigrationError) as e3:
        inventory(tmp_path / "junk.db")
    assert e3.value.code == "not_a_database"


def test_retiring_the_original_is_never_done_here_and_the_module_has_no_way_to_delete():
    with pytest.raises(MigrationError) as e:
        retire_original(Path("/nonexistent"), approval="yes please")
    assert e.value.code == "retirement_is_a_separate_approved_action"
    source = Path(migration.__file__).read_text()
    code = re.sub(r'""".*?"""', "", source, flags=re.S)
    assert not re.search(
        r"\.unlink\(|os\.remove|shutil\.rmtree|\.rename\(|os\.replace|shutil\.move|\.write_bytes\(|\.write_text\(", code
    )  # it can copy and read; it cannot change or remove an original
