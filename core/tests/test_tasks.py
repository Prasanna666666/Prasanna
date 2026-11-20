"""Criteria 3 and 11: durable task state, restart recovery at every boundary, idempotency, cancellation, expiry; the store is new, separate, encrypted and touches nothing else."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest
from conftest import KEY, SENTINEL_QUESTION, T0, World, grant, request

from atlas_core.errors import CoreError
from atlas_core.policy import InMemoryGrants
from atlas_core.service import SimulatedCrash
from atlas_core.tasks import SCHEMA_VERSION, TERMINAL, TRANSITIONS, StoreKeyError, TaskStore, task_store_key

SRC = Path(__file__).resolve().parents[1] / "src" / "atlas_core"
BOUNDARIES = [f"{when}:{step}" for step in ("retrieved", "drafted", "verified") for when in ("before", "mid", "after")] + ["after:attempt", "before:final"]


def _all_ids(w: World) -> list[str]:
    return w.store.ids_in(tuple(TRANSITIONS))


@pytest.mark.criterion(3)
@pytest.mark.parametrize("boundary", BOUNDARIES)
def test_a_crash_at_every_lifecycle_boundary_recovers_to_one_completed_task(tmp_path, boundary):
    w = World(tmp_path, [grant("documents")])
    record, _ = w.service.submit(request())
    w.faults.armed.add(boundary)
    with pytest.raises(SimulatedCrash):
        w.service.run(record["task_id"])
    w.restart()
    state = w.store.record(record["task_id"])["state"]
    final = w.service.run(record["task_id"]) if state == "queued" else w.store.record(record["task_id"])
    assert final["state"] == "completed", boundary
    assert len(_all_ids(w)) == 1 and w.service.answer(record["task_id"])["verification"]["status"] == "verified"
    assert len(w.model.calls) <= 2  # at most the one step that was interrupted is repeated
    seqs = [e["seq"] for e in w.store.events_after(record["task_id"], 0)]
    assert seqs == sorted(set(seqs))


@pytest.mark.criterion(3)
def test_a_crash_before_any_step_with_no_retries_left_ends_as_needs_attention(tmp_path):
    w = World(tmp_path, [grant("documents")])
    record, _ = w.service.submit(request(max_retries=0))
    w.faults.armed.add("mid:retrieved")
    with pytest.raises(SimulatedCrash):
        w.service.run(record["task_id"])
    w.restart()
    final = w.store.record(record["task_id"])
    assert (final["state"], final["terminal_reason"]) == ("failed", "needs_attention")
    assert [e["error"]["code"] for e in w.store.events_after(record["task_id"], 0) if e["type"] == "error"] == ["needs_attention"]


@pytest.mark.criterion(3)
def test_a_task_stuck_before_it_was_queued_is_never_left_pending_after_a_restart(tmp_path):
    w = World(tmp_path, [grant("documents")])
    decision, _ = w.service._d.policy.decide(["documents"], w.clock())
    record, _ = w.store.create(request(), decision, w.clock())  # created, then the process died before anything else
    w.restart()
    assert w.store.record(record["task_id"])["terminal_reason"] == "needs_attention"


@pytest.mark.criterion(3)
def test_the_same_idempotency_key_never_creates_a_second_task_and_a_different_request_is_a_conflict(tmp_path):
    w = World(tmp_path, [grant("documents")])
    first, created = w.service.submit(request(key="idem-key-0001"))
    again, created_again = w.service.submit(request(key="idem-key-0001"))
    assert created and not created_again and first["task_id"] == again["task_id"] and len(_all_ids(w)) == 1
    with pytest.raises(CoreError) as error:
        w.service.submit(request(key="idem-key-0001", objective="a different question"))
    assert error.value.code == "conflict"


@pytest.mark.criterion(3)
def test_cancellation_is_honoured_before_the_run_and_during_it(tmp_path):
    w = World(tmp_path, [grant("documents")])
    queued, _ = w.service.submit(request(key="idem-key-0001"))
    assert w.service.cancel(queued["task_id"])["state"] == "cancelled"
    assert w.service.cancel(queued["task_id"])["state"] == "cancelled"  # safe to repeat
    assert w.service.run(queued["task_id"])["state"] == "cancelled" and w.model.calls == []
    running, _ = w.service.submit(request(key="idem-key-0002"))
    w.model.on_call = lambda: w.service.cancel(running["task_id"])  # the owner cancels while the model is working
    final = w.service.run(running["task_id"])
    assert (final["state"], final["terminal_reason"]) == ("cancelled", "cancelled")
    assert [e["error"]["code"] for e in w.store.events_after(running["task_id"], 0) if e["type"] == "error"] == ["task_cancelled"]


@pytest.mark.criterion(3)
def test_a_task_past_its_deadline_expires_whether_it_is_waiting_or_running(tmp_path):
    w = World(tmp_path, [grant("documents")])
    waiting, _ = w.service.submit(request(key="idem-key-0001", seconds=10))
    w.clock.advance(60)
    assert w.service.expire_due() == [waiting["task_id"]] and w.store.record(waiting["task_id"])["state"] == "expired"
    late, _ = w.service.submit(request(key="idem-key-0002", seconds=10))
    w.clock.advance(60)
    assert w.service.run(late["task_id"])["state"] == "expired" and w.model.calls == []


@pytest.mark.criterion(3)
def test_a_revoked_grant_stops_a_queued_task_at_run_time(tmp_path):
    grants = InMemoryGrants([grant("documents")])
    w = World(tmp_path, [])
    w.grants._grants = grants._grants  # the grant exists at submit time
    record, _ = w.service.submit(request())
    w.grants._grants.clear()  # and is gone when the task runs
    final = w.service.run(record["task_id"])
    assert (final["state"], final["terminal_reason"]) == ("failed", "denied") and w.retriever.calls == []


@pytest.mark.criterion(3)
def test_the_lifecycle_is_strict_every_state_is_known_and_a_finished_task_never_moves(tmp_path):
    assert set(TRANSITIONS) >= TERMINAL and all(not TRANSITIONS[s] for s in TERMINAL)
    assert all(to in TRANSITIONS for targets in TRANSITIONS.values() for to in targets)
    w = World(tmp_path, [grant("documents")])
    record = w.run_new(request())
    assert record["state"] == "completed"
    with pytest.raises(CoreError):
        w.store.transition(record["task_id"], "running", w.clock())


@pytest.mark.criterion(11)
def test_the_task_store_is_a_new_encrypted_file_with_its_own_key_and_nothing_else_is_touched(tmp_path):
    neighbour = tmp_path / "finance.db"
    neighbour.write_bytes(b"an existing database the foundation must never touch")
    before = neighbour.read_bytes()
    folder = tmp_path / "core"
    folder.mkdir()
    w = World(folder, [grant("documents")])
    w.run_new(request())
    w.store.close()
    names = {p.name for p in folder.iterdir()}
    assert names <= {"tasks.db", "tasks.db-wal", "tasks.db-shm"} and neighbour.read_bytes() == before
    raw = b"".join(p.read_bytes() for p in folder.iterdir())
    assert SENTINEL_QUESTION.encode() not in raw and b"SQLite format" not in raw  # the question is not readable from disk
    with pytest.raises(sqlite3.DatabaseError):
        sqlite3.connect(folder / "tasks.db").execute("SELECT * FROM sqlite_master").fetchall()
    with pytest.raises(Exception, match="key"):
        TaskStore(folder / "tasks.db", "a-different-key")


@pytest.mark.criterion(11)
def test_the_store_always_needs_its_own_key_never_the_database_key(monkeypatch, tmp_path):
    for name in ("ATLAS_TASK_KEY", "ATLAS_TASK_KEY_FILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ATLAS_DB_KEY", "the-other-databases-key")
    with pytest.raises(StoreKeyError):
        task_store_key()
    with pytest.raises(StoreKeyError):
        TaskStore(tmp_path / "x.db", "")
    monkeypatch.setenv("ATLAS_TASK_KEY", KEY)
    assert task_store_key() == KEY


@pytest.mark.criterion(11)
def test_a_store_written_by_a_newer_version_is_refused_not_guessed_at(tmp_path):
    store = TaskStore(tmp_path / "tasks.db", KEY)
    store._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    store.close()
    with pytest.raises(CoreError):
        TaskStore(tmp_path / "tasks.db", KEY)


@pytest.mark.criterion(11)
def test_no_source_file_names_an_existing_database_or_writes_outside_its_own_store():
    for path in SRC.glob("*.py"):
        text = path.read_text()
        assert not re.search(r"finance\.db|library\.db|aperture\.db|ATLAS_DB_KEY|database_key", text), path.name
    # the only two stores, each its own new file opened with the key it is given (the document index of WP3.2 is separate from the task store; neither touches an existing database)
    assert sorted(p.name for p in SRC.glob("*.py") if "connect(" in p.read_text() and "sqlite3" not in p.read_text()) == ["documents.py", "tasks.py"]
    assert T0  # the fixtures are synthetic
