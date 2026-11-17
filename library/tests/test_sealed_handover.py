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
