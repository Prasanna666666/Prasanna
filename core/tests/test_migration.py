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


def test_a_migrated_finance_database_is_durable_and_listed_newest_first(tmp_path):
    from conftest import KEY

    from atlas_core.recordstore import RecordStore, StoredRecords

    source = legacy(tmp_path / "finance.db")
    store = RecordStore(tmp_path / "finance-records.db", KEY + "f", frozenset({"finance"}))
    result = migrate(source, StoredRecords(store, "finance"))
    assert result.ok and len(store.in_domain("finance")) == 4
    store.close()
    again = RecordStore(tmp_path / "finance-records.db", KEY + "f", frozenset({"finance"}))  # a restart: the records are still there, byte for byte
    try:
        sink = StoredRecords(again, "finance")
        assert sink.records["legacy-tx-1"].fields["amount"] == "412.30"
        assert migrate(source, sink).ok and len(again.in_domain("finance")) == 4  # running the import again changes nothing
        page = sink.list_page(None, 2)
        assert [i.message_id for i in page.items] == ["legacy-tx-3", "legacy-tx-2"] and page.next_cursor == "2"  # newest first, paged
        assert sink.read("legacy-tx-1")["body"].count("amount: 412.30") == 1 and sink.read("missing") is None
    finally:
        again.close()


def test_a_failure_part_way_through_leaves_no_partial_import_and_touches_nothing_that_was_there(tmp_path):
    """ATLAS-MIG-039: whatever fails after some records were written, those records are taken back; records that existed before are untouched."""
    from atlas_core.records import Record

    source = legacy(tmp_path / "finance.db")
    before = Record("mine-1", "finance", "2026-09-01", "pre-existing", {"amount": "1.00", "currency": "EUR", "kind": "expense"})
    for failing_write in (2, 3, 4):

        class Flaky(InMemoryRecords):
            writes = 0

            def put(self, record):
                if record.record_id.startswith("legacy-"):
                    Flaky.writes += 1
                    if Flaky.writes == failing_write:
                        raise OSError("disk full")
                super().put(record)

        sink = Flaky("finance", [before])
        with pytest.raises(MigrationError) as failed:
            migrate(source, sink)
        assert failed.value.code == "import_rolled_back" and set(sink.records) == {"mine-1"} and sink.records["mine-1"] == before

    class Interrupted(InMemoryRecords):
        def put(self, record):
            if record.record_id == "legacy-tx-3":
                raise KeyboardInterrupt
            super().put(record)

    sink = Interrupted("finance", [before])
    with pytest.raises(KeyboardInterrupt):
        migrate(source, sink)
    assert set(sink.records) == {"mine-1"}  # even an interrupt rolls back
    clean = InMemoryRecords("finance", [before])
    assert migrate(source, clean).ok and len(clean.records) == 5  # and a retry afterwards succeeds


def test_a_durable_store_import_that_fails_is_rolled_back_in_the_store(tmp_path):
    from conftest import KEY

    from atlas_core.recordstore import RecordStore, StoredRecords

    source = legacy(tmp_path / "finance.db")
    store = RecordStore(tmp_path / "finance-records.db", KEY + "f", frozenset({"finance"}))
    sink = StoredRecords(store, "finance")
    real_put, calls = sink.put, []

    def failing_put(record):
        calls.append(record.record_id)
        if len(calls) == 3:
            raise OSError("disk full")
        real_put(record)

    sink.put = failing_put
    with pytest.raises(MigrationError):
        migrate(source, sink)
    assert store.in_domain("finance") == []  # nothing visible is left (the history keeps what was written and taken back)
    sink.put = real_put
    assert migrate(source, sink).ok and len(store.in_domain("finance")) == 4
    store.close()
