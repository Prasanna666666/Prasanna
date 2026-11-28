"""The owner's backup, verify, drill and restore commands: passphrase on stdin only, keys through the platform seam, one short line of codes, and the same refusals as the library."""

from __future__ import annotations

import io
import json
import os
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


class _Items:
    """A Keychain stand-in, by service name. `fail_write_at`: the Nth write raises; `fail_delete`: every delete raises; `lie_on`: a staged
    item whose name ends so reads back wrong after any write. With `path`, the items live in a JSON file and `crash_at` kills the process
    (os._exit) at the Nth write, so no exception handler runs: a real interruption. `add_if_absent` counts as a write when it adds."""

    def __init__(self, existing=None, fail_write_at=None, fail_delete=False, lie_on=None, path=None, crash_at=None):
        self.path = path
        self.store = dict(existing or {}) if path is None or not path.exists() else json.loads(path.read_text())
        self.writes, self.fail_write_at, self.fail_delete, self.lie_on, self.crash_at = 0, fail_write_at, fail_delete, lie_on, crash_at
        self._save()

    def _save(self):
        if self.path is not None:
            self.path.write_text(json.dumps(self.store))

    def read(self, service):
        lie = self.lie_on and self.writes and service.startswith("atlas-staged-") and service.endswith(self.lie_on)
        return "not-what-was-written" if lie else self.store.get(service)

    def write(self, service, value):
        self.writes += 1
        if self.writes == self.crash_at:
            os._exit(9)
        if self.writes == self.fail_write_at:
            raise OSError("keychain write failed")
        self.store[service] = value
        self._save()

    def add_if_absent(self, service, value):
        if service not in self.store:
            self.write(service, value)

    def delete(self, service):
        if self.fail_delete:
            raise OSError("keychain delete failed")
        self.store.pop(service, None)
        self._save()

    def live(self):
        return {k: v for k, v in self.store.items() if not k.startswith("atlas-staged-") and k != "atlas-restore-journal"}


GONE = "/nonexistent/atlas-old-installation"  # the previous installation's folder, no longer on disk: replacing its keys orphans nothing
OLD = {"atlas-task-store": "old-task-key", "atlas-documents-index": "old-docs-key", "atlas-unrelated": "kept", "atlas-installation": GONE}
NEW = {"atlas-task-store": "new-task-key", "atlas-edits-store": "new-edits-key", "atlas-documents-index": "new-docs-key"}
BUNDLE = {"db:tasks.db": "new-task-key", "db:edits.db": "new-edits-key", "documents_index": "new-docs-key"}


def _after(target):
    return {**OLD, **NEW, "atlas-installation": str(target.resolve())}


def test_recovered_keys_are_installed_as_one_unit_and_leave_nothing_staged(tmp_path):
    from atlas_core.maintenance import provision_staged

    items = _Items(OLD)
    provision_staged(items, BUNDLE, tmp_path / "restored")
    assert items.store == _after(tmp_path / "restored")  # no staged item, no journal, and the restored folder now owns the keys


@pytest.mark.parametrize("failure", [{"fail_write_at": 3}, {"lie_on": "edits-store"}, {"fail_write_at": 3, "fail_delete": True}])
def test_a_failure_before_the_commit_point_never_touches_a_live_key_even_when_clean_up_fails(tmp_path, failure):
    """MAC-17: staging writes only inactive items of this transaction, so a staging failure (or a failed read-back, or a clean-up whose
    deletes fail too) leaves every live key exactly as it was; leftover inactive items and the journal are removed by the next recovery."""
    from atlas_core import keyrestore
    from atlas_core.maintenance import provision_staged

    items = _Items(OLD, **failure)
    with pytest.raises(Exception):  # noqa: B017 - an OSError or the read-back error, by case
        provision_staged(items, BUNDLE, tmp_path / "restored")
    assert items.live() == OLD
    items.fail_delete = False
    keyrestore.recover(items)
    assert items.store == OLD


_CRASHING_RUN = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[3])
from test_maintenance import _Items, BUNDLE
from atlas_core.maintenance import provision_staged
items = _Items(path=Path(sys.argv[1]), crash_at=int(sys.argv[2]))
provision_staged(items, BUNDLE, Path(sys.argv[4]))
"""


# writes: 1 journal added, 2-4 staged keys, 5 journal `committing` (the commit point), then per key a live write and a journal update
# (6-7, 8-9, 10-11), 12 the owner record; the journal is then deleted.
@pytest.mark.parametrize(
    ("crash_at", "outcome"),
    [(1, "none"), (3, "discarded"), (5, "discarded"), (6, "completed"), (7, "completed"), (9, "completed"), (12, "completed")],
)
def test_a_process_killed_at_any_key_write_is_finished_or_undone_by_the_next_recovery(tmp_path, crash_at, outcome):
    """MAC-17: the process is killed (os._exit, no handler runs) at every kind of step: adding the journal, staging, writing the commit
    point, promoting a key, recording a promotion and moving ownership. The next start's recovery leaves one consistent set: the old keys
    and owner if the commit point was not written, the complete new set and the new owner if it was."""
    import subprocess
    import sys

    from atlas_core import keyrestore

    store, target = tmp_path / "keychain.json", tmp_path / "restored"
    _Items(OLD, path=store)
    run = [sys.executable, "-c", _CRASHING_RUN, str(store), str(crash_at), str(Path(__file__).parent), str(target)]
    done = subprocess.run(run, check=False, capture_output=True)
    assert done.returncode == 9, done.stderr
    items = _Items(path=store)
    assert keyrestore.recover(items) == outcome
    assert items.store == (OLD if outcome != "completed" else _after(target))


def test_a_staged_key_that_is_missing_and_never_promoted_is_an_error_not_a_finished_restore(tmp_path):
    """MAC-17: recovery tells a verified promotion (recorded in the journal) from a missing staged item, and never takes the second for the
    first: it refuses, leaving that live key untouched and the journal in place for diagnosis."""
    from atlas_core import keyrestore
    from atlas_core.maintenance import provision_staged

    items = _Items(OLD, fail_write_at=6)  # stop at the first promotion, past the commit point
    with pytest.raises(keyrestore.KeyCommitIncomplete):
        provision_staged(items, BUNDLE, tmp_path / "restored")
    staged = [k for k in items.store if k.startswith("atlas-staged-")]
    items.fail_write_at, items.store = None, {k: v for k, v in items.store.items() if k != staged[0]}
    with pytest.raises(keyrestore.KeyRestoreError, match="staged_missing"):
        keyrestore.recover(items)
    assert "atlas-restore-journal" in items.store and items.live()["atlas-installation"] == GONE


def test_restores_are_serialized_account_wide(tmp_path):
    """MAC-17: a restore first finishes or undoes an earlier interrupted one (whichever folder it targeted), and one whose journal another
    restore added first is refused before it writes any key."""
    from atlas_core import keyrestore
    from atlas_core.maintenance import provision_staged

    items = _Items(OLD, fail_write_at=3, fail_delete=True)
    with pytest.raises(OSError):
        provision_staged(items, BUNDLE, tmp_path / "first")
    items.fail_write_at, items.fail_delete = None, False
    provision_staged(items, BUNDLE, tmp_path / "second")  # the first restore's staging is undone, then this one completes
    assert items.store == _after(tmp_path / "second")

    class Racing(_Items):
        def add_if_absent(self, service, value):
            if service == "atlas-restore-journal":
                self.store[service] = '{"tx": "theirs", "state": "staging", "services": [], "target": "/elsewhere", "promoted": []}'
            super().add_if_absent(service, value)

    racing = Racing(OLD)
    with pytest.raises(keyrestore.KeyRestoreError, match="restore_in_progress"):
        provision_staged(racing, BUNDLE, tmp_path / "third")
    assert racing.live() == OLD


@pytest.mark.parametrize("owner", [None, "existing"])
def test_a_restore_never_replaces_keys_another_installation_still_needs(tmp_path, owner):
    """MAC-17: the live keys are account-wide, so a restore into a different folder is refused while the owning folder still holds files,
    and when live keys exist with no recorded owner (they may protect a working folder). No key is written either way."""
    from atlas_core import keyrestore
    from atlas_core.maintenance import provision_staged

    working = tmp_path / "working"
    working.mkdir()
    (working / "tasks.db").write_bytes(b"encrypted under old-task-key")
    keys = {k: v for k, v in OLD.items() if k != "atlas-installation"}
    items = _Items(keys if owner is None else {**keys, "atlas-installation": str(working.resolve())})
    before = dict(items.store)
    with pytest.raises(keyrestore.KeyRestoreError, match="owner_unknown" if owner is None else "another_installation"):
        provision_staged(items, BUNDLE, tmp_path / "restored")
    assert items.store == before and items.writes == 0
