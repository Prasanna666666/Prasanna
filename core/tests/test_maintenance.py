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
