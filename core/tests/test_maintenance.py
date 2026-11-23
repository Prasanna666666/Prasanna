"""The owner's backup, verify, drill and restore commands: passphrase on stdin only, keys through the platform seam, one short line of codes, and the same refusals as the library."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from conftest import KEY
from test_operations_api import NOTE, OpsWorld

from atlas_core.maintenance import BUNDLE_ITEMS, KEY_ITEMS, run

pytestmark = pytest.mark.criterion(15)
PASS = "correct horse battery staple"
ITEM_KEYS = {
    "task-store": KEY + "t",
    "designation-store": KEY + "d",
    "edits-store": KEY + "e",
    "finance-records": KEY + "f",
    "health-records": KEY + "h",
    "documents-index": KEY + "o",
    "mail-index": KEY + "m",
    "model-record": "6b" * 32,
}


def cli(argv, passphrase=PASS):
    out, written = io.StringIO(), {}
    code = run(argv, stdin=io.StringIO(passphrase + "\n"), out=out, read_key=ITEM_KEYS.__getitem__, write_keys=written.update)
    return code, out.getvalue(), written


@pytest.fixture
def made(tmp_path):
    (tmp_path / "a").mkdir()
    world = OpsWorld(tmp_path / "a")
    core = world.build()
    core.start()
    world.client().act("notes.create", NOTE)
    from atlas_core.records import Record
    from atlas_core.recordstore import RecordStore

    for domain, key, fields in (
        ("finance", "f", {"amount": "9.99", "currency": "EUR", "kind": "expense"}),
        ("health", "h", {"measure": "weight", "value": "70", "unit": "kg"}),
    ):
        store = RecordStore(world.tmp / "core" / f"{domain}-records.db", KEY + key, frozenset({domain}))
        store.create(Record(f"{domain}-1", domain, "2026-10-01", "synthetic", fields))
        store.close()
    code, text, _ = cli(["backup", str(world.tmp / "core"), str(tmp_path / "backups")])
    world.close()
    assert code == 0 and text.startswith("backup: ok atlas-backup-")
    return tmp_path, next((tmp_path / "backups").iterdir())


def test_backup_verify_drill_and_restore_through_the_commands(made):
    tmp, folder = made
    assert cli(["verify", str(folder)], passphrase="")[1].startswith("verify: ok") and "authenticated" in cli(["verify", str(folder)])[1]
    data = tmp / "live"
    data.mkdir()
    code, text, _ = cli(["drill", str(folder), str(data)])
    assert (code, text) == (0, "drill: ok\n") and (data / "restore-drill.json").exists()
    code, text, written = cli(["restore", str(folder), str(tmp / "new")])
    assert code == 0 and "grants not restored" in text and (tmp / "new" / "edits.db").exists()
    from atlas_core.recordstore import RecordStore

    for domain, key in (("finance", "f"), ("health", "h")):  # the owner's Finance and Health records are backed up and come back under their own keys
        restored = RecordStore(tmp / "new" / f"{domain}-records.db", KEY + key, frozenset({domain}))
        assert [s.record.record_id for s in restored.in_domain(domain)] == [f"{domain}-1"]
        restored.close()
        assert written[f"db:{domain}-records.db"] == KEY + key
    assert (
        written["db:edits.db"] == KEY + "e" and written["documents_index"] == KEY + "o" and set(KEY_ITEMS) | set(BUNDLE_ITEMS) and len(written) >= 5
    )  # the recovered keys go back through the seam


def test_a_wrong_passphrase_a_damaged_backup_and_a_bad_command_are_refused_with_one_code_and_no_secret(made):
    tmp, folder = made
    code, text, written = cli(["restore", str(folder), str(tmp / "x")], passphrase="not the passphrase at all")
    assert (code, text) == (1, "restore: refused bad_passphrase\n") and written == {} and not (tmp / "x").exists()
    (folder / "tasks.db").write_bytes((folder / "tasks.db").read_bytes()[:-50])
    assert cli(["verify", str(folder)], passphrase="")[1] == "verify: refused size_mismatch\n"
    assert cli([])[0] == 64 and cli(["explode", "x"])[0] == 64
    assert cli(["backup", str(tmp / "nope"), str(tmp / "b")])[1].startswith("backup: refused")
    for secret in (PASS, KEY):
        assert secret not in text


def test_the_commands_take_the_passphrase_only_from_standard_input():
    source = (Path(__file__).resolve().parents[1] / "src" / "atlas_core" / "maintenance.py").read_text()
    assert (
        "sys.argv[1:]" in source and "os.environ" not in source and "getenv" not in source and "readline()" in source
    )  # a verb and paths on the command line; the passphrase from standard input only
    assert json.dumps(ITEM_KEYS)  # the fixture's keys are synthetic


def test_the_legacy_finance_database_is_imported_through_the_command_and_the_original_is_untouched(tmp_path):
    import sqlite3

    from atlas_core.recordstore import RecordStore, StoredRecords

    legacy = tmp_path / "finance.db"
    conn = sqlite3.connect(str(legacy))
    conn.executescript("CREATE TABLE transactions (id INTEGER PRIMARY KEY, day TEXT, amount_minor INTEGER, kind TEXT, category TEXT, note TEXT);")
    conn.execute("INSERT INTO transactions VALUES (1, '2026-10-15', 41230, 'expense', 'rent', 'October')")
    conn.commit()
    conn.close()
    before = legacy.read_bytes()
    stores = []

    def open_sink(data_dir):
        data_dir.mkdir(parents=True, exist_ok=True)
        store = RecordStore(data_dir / "finance-records.db", KEY + "f", frozenset({"finance"}))
        stores.append(store)
        return StoredRecords(store, "finance"), lambda: None

    out = io.StringIO()
    code = run(
        ["import-finance", str(legacy), str(tmp_path / "core")],
        stdin=io.StringIO("\n"),
        out=out,
        read_key=ITEM_KEYS.__getitem__,
        write_keys=lambda b: None,
        open_sink=open_sink,
    )
    assert (code, out.getvalue()) == (0, "import-finance: ok 1 records\n") and legacy.read_bytes() == before
    assert stores[0].get("legacy-tx-1").record.fields["amount"] == "412.30"
    stores[0].close()
    out2 = io.StringIO()
    assert (
        run(
            ["import-finance", str(tmp_path / "missing.db"), str(tmp_path / "core")],
            stdin=io.StringIO("\n"),
            out=out2,
            read_key=ITEM_KEYS.__getitem__,
            write_keys=lambda b: None,
            open_sink=open_sink,
        )
        == 1
    )
    assert out2.getvalue() == "import-finance: refused missing_source\n"
