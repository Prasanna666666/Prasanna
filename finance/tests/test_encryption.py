import pytest

from finance import db
from finance.modules import ALL, notes

sqlcipher = pytest.importorskip("sqlcipher3")


def _make(path, key):
    c = db.connect(path, key=key)
    db.migrate(c, ALL)
    notes.add_note(c, {"body": "PLAINTEXT-MARKER dad's bp 150/90"})
    c.close()


def test_file_is_encrypted_and_roundtrips(tmp_path):
    p = tmp_path / "o.db"
    _make(p, "k1")
    raw = p.read_bytes()
    assert b"PLAINTEXT-MARKER" not in raw and not raw.startswith(b"SQLite format 3")
    c = db.connect(p, key="k1")
    assert notes.search_notes(c, {"query": "PLAINTEXT-MARKER"})[0]["body"].startswith("PLAINTEXT")
    assert (p.stat().st_mode & 0o777) == 0o600


def test_wrong_or_missing_key_refused(tmp_path):
    p = tmp_path / "o.db"
    _make(p, "k1")
    with pytest.raises(db.EncryptionError, match="Wrong"):
        db.connect(p, key="nope")
    with pytest.raises(db.EncryptionError, match="encrypted"):
        db.connect(p)  # no key: refuses instead of showing garbage


def test_require_encryption_never_falls_back_to_plaintext(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_REQUIRE_ENCRYPTION", "1")
    monkeypatch.delenv("ATLAS_DB_KEY", raising=False)
    monkeypatch.delenv("ATLAS_DB_KEY_FILE", raising=False)
    with pytest.raises(db.EncryptionError, match="required"):
        db.connect(tmp_path / "x.db")
    assert not (tmp_path / "x.db").exists()


def test_key_from_file(tmp_path, monkeypatch):
    kf = tmp_path / "key"
    kf.write_text("filekey\n")
    monkeypatch.setenv("ATLAS_DB_KEY_FILE", str(kf))
    _make(tmp_path / "o.db", None)
    monkeypatch.delenv("ATLAS_DB_KEY_FILE")
    c = db.connect(tmp_path / "o.db", key="filekey")
    assert c.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 1
