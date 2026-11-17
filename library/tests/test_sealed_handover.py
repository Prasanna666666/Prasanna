"""The reader can seal what it hands over to the app's public key, so the text is not left readable in the shared volume (review item O-16). It is off unless the key is given. A wrong or missing key never throws away the reader's work."""

from pathlib import Path

import pytest

from library import batch, seal, store

DOC = {"schema": 1, "sha256": "a" * 64, "name": "blood-test.pdf", "kind": "pdf", "text": "Glucose 5,2 mmol/L for Alex Example", "area": "health"}


def _write(out: Path, doc: dict, public: str) -> None:
    import os

    os.environ[batch.HANDOVER_PUBLIC_KEY] = public
    try:
        batch._write(out, doc["sha256"], doc["name"], 10, {"kind": doc["kind"], "text": doc["text"]}, doc["area"])
    finally:
        os.environ.pop(batch.HANDOVER_PUBLIC_KEY, None)


@pytest.fixture
def keys(monkeypatch):
    private, public = seal.generate_keypair()
    monkeypatch.delenv("LIBRARY_HANDOVER_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("LIBRARY_HANDOVER_PRIVATE_KEY_FILE", raising=False)
    return private, public


def test_with_the_public_key_the_file_on_the_volume_holds_no_readable_text(tmp_path, keys):
    _, public = keys
    _write(tmp_path, DOC, public)
    sealed = tmp_path / ("a" * 64 + ".sealed")
    assert sealed.is_file() and not (tmp_path / ("a" * 64 + ".json")).exists()
    assert b"Glucose" not in sealed.read_bytes() and b"Alex" not in sealed.read_bytes()
    assert (sealed.stat().st_mode & 0o777) == 0o600
    assert batch._done(tmp_path, "a" * 64)


def test_without_the_public_key_nothing_changes_and_the_old_plain_hand_over_is_used(tmp_path):
    batch._write(tmp_path, "b" * 64, "x.pdf", 1, {"kind": "pdf", "text": "plain"}, "")
    assert (tmp_path / ("b" * 64 + ".json")).is_file() and not list(tmp_path.glob("*.sealed"))


def test_the_app_with_the_private_key_stores_the_document_and_removes_the_file(tmp_path, conn, keys, monkeypatch):
    private, public = keys
    _write(tmp_path, DOC, public)
    monkeypatch.setenv("LIBRARY_HANDOVER_PRIVATE_KEY", private)
    got = store.ingest_dir(conn, tmp_path, on_rejected=lambda *a: None)
    assert got["new"] == 1
    assert conn.execute("SELECT text FROM documents").fetchone()[0] == DOC["text"]
    assert not list(tmp_path.glob("*.sealed"))


def test_the_key_can_come_from_a_file(tmp_path, conn, keys, monkeypatch):
    private, public = keys
    _write(tmp_path, DOC, public)
    key_file = tmp_path / "handover.key"
    key_file.write_text(private)
    monkeypatch.setenv("LIBRARY_HANDOVER_PRIVATE_KEY_FILE", str(key_file))
    assert store.ingest_dir(conn, tmp_path, on_rejected=lambda *a: None)["new"] == 1


def test_a_missing_or_wrong_key_leaves_the_sealed_file_and_its_mark_in_place(tmp_path, conn, keys, monkeypatch):
    _, public = keys
    _write(tmp_path, DOC, public)
    got = store.ingest_dir(conn, tmp_path, on_rejected=lambda *a: None)  # no key at all
    assert got == {"new": 0, "known": 0, "rejected": 0, "replaced": 0, "unopened": 1}
    wrong, _ = seal.generate_keypair()
    monkeypatch.setenv("LIBRARY_HANDOVER_PRIVATE_KEY", wrong)
    got = store.ingest_dir(conn, tmp_path, on_rejected=lambda *a: None)
    assert got["new"] == 0 and got["rejected"] == 0 and got["unopened"] == 1
    assert (tmp_path / ("a" * 64 + ".sealed")).is_file() and (tmp_path / ".done" / ("a" * 64)).exists()


def test_the_compose_file_gives_the_parser_only_the_public_key_and_the_app_only_the_private_one():
    compose = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text(encoding="utf-8")
    parser = compose.split("  parser:")[1].split("  app:")[0]
    app = compose.split("  app:")[1].split("  gateway:")[0]
    assert "LIBRARY_HANDOVER_PUBLIC_KEY" in parser and "PRIVATE" not in parser
    assert "LIBRARY_HANDOVER_PRIVATE_KEY" in app and "LIBRARY_HANDOVER_PUBLIC_KEY" not in app


def test_both_images_carry_the_sealing_library_and_the_parser_image_still_has_no_shared_code():
    d = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()
    app = d.split("AS app")[1].split("AS parser")[0]
    parser = d.split("AS parser")[1].split("AS indexer")[0]
    assert "cryptography" in app and "cryptography" in parser
    assert "COPY kit" not in parser and "./kit" not in parser


# ---- a key that is malformed, empty, missing or wrong must never cost the owner the reader's work ------------------------------
def _bad_keys(private: str) -> list[str]:
    return ["not-hex-at-all", "zz" * 32, private[:-1], private[:10], private + "00", "00" * 31, "00" * 33, "   ", ""]


def test_no_malformed_empty_or_wrong_private_key_ever_deletes_a_sealed_file_or_its_mark(tmp_path, conn, keys, monkeypatch):
    private, public = keys
    wrong, _ = seal.generate_keypair()
    for bad in [*_bad_keys(private), wrong]:
        out = tmp_path / ("k" + str(abs(hash(bad)) % 10**8))
        out.mkdir()
        _write(out, DOC, public)
        sealed = out / ("a" * 64 + ".sealed")
        before = sealed.read_bytes()
        monkeypatch.setenv("LIBRARY_HANDOVER_PRIVATE_KEY", bad)
        rejected: list = []

        def collect(*a, sink=rejected):
            sink.append(a)

        got = store.ingest_dir(conn, out, on_rejected=collect)
        assert got["new"] == 0 and got["rejected"] == 0 and got["unopened"] == 1, (bad, got)
        assert rejected == [], bad  # nothing was reported as a bad file
        assert sealed.read_bytes() == before and (out / ".done" / ("a" * 64)).exists(), bad
        monkeypatch.setenv("LIBRARY_HANDOVER_PRIVATE_KEY", private)  # the key is then fixed: the very same file opens
        fixed = store.ingest_dir(conn, out, on_rejected=lambda *a: None)
        assert fixed["new"] + fixed["known"] == 1 and not sealed.exists(), bad  # the very same file was opened and stored
    assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1  # the same document each time: stored once


def test_a_key_file_that_is_missing_empty_or_garbage_also_keeps_the_sealed_file(tmp_path, conn, keys, monkeypatch):
    private, public = keys
    _write(tmp_path, DOC, public)
    sealed = tmp_path / ("a" * 64 + ".sealed")
    before = sealed.read_bytes()
    for content in (None, "", "garbage\n", private[:20]):
        key_file = tmp_path / "k.key"
        key_file.unlink(missing_ok=True)
        if content is not None:
            key_file.write_text(content)
        monkeypatch.setenv("LIBRARY_HANDOVER_PRIVATE_KEY_FILE", str(key_file))
        got = store.ingest_dir(conn, tmp_path, on_rejected=lambda *a: None)
        assert got["rejected"] == 0 and sealed.read_bytes() == before and (tmp_path / ".done" / ("a" * 64)).exists(), content
    key_file.write_text(private + "\n")  # a trailing newline in the key file is fine
    assert store.ingest_dir(conn, tmp_path, on_rejected=lambda *a: None)["new"] == 1


def test_only_a_file_too_short_to_be_sealed_is_rejected_whatever_the_key(tmp_path, conn, keys, monkeypatch):
    private, _ = keys
    (tmp_path / ("c" * 64 + ".sealed")).write_bytes(b"short")
    (tmp_path / ".done").mkdir()
    (tmp_path / ".done" / ("c" * 64)).touch()
    monkeypatch.setenv("LIBRARY_HANDOVER_PRIVATE_KEY", private)
    got = store.ingest_dir(conn, tmp_path, on_rejected=lambda *a: None)
    assert got["rejected"] == 1 and not (tmp_path / ("c" * 64 + ".sealed")).exists()  # a fault of the file: it is read again next round


def test_a_malformed_public_key_stops_the_reader_before_it_writes_or_marks_anything(tmp_path):
    for bad in ["not-hex", "zz" * 32, "00" * 31, "00" * 33]:
        out = tmp_path / ("w" + str(abs(hash(bad)) % 10**8))
        out.mkdir()
        with pytest.raises(seal.SealKeyError):
            _write(out, DOC, bad)
        assert list(out.iterdir()) == [], bad  # no half-written file, no completion mark: the file is read again once the key is fixed


def test_a_forged_low_order_ephemeral_key_is_a_fault_of_the_file_not_of_the_key(tmp_path, conn, keys, monkeypatch):
    private, _ = keys
    (tmp_path / ("d" * 64 + ".sealed")).write_bytes(bytes(32) + bytes(12) + bytes(40))  # an all-zero ephemeral public key
    (tmp_path / ".done").mkdir()
    (tmp_path / ".done" / ("d" * 64)).touch()
    with pytest.raises(seal.NotSealedError):
        seal.open_sealed((tmp_path / ("d" * 64 + ".sealed")).read_bytes(), private)
    monkeypatch.setenv("LIBRARY_HANDOVER_PRIVATE_KEY", private)
    got = store.ingest_dir(conn, tmp_path, on_rejected=lambda *a: None)
    assert got["rejected"] == 1 and not (tmp_path / ("d" * 64 + ".sealed")).exists()  # rejected on purpose: the mark goes too, so the original is read again


def test_the_read_summary_tells_the_person_when_sealed_files_could_not_be_opened(tmp_path, conn, monkeypatch):
    from types import SimpleNamespace

    from library import appstate, reading

    monkeypatch.setattr(appstate, "parsed_dir", lambda: tmp_path)
    state = SimpleNamespace(scan={}, control="")
    reading._summarise(state, conn, {"new": 0, "replaced": 0, "unopened": 2})
    assert "2 files read but not opened" in state.scan["summary"] and "nothing was lost" in state.scan["summary"]
    reading._summarise(state, conn, {"new": 0, "replaced": 0})
    assert "not opened" not in state.scan["summary"]
