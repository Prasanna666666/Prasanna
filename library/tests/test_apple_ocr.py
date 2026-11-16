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
