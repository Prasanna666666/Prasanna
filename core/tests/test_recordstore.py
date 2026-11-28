"""Stage 5: the owner's own Calendar, Contacts and Notes records are editable with exact undo, version checks and a full history; nothing is removed for good."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import KEY

from atlas_core.records import Record
from atlas_core.recordstore import RecordStore, StoreError

pytestmark = pytest.mark.criterion(15)
DOMAINS = frozenset({"calendar", "contacts", "notes"})


def note(rid="n1", text="Renew the passport before March."):
    return Record(rid, "notes", "2026-10-18T00:00:00+00:00", "Passport", {"text": text})


@pytest.fixture
def store(tmp_path):
    s = RecordStore(tmp_path / "edits.db", KEY + "e", DOMAINS)
    yield s
    s.close()


def test_create_update_and_read_back_with_versions(store):
    store.create(note())
    assert store.get("n1").version == 1
    store.update("n1", 1, fields={"text": "Renew the passport before April."})
    got = store.get("n1")
    assert got.version == 2 and got.record.fields["text"].endswith("April.") and [h["op"] for h in store.history("n1")] == ["create", "update"]


def test_two_writers_cannot_silently_overwrite_each_other(store):
    store.create(note())
    store.update("n1", 1, title="Passport (renewal)")
    with pytest.raises(StoreError) as e:
        store.update("n1", 1, title="Passport (other writer)")  # made against the old version
    assert e.value.code == "conflict" and store.get("n1").record.title == "Passport (renewal)"


def test_undo_restores_exactly_and_only_the_latest_change(store):
    store.create(note())
    first = store.update("n1", 1, fields={"text": "A"})
    second = store.update("n1", 2, fields={"text": "B"})
    with pytest.raises(StoreError) as e:
        store.undo(first)  # a later change exists: undoing this one would guess
    assert e.value.code == "conflict"
    store.undo(second)
    assert store.get("n1").record.fields["text"] == "A"
    with pytest.raises(StoreError) as e2:
        store.undo(second)  # already undone
    assert e2.value.code == "nothing_to_undo"


def test_deleting_is_soft_and_undoable_and_the_history_keeps_everything(store):
    store.create(note())
    deleted = store.delete("n1", 1)
    with pytest.raises(StoreError) as e:
        store.get("n1")
    assert e.value.code == "not_found" and store.get("n1", include_deleted=True).deleted is True and store.in_domain("notes") == []
    store.undo(deleted)
    assert store.get("n1").record.fields["text"] == "Renew the passport before March." and len(store.in_domain("notes")) == 1
    assert [h["op"] for h in store.history("n1")] == ["create", "delete", "undo_delete"]


def test_undoing_a_create_hides_the_record_without_losing_its_history(store):
    seq = store.create(note())
    store.undo(seq)
    assert store.in_domain("notes") == [] and store.get("n1", include_deleted=True).deleted is True and store.history("n1")[0]["op"] == "create"


def test_a_domain_this_store_does_not_hold_is_refused_and_a_duplicate_id_is_a_conflict(store):
    with pytest.raises(StoreError) as e:
        store.create(Record("f1", "finance", "2026-10-01", "x", {"amount": "1.00", "currency": "EUR", "kind": "expense"}))
    assert e.value.code == "wrong_domain"
    store.create(note())
    with pytest.raises(StoreError) as e2:
        store.create(note())
    assert e2.value.code == "exists"
    with pytest.raises(StoreError) as e3:
        store.update("n1", 1, fields={"colour": "red"})
    assert e3.value.code == "invalid" and store.get("n1").version == 1  # an invalid change leaves the record untouched


def test_the_store_survives_a_restart_is_encrypted_and_never_removes_anything(tmp_path):
    path = tmp_path / "edits.db"
    s = RecordStore(path, KEY + "e", DOMAINS)
    s.create(note(text="Sentinel passage 4929 about the trip"))
    s.close()
    assert b"Sentinel passage" not in path.read_bytes() and b"SQLite format 3" not in path.read_bytes()[:20]
    again = RecordStore(path, KEY + "e", DOMAINS)
    try:
        assert again.get("n1").record.fields["text"].startswith("Sentinel passage")
        source = Path("src/atlas_core/recordstore.py").read_text().upper()
        assert "DELETE FROM" not in source and "DROP TABLE" not in source  # no statement in the store removes a row
    finally:
        again.close()


def test_a_newer_store_is_refused_before_any_change_to_its_schema_or_bytes(tmp_path):
    """ATLAS-STORE-046: the version is read before any DDL, so an older app cannot alter a newer store while refusing it."""
    import sqlite3

    path = tmp_path / "newer.db"
    raw = sqlite3.connect(path)
    raw.executescript("CREATE TABLE future_only (x); CREATE INDEX future_ix ON future_only(x); INSERT INTO future_only VALUES (1);")
    raw.execute("PRAGMA user_version = 99")
    raw.commit()
    schema = raw.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall()
    raw.close()
    with pytest.raises(StoreError) as refused:
        RecordStore(path, None, frozenset({"finance"}))
    assert str(refused.value) == "newer_store" or getattr(refused.value, "code", "") == "newer_store"
    check = sqlite3.connect(path)
    assert check.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall() == schema
    assert check.execute("PRAGMA user_version").fetchone()[0] == 99
    assert check.execute("SELECT x FROM future_only").fetchall() == [
        (1,)
    ]  # the data is untouched (the journal-mode header flag is the connection's, not this store's schema)
    check.close()


def _event(rid: str, starts: str, ends: str | None = None) -> Record:
    return Record(rid, "calendar", starts[:10], "Dentist", {"starts": starts, **({"ends": ends} if ends else {})})


@pytest.mark.parametrize(
    ("starts", "ends", "code"),
    [
        ("2026-10-20T09:00:00", None, "ambiguous_time"),  # no offset: 09:00 where? never read as UTC
        ("2026-10-20T09:00", "2026-10-20T10:00:00+02:00", "ambiguous_time"),
        ("2026-10-20T09:00:00+02:00", "2026-10-20T10:00:00", "ambiguous_time"),
        ("next tuesday", None, "bad_time"),
        ("2026-10-20T10:00:00+02:00", "2026-10-20T09:00:00+02:00", "bad_time_range"),
    ],
)
def test_an_event_written_without_a_utc_offset_or_ending_before_it_starts_is_refused(store, starts, ends, code):
    """UC-L21: a start or end the owner's records are written with must name one moment. Before this fix a time without an offset was stored and
    then read as UTC, moving a 09:00 Amsterdam appointment to 10:00 or 11:00 local time."""
    with pytest.raises(StoreError) as e:
        store.create(_event("e1", starts, ends))
    assert e.value.code == code and store.in_domain("calendar") == []


def test_an_event_with_an_offset_is_kept_as_written_and_an_edit_to_an_ambiguous_time_is_refused(store):
    store.create(_event("e1", "2026-10-20T09:00:00+02:00", "2026-10-20T10:00:00+02:00"))
    store.create(_event("e2", "2026-10-21T07:00:00Z"))
    assert store.get("e1").record.fields["starts"] == "2026-10-20T09:00:00+02:00"  # the offset the owner wrote is kept, not converted
    with pytest.raises(StoreError) as e:
        store.update("e1", 1, fields={"starts": "2026-10-20T11:00:00"})
    assert e.value.code == "ambiguous_time" and store.get("e1").version == 1 and store.get("e1").record.fields["starts"] == "2026-10-20T09:00:00+02:00"
    store.update("e1", 1, fields={"starts": "2026-10-20T11:00:00+02:00", "ends": "2026-10-20T12:00:00+02:00"})
    assert store.get("e1").version == 2


def test_a_stored_time_without_an_offset_is_skipped_by_the_attention_check_never_read_as_utc():
    """An event stored before UC-L21 without an offset names no moment: the overlap check skips it rather than placing it at that hour in UTC."""
    from atlas_core.operations import _moment

    assert _moment("2026-10-20T09:00:00") is None
    assert _moment("2026-10-20T09:00:00+02:00").utcoffset().total_seconds() == 7200 and _moment("2026-10-20T07:00:00Z").utcoffset().total_seconds() == 0
