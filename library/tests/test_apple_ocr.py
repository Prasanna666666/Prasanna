"""Apple's text recognition is used when its helper is running, and the usual reader takes over when it is not."""

import threading
import time

from library import readers


def helper(folder, stop):
    """Stands in for the sandboxed Mac helper: it answers every page picture with a word table."""
    while not stop.is_set():
        (folder / "alive").write_text("alive")
        for p in folder.glob("*.png"):
            (folder / (p.stem + ".part")).write_text(
                "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t1\t1\t1\t10\t20\t30\t8\t95\tTotal\n"
            )
            (folder / (p.stem + ".part")).rename(folder / (p.stem + ".tsv"))
            p.unlink()
        time.sleep(0.01)


def test_a_page_goes_to_the_helper_and_comes_back_and_nothing_is_left_behind(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_OCR_DIR", str(tmp_path))
    stop = threading.Event()
    threading.Thread(target=helper, args=(tmp_path, stop), daemon=True).start()
    time.sleep(0.1)
    words, confidence = readers.ocr_words(b"\x89PNG fake page", 1.0)
    stop.set()
    assert [w[4] for w in words] == ["Total"] and confidence == 95.0
    assert not list(tmp_path.glob("*.png")) and not list(tmp_path.glob("*.tsv"))  # the page and the answer are gone


def test_without_a_running_helper_the_usual_reader_is_used(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_OCR_DIR", str(tmp_path))  # a folder, but no helper has written its sign of life
    assert readers.apple_ocr(b"x") is None
    monkeypatch.delenv("LIBRARY_OCR_DIR")
    assert readers.apple_ocr(b"x") is None
    (tmp_path / "alive").write_text("x")
    monkeypatch.setenv("LIBRARY_OCR_DIR", str(tmp_path))
    old = time.time() - 60
    import os

    os.utime(tmp_path / "alive", (old, old))
    assert readers.apple_ocr(b"x") is None  # the sign of life is old: the helper has stopped


def test_what_was_read_under_other_limits_or_a_worse_engine_is_read_again_by_itself(conn, tmp_path):
    import json

    from library import limits, store

    now = limits.version()
    rows = (
        ("cut under old limits.pdf", "t", {"meta": {"limits_hit": ["ocr"], "limits_version": "old"}}),
        ("cut under the limits in force.pdf", "t", {"meta": {"limits_hit": ["ocr"], "limits_version": now}}),
        ("never cut.pdf", "t", {"meta": {"limits_hit": [], "limits_version": "old"}}),
        ("read before versions existed, cut.pdf", "t", {"meta": {"ocr_cut_short": True}}),
        ("scan by the old engine.pdf", "t", {"meta": {"ocr_pages": 2, "ocr_engine": "tesseract", "limits_hit": [], "limits_version": now}}),
        ("scan by the better engine.pdf", "t", {"meta": {"ocr_pages": 2, "ocr_engine": "apple", "limits_hit": [], "limits_version": now}}),
    )
    for i, (name, text, data) in enumerate(rows):
        conn.execute(
            "INSERT INTO documents (sha256, name, kind, text, area, data) VALUES (?,?,?,?,?,?)", (f"{i:064x}", name, "pdf", text, "", json.dumps(data))
        )
    conn.commit()
    assert store.forget_stale_reads(conn, tmp_path) == 2  # no better engine: only what limits left something out of
    assert store.forget_stale_reads(conn, tmp_path, "apple") == 1  # the better engine appears: the scan read by another one
    assert sorted(r["name"] for r in conn.execute("SELECT name FROM documents")) == [
        "cut under the limits in force.pdf",
        "never cut.pdf",
        "scan by the better engine.pdf",
    ]
