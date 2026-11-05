"""The text reader that stands in for Apple Vision where there is none (the Docker image)."""

import io
import shutil

import pytest

from images.ml import ocr


def test_tesseract_missing_or_failing_gives_no_text_not_a_crash(monkeypatch):
    def boom(*a, **k):
        raise OSError("no such program")

    monkeypatch.setattr(ocr.subprocess, "run", boom)
    assert ocr.TesseractOCR().read(b"not a picture") == ""


def test_text_available_when_either_reader_exists(monkeypatch):
    monkeypatch.setattr(ocr, "vision_available", lambda: False)
    monkeypatch.setattr(ocr, "tesseract_available", lambda: True)
    assert ocr.text_available() is True
    monkeypatch.setattr(ocr, "tesseract_available", lambda: False)
    assert ocr.text_available() is False


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract is not installed here")
def test_tesseract_reads_printed_words():
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (600, 160), "white")
    ImageDraw.Draw(img).text((20, 40), "HELLO LUMO 2025", fill="black", font=ImageFont.load_default(size=56))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    assert "LUMO" in ocr.TesseractOCR("eng").read(buf.getvalue()).upper()
