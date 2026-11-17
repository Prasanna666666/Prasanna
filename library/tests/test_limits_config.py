"""Every limit on what is kept comes from limits.json: changing the file changes the behaviour, says what was cut, and finds the documents cut under the old numbers."""

import json

import pytest

from library import limits, sniff, store


@pytest.fixture
def configure(tmp_path, monkeypatch):
    def write(**numbers):
        (tmp_path / "limits.json").write_text(json.dumps(numbers))
        monkeypatch.setenv("LIBRARY_LIMITS", str(tmp_path / "limits.json"))

    return write


def _document(sha="a", **over):
    return {"schema": 1, "sha256": sha * 64, "kind": "pdf", "name": "ok.pdf", "text": "t", **over}


def test_every_limit_is_in_the_fingerprint(configure):
    before = limits.version()
    for name in limits.DEFAULTS:
        configure(**{name: limits.DEFAULTS[name] + 1})
        assert limits.version() != before, name


def test_the_name_text_and_source_limits_come_from_the_file_and_each_cut_is_recorded(configure):
    configure(max_name_chars=10, max_text_chars=20, max_source_chars=15)
    fixed = store._repaired(_document(name="n" * 30, text="x" * 50, source="s" * 40), "a" * 64)
    assert (len(fixed["name"]), len(fixed["text"]), len(fixed["source"])) == (10, 20, 15)
    assert sorted(fixed["meta"]["limits_hit"]) == ["name", "source", "text"]
    assert fixed["meta"]["limits_version"] == limits.version()


def test_nothing_is_cut_and_nothing_recorded_when_everything_fits(configure):
    configure(max_name_chars=100, max_text_chars=100, max_source_chars=100)
    fixed = store._repaired(_document(name="short.pdf", text="x" * 50, source="where"), "a" * 64)
    assert "limits_hit" not in (fixed.get("meta") or {}) and fixed["text"] == "x" * 50


def test_the_attachment_count_limit_comes_from_the_file(configure):
    mail = {"kind": "email", "meta": {"attachments": 7}}
    configure(max_promised_attachments=5)
    assert store._promised(mail) == 0
    configure(max_promised_attachments=50)
    assert store._promised(mail) == 7


def test_a_result_file_over_the_json_limit_is_not_read_into_memory(configure, conn, tmp_path):
    folder = tmp_path / "results"
    folder.mkdir()
    (folder / f"{'a' * 64}.json").write_text(json.dumps(_document()))
    configure(max_json_bytes=10)
    said = []
    assert store.ingest_dir(conn, folder, on_rejected=lambda *a: said.append(a))["new"] == 0
    assert said, "the refusal is reported, not silent"
    (folder / f"{'a' * 64}.json").write_text(json.dumps(_document()))  # the reader writes the result again at its next round
    configure(max_json_bytes=10_000)
    assert store.ingest_dir(conn, folder, on_rejected=lambda *a: None)["new"] == 1


def test_the_json_detection_size_comes_from_the_file(configure, tmp_path):
    path = tmp_path / "data.bin"
    path.write_text(json.dumps({"a": list(range(100))}))
    configure(json_sniff_bytes=10)
    assert sniff.kind_of(path) != "json"
    configure(json_sniff_bytes=100_000)
    assert sniff.kind_of(path) == "json"


def test_documents_cut_under_old_limits_are_read_again_when_the_limits_change(configure, conn, tmp_path):
    folder = tmp_path / "results"
    folder.mkdir()
    configure(max_name_chars=10)
    (folder / f"{'a' * 64}.json").write_text(json.dumps(_document(name="n" * 30)))
    store.ingest_dir(conn, folder, on_rejected=lambda *a: None)
    assert store.forget_stale_reads(conn, folder) == 0  # the limits have not changed
    configure(max_name_chars=1000)
    assert store.forget_stale_reads(conn, folder) == 1  # they have: what was cut is read again


def test_a_raised_limit_lets_longer_names_sources_and_text_through_whole(configure, conn, tmp_path):
    """A hard-coded copy of a limit anywhere in the path (validation as well as repair) would reject or cut these."""
    folder = tmp_path / "results"
    folder.mkdir()
    configure(max_name_chars=1000, max_source_chars=2000, max_text_chars=100_000)
    d = _document(name="n" * 700, text="t" * 60_000, source="s" * 1500)
    (folder / f"{'a' * 64}.json").write_text(json.dumps(d))
    assert store.ingest_dir(conn, folder, on_rejected=lambda *a: None)["new"] == 1
    row = conn.execute("SELECT name, length(text) AS n, source FROM documents").fetchone()
    assert len(row["name"]) == 700 and row["n"] == 60_000 and len(row["source"]) == 1500
    assert "limits_hit" not in conn.execute("SELECT data FROM documents").fetchone()["data"]


def test_the_same_document_under_the_default_limits_is_not_cut_either(conn, tmp_path):
    folder = tmp_path / "results"
    folder.mkdir()
    (folder / f"{'b' * 64}.json").write_text(json.dumps(_document("b", name="n" * 255, text="t" * 10_000)))
    store.ingest_dir(conn, folder, on_rejected=lambda *a: None)
    assert len(conn.execute("SELECT name FROM documents").fetchone()["name"]) == 255
