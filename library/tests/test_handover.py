"""What the reader hands to Documents holds the whole text of a file. It is readable by its owner only, removed once it is in the encrypted database, removed when it cannot be used, and a stopped reader's half-written file is cleaned up; one ingest never removes another's files."""

import json
import os
import stat
import time

from library import batch, store

SHA = "a" * 64


def _result(sha: str = SHA, text: str = "salary 2.500,00") -> dict:
    return {"schema": 1, "sha256": sha, "kind": "pdf", "name": "payslip.pdf", "text": text}


def test_the_handover_files_can_only_be_read_by_their_owner(tmp_path):
    batch._write(tmp_path, SHA, "payslip.pdf", 10, {"kind": "pdf", "text": "private text"}, "finance")
    result = tmp_path / f"{SHA}.json"
    assert stat.S_IMODE(result.stat().st_mode) == 0o600
    batch.private_text(tmp_path / ".now", "payslip.pdf\nreading")
    assert stat.S_IMODE((tmp_path / ".now").stat().st_mode) == 0o600
    assert json.loads(result.read_text())["text"] == "private text"
    assert not list(tmp_path.glob(".*.tmp")), "the temporary name is gone once the file is complete"


def test_a_stored_result_is_removed_from_the_handover_folder(conn, tmp_path):
    (tmp_path / f"{SHA}.json").write_text(json.dumps(_result()))
    assert store.ingest_dir(conn, tmp_path, on_rejected=lambda *a: None)["new"] == 1
    assert not (tmp_path / f"{SHA}.json").exists()
    assert conn.execute("SELECT count(*) FROM documents").fetchone()[0] == 1


def test_a_result_that_cannot_be_used_is_removed_too_not_left_with_its_text(conn, tmp_path):
    (tmp_path / f"{'b' * 64}.json").write_text('{"name": "broken", "text": "private text"')  # cut off
    (tmp_path / ".done").mkdir()
    (tmp_path / ".done" / ("b" * 64)).touch()  # the reader writes its completion mark before it puts the file in place
    got = store.ingest_dir(conn, tmp_path, on_rejected=lambda *a: None)
    assert got["rejected"] == 1 and not list(tmp_path.glob("*.json"))


def test_a_sha_named_file_without_the_readers_mark_was_not_written_by_the_reader_and_is_kept(conn, tmp_path):
    stranger = tmp_path / f"{'f' * 64}.json"
    stranger.write_text("not a result at all")
    said: list = []

    def collect(*a, sink=said):
        sink.append(a[:2])

    got = store.ingest_dir(conn, tmp_path, on_rejected=collect)
    assert got["rejected"] == 1 and len(said) == 1  # said to the person
    assert stranger.read_text() == "not a result at all"  # and kept: no mark, so it is not ours to remove


def test_only_the_readers_own_hand_over_temporaries_are_cleaned_up_never_other_hidden_tmp_files(conn, tmp_path):
    ours, theirs = tmp_path / f".{'a' * 64}.tmp", tmp_path / ".my-notes.tmp"
    ours.write_text("part of a file's text")
    theirs.write_text("somebody else's file")
    old = time.time() - store.ORPHAN_SECONDS - 60
    for f in (ours, theirs):
        os.utime(f, (old, old))
    store.ingest_dir(conn, tmp_path, on_rejected=lambda *a: None)
    assert not ours.exists()
    assert theirs.read_text() == "somebody else's file"


def test_a_half_written_file_from_a_stopped_reader_is_removed_once_it_is_clearly_abandoned(conn, tmp_path):
    abandoned, active = tmp_path / f".{'c' * 64}.tmp", tmp_path / f".{'d' * 64}.tmp"
    abandoned.write_text("part of a file's text")
    active.write_text("a reader is writing this right now")
    old = time.time() - store.ORPHAN_SECONDS - 60
    os.utime(abandoned, (old, old))
    store.ingest_dir(conn, tmp_path, on_rejected=lambda *a: None)
    assert not abandoned.exists()
    assert active.exists(), "a file a reader may still be writing is never removed"


def test_an_ingest_removes_only_the_files_it_stored(conn, tmp_path):
    (tmp_path / f"{SHA}.json").write_text(json.dumps(_result()))
    store.ingest_dir(conn, tmp_path, on_rejected=lambda *a: None)
    later = tmp_path / f"{'e' * 64}.json"  # written by the reader after that ingest looked at the folder
    later.write_text(json.dumps(_result("e" * 64, "another file")))
    assert later.exists()
    assert store.ingest_dir(conn, tmp_path, on_rejected=lambda *a: None)["new"] == 1 and not later.exists()


def test_two_ingests_of_the_same_folder_store_each_file_once(conn, tmp_path):
    (tmp_path / f"{SHA}.json").write_text(json.dumps(_result()))
    first = store.ingest_dir(conn, tmp_path, on_rejected=lambda *a: None)
    second = store.ingest_dir(conn, tmp_path, on_rejected=lambda *a: None)
    assert (first["new"], second["new"]) == (1, 0) and conn.execute("SELECT count(*) FROM documents").fetchone()[0] == 1
