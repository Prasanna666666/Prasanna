"""Stage 4: backup, restore and key recovery (UC-L15, UC-040). Synthetic data only; the Keychain is a fake. A backup is trusted only after it verifies, a restore never resurrects a grant, and every refusal is a code."""

from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import KEY, SENTINEL_DOC
from test_app import World

from atlas_core.access import FakeOSPermissions
from atlas_core.app import Core, CoreConfig
from atlas_core.backup import BackupError, create_backup, recover_keys, restore_backup, verify_backup
from atlas_core.designation import InMemoryAnchor
from atlas_core.models import ModelStore

PASS = "correct horse battery staple"
DB_KEYS = {"tasks.db": KEY + "t", "designation.db": KEY + "d"}
BUNDLE = {"documents": KEY + "o", "mail": KEY + "m", "model_record": "6b" * 32}
NOW = lambda: datetime(2026, 11, 23, 3, 0, tzinfo=UTC)  # noqa: E731

pytestmark = pytest.mark.criterion(15)


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    yield w
    w.close()


def a_core_with_a_finished_task(world):
    core = world.build()
    core.start()
    world.enable(core, "documents")
    world.wait_indexed(core)
    client = world.client()
    task_id = client.ask(*world.question("en-total"))
    client.result(task_id)
    answer = json.dumps(core.service.answer(task_id), sort_keys=True)
    core.close()
    return task_id, answer


def make_backup(world, tmp_path):
    return create_backup(world.tmp / "core", tmp_path / "backups", db_keys=DB_KEYS, keys=BUNDLE, passphrase=PASS, clock=NOW)


def test_a_backup_verifies_holds_only_what_cannot_be_rebuilt_and_leaks_no_plaintext(world, tmp_path):
    _task_id, _answer = a_core_with_a_finished_task(world)
    folder = make_backup(world, tmp_path)
    assert sorted(p.name for p in folder.iterdir()) == ["clients.json", "designation.db", "keys.enc", "manifest.json", "tasks.db"] or sorted(
        p.name for p in folder.iterdir()
    ) == ["designation.db", "keys.enc", "manifest.json", "tasks.db"]
    manifest = json.loads((folder / "manifest.json").read_text())
    assert {"documents.db", "mail.db", "models"} <= set(manifest["derived_not_backed_up"]) and manifest["grants_restored"] is False
    assert verify_backup(folder).ok and verify_backup(folder, PASS).authenticated
    assert all(os.stat(p).st_mode & 0o077 == 0 for p in folder.iterdir())  # owner-only
    blob = b"".join(p.read_bytes() for p in folder.iterdir())
    assert (
        b"1250.50" not in blob and SENTINEL_DOC.encode() not in blob and PASS.encode() not in blob and KEY.encode() not in blob
    )  # databases are encrypted, keys are wrapped


def test_a_corrupted_truncated_missing_or_tampered_backup_is_refused_with_a_code(world, tmp_path):
    a_core_with_a_finished_task(world)
    folder = make_backup(world, tmp_path)
    cases = {}
    for name in ("flip", "truncate", "missing", "manifest", "keys"):
        copy = tmp_path / f"copy-{name}"
        shutil.copytree(folder, copy)
        cases[name] = copy
    data = bytearray((cases["flip"] / "tasks.db").read_bytes())
    data[len(data) // 2] ^= 0xFF
    (cases["flip"] / "tasks.db").write_bytes(bytes(data))
    (cases["truncate"] / "tasks.db").write_bytes((cases["truncate"] / "tasks.db").read_bytes()[:-100])
    (cases["missing"] / "tasks.db").unlink()
    manifest = json.loads((cases["manifest"] / "manifest.json").read_text())
    manifest["created_at"] = "2020-01-01T00:00:00+00:00"  # an edit that keeps every hash valid but breaks the MAC
    (cases["manifest"] / "manifest.json").write_text(json.dumps(manifest))
    (cases["keys"] / "keys.enc").write_bytes(b"x" * 80)
    assert verify_backup(cases["flip"]).problems == ("hash_mismatch",)
    assert verify_backup(cases["truncate"]).problems == ("size_mismatch",)
    assert verify_backup(cases["missing"]).problems == ("missing_file",)
    assert verify_backup(cases["manifest"]).ok and verify_backup(cases["manifest"], PASS).problems == (
        "manifest_not_authentic",
    )  # corruption checks pass; tampering needs the passphrase
    assert verify_backup(cases["keys"]).problems == ("size_mismatch",) or verify_backup(cases["keys"]).problems == ("hash_mismatch",)
    assert verify_backup(folder, "wrong passphrase entirely").problems == ("bad_passphrase",)
    (folder / "manifest.json").write_text("not json")
    assert verify_backup(folder).problems == ("bad_manifest",)


def test_the_keys_come_back_only_with_the_recovery_passphrase(world, tmp_path):
    a_core_with_a_finished_task(world)
    folder = make_backup(world, tmp_path)
    assert recover_keys(folder, PASS) == {**BUNDLE, "db:tasks.db": DB_KEYS["tasks.db"], "db:designation.db": DB_KEYS["designation.db"]}
    for wrong in ("wrong passphrase entirely", "", PASS + " "):
        with pytest.raises(BackupError) as e:
            recover_keys(folder, wrong)
        assert e.value.code == "bad_passphrase" and str(e.value) == "bad_passphrase"  # the same code every time, no hint


def test_a_weak_passphrase_a_full_disk_or_nothing_to_back_up_is_refused_before_anything_is_written(world, tmp_path, monkeypatch):
    a_core_with_a_finished_task(world)
    with pytest.raises(BackupError) as e:
        create_backup(world.tmp / "core", tmp_path / "b1", db_keys=DB_KEYS, keys=BUNDLE, passphrase="short")
    assert e.value.code == "weak_passphrase" and not (tmp_path / "b1").exists()
    monkeypatch.setattr("atlas_core.backup._free_bytes", lambda folder: 10)
    with pytest.raises(BackupError) as e2:
        make_backup(world, tmp_path)
    assert e2.value.code == "not_enough_space" and not list((tmp_path / "backups").iterdir())
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(BackupError) as e3:
        create_backup(empty, tmp_path / "b3", db_keys=DB_KEYS, keys=BUNDLE, passphrase=PASS)
    assert e3.value.code == "nothing_to_back_up"


def test_a_backup_never_changes_the_live_data_folder_and_never_overwrites_a_backup(world, tmp_path):
    a_core_with_a_finished_task(world)
    live = world.tmp / "core"
    before = {p.name: p.read_bytes() for p in live.iterdir() if p.is_file() and p.suffix in (".db", ".json")}
    folder = make_backup(world, tmp_path)
    assert {p.name: p.read_bytes() for p in live.iterdir() if p.is_file() and p.suffix in (".db", ".json")} == before
    with pytest.raises(BackupError) as e:
        make_backup(world, tmp_path)  # the same second, the same name
    assert e.value.code == "backup_exists" and verify_backup(folder).ok
    assert not [p for p in (tmp_path / "backups").iterdir() if p.name.startswith(".incomplete")]


def restored_core(world, target: Path, bundle: dict[str, str]) -> Core:
    """A replacement Mac: a new data folder, a NEW anchor and OS permission state, the keys recovered from the backup."""
    config = CoreConfig(
        data_dir=target,
        socket_path=world.sock,  # Core A is closed; the replacement Core takes its place
        task_key=bundle["db:tasks.db"],
        designation_key=bundle["db:designation.db"],
        documents_key=bundle["documents"],
        mail_key=bundle["mail"],
        anchor=InMemoryAnchor(),
        os_permissions=FakeOSPermissions(world.clock),
        clients=world.clients,
        manifest=world.manifest,
        model_record_key=b"k" * 32,
        runtime=world.runtime,
        documents=("documents", world.docs),
        open_bootstrap=True,
        clock=world.clock,
    )
    models = target / "models"  # the model folder is not backed up: the replacement Mac re-imports it from the signed manifest
    (models / "primary-1").mkdir(parents=True)
    (models / "primary-1" / "w.safetensors").write_bytes(b"w")
    ModelStore(models, world.manifest, b"k" * 32).import_model("primary-1")
    world.runtime.unload("primary-1")  # a replacement Mac has a fresh runtime; the old one still held the model from Core A
    core = Core(config)
    world.cores.append(core)
    return core


def test_the_restore_drill_a_replacement_mac_gets_its_tasks_back_but_no_grant_and_the_index_is_rebuilt(world, tmp_path):
    task_id, answer = a_core_with_a_finished_task(world)
    folder = make_backup(world, tmp_path)
    provisioned: dict[str, str] = {}
    target = tmp_path / "new-mac" / "core"
    report = restore_backup(folder, PASS, target, provision_keys=provisioned.update)
    assert report.grants_restored is False and set(provisioned) >= {"documents", "mail", "db:tasks.db"}
    assert report.rows["tasks.db"]["tasks"] == 1 and (target / "history" / "designation-history.db").exists() and not (target / "designation.db").exists()
    core = restored_core(world, target, provisioned)
    core.start()
    assert core.designation.lifecycle("documents") != "enabled"  # a restored backup never brings a permission back
    assert core.service.get(task_id)["task_id"] == task_id  # the task history is back
    withheld = json.dumps(core.service.answer(task_id), sort_keys=True)
    assert "1250.50" not in withheld and withheld != answer  # and with no grant its content is not served
    world.os = core.config.os_permissions  # the replacement Mac has its own OS permission state: the owner grants it again too
    world.enable(core, "documents")  # the owner turns the source on again: the one Get Started step
    world.wait_indexed(core)  # the index is rebuilt from the owner's own files
    assert "1250.50" not in json.dumps(
        core.service.answer(task_id), sort_keys=True
    )  # a new grant is a new identity: the old task stays withheld (the Stage 3 rule), nothing is resurrected
    fresh = world.client()
    view = fresh.run_question(*world.question("en-total"))  # a new question is answered from the rebuilt index
    assert "1250.50" in view["text"] and (target / "documents.db").exists()


def test_a_restore_goes_only_into_an_empty_place_and_a_failure_leaves_nothing_behind(world, tmp_path):
    a_core_with_a_finished_task(world)
    folder = make_backup(world, tmp_path)
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("the owner's file")
    with pytest.raises(BackupError) as e:
        restore_backup(folder, PASS, occupied, provision_keys=lambda keys: None)
    assert e.value.code == "target_not_empty" and [p.name for p in occupied.iterdir()] == ["keep.txt"]

    def boom(keys):
        raise OSError("keychain refused")

    fresh = tmp_path / "fresh"
    with pytest.raises(OSError):
        restore_backup(folder, PASS, fresh, provision_keys=boom)
    assert not fresh.exists()  # created by the restore, removed by the restore
    existing_empty = tmp_path / "existing-empty"
    existing_empty.mkdir()
    with pytest.raises(OSError):
        restore_backup(folder, PASS, existing_empty, provision_keys=boom)
    assert existing_empty.exists() and list(existing_empty.iterdir()) == []  # an existing empty folder is left as it was found


def test_a_damaged_backup_is_never_restored_even_partly(world, tmp_path):
    a_core_with_a_finished_task(world)
    folder = make_backup(world, tmp_path)
    data = bytearray((folder / "tasks.db").read_bytes())
    data[100] ^= 0x01
    (folder / "tasks.db").write_bytes(bytes(data))
    target = tmp_path / "t"
    with pytest.raises(BackupError) as e:
        restore_backup(folder, PASS, target, provision_keys=lambda keys: None)
    assert e.value.code == "hash_mismatch" and not target.exists()


def test_a_restore_drill_proves_a_backup_and_only_then_may_the_restricted_domains_be_designated(tmp_path):
    from datetime import timedelta

    from test_domains import DomainWorld

    from atlas_core.backup import DRILL_FILE, drill_passed, run_restore_drill

    (tmp_path / "src").mkdir()
    task_world = World(tmp_path / "src")
    try:
        a_core_with_a_finished_task(task_world)
        folder = make_backup(task_world, tmp_path)
    finally:
        task_world.close()
    (tmp_path / "dom").mkdir()
    world = DomainWorld(tmp_path / "dom")
    try:
        core = world.build()
        core.config.require_restore_drill = True
        core.start()
        core.tick()  # the Core re-reads the gate on every round
        assert (
            "finance" not in core.designation.designable() and "health" not in core.designation.designable() and "notes" in core.designation.designable()
        )  # held back until a drill passes
        assert run_restore_drill(
            folder, "wrong passphrase entirely", tmp_path / "scratch0", core.config.data_dir
        ).code == "bad_passphrase" and not drill_passed(core.config.data_dir)
        assert (
            run_restore_drill(folder, PASS, tmp_path / "scratch1", core.config.data_dir).ok and not (tmp_path / "scratch1").exists()
        )  # the drill cleans up what it made
        core.tick()
        assert {"finance", "health"} <= set(core.designation.designable())
        marker = core.config.data_dir / DRILL_FILE
        assert drill_passed(core.config.data_dir) and not drill_passed(
            core.config.data_dir, lambda: datetime.now(UTC) + timedelta(days=91)
        )  # a drill goes stale
        marker.write_text("not json")
        assert drill_passed(core.config.data_dir) is False
    finally:
        world.close()
