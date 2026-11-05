"""Pictures: the shared engine run for every picture. One indexer reads the photo folder, the service answers from the index, and the text found in
pictures joins the documents' text in one search."""

import json
import threading
import time
from http.server import ThreadingHTTPServer
from io import BytesIO

import pytest
from images.config import ENV_INTERNAL
from images.indexing.pipeline import STAGE_OCR, Services
from kit import db
from PIL import Image

from library import indexer, pictures, store, web
from tests.test_web import call, post


class FakeOCR:
    def read(self, image_bytes: bytes) -> str:
        px = Image.open(BytesIO(image_bytes)).convert("RGB").getpixel((5, 5))
        return "Albert Heijn kassabon totaal 23,45 euro Utrecht" if px[0] > 150 else ""


@pytest.fixture
def drive(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_INTERNAL, "1")
    monkeypatch.setenv("LIBRARY_PICTURES_DRIVE", str(tmp_path / "drive"))
    monkeypatch.setenv("LIBRARY_PHOTOS", str(tmp_path / "drive" / "Photos"))
    photos = tmp_path / "drive" / "Photos"
    photos.mkdir(parents=True)
    Image.new("RGB", (120, 100), (220, 20, 20)).save(photos / "receipt.jpg")  # text in it
    Image.new("RGB", (120, 100), (20, 20, 220)).save(photos / "beach.jpg")  # no text
    return tmp_path / "drive"


def engine_with_fake_models():
    engine = pictures.build_engine()
    engine.services_for_stage = lambda stage: Services(ocr=FakeOCR()) if stage == STAGE_OCR else Services()
    return engine


def test_the_indexer_reads_the_photo_folder_and_reports_through_its_state_file(drive):
    engine = engine_with_fake_models()
    assert pictures.scan_state(engine)["running"] is False
    summary = indexer.run_once(engine)
    assert "2 of 2 pictures read" in summary and pictures.scan_state(engine)["summary"] == summary and pictures.counts(engine) == {"pictures": 2, "indexed": 2}


def test_pictures_are_found_by_the_words_in_them_and_have_a_thumbnail(drive):
    engine = engine_with_fake_models()
    indexer.run_once(engine)
    [found] = pictures.search(engine, "kassabon Utrecht")
    assert found["name"] == "receipt.jpg" and pictures.thumb_file(engine, found["id"]) is not None
    assert pictures.thumb_file(engine, 99999) is None


def test_text_in_pictures_joins_the_documents_in_one_search(drive, tmp_path):
    engine = engine_with_fake_models()
    indexer.run_once(engine)
    conn = db.connect(tmp_path / "lib.db")
    db.migrate(conn, [store.MODULE])
    hits = store.passages(conn, "Albert Heijn kassabon", 5, extra=pictures.text_sources(engine))
    assert hits and hits[0]["source"] == "picture" and hits[0]["title"] == "receipt.jpg"


def test_the_service_serves_the_pictures_api_and_update_waits_for_the_indexer(drive, tmp_path, monkeypatch):
    monkeypatch.setenv("ORBIT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ORBIT_PARSED", str(tmp_path / "parsed"))
    monkeypatch.setattr(web, "SETTLE_SECONDS", 0.05)
    monkeypatch.setattr(web, "model_client", lambda: (None, ""))
    monkeypatch.setattr(pictures, "wait_for_scan", lambda engine, progress, **kw: indexer.run_once(engine))  # the sealed indexer, run in-process
    (tmp_path / "home").mkdir()
    state = web.State()
    state._engine = engine_with_fake_models()
    c = state.connect()
    db.migrate(c, [store.MODULE])
    c.close()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(state))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    try:
        assert post(port, "/api/scan", {})[1]["started"] is True
        for _ in range(200):
            status = call(port, "GET", "/api/scan")[1]
            if not status["running"]:
                break
            time.sleep(0.05)
        assert "2 of 2 pictures read" in status["summary"]
        [pic] = call(port, "GET", "/api/pictures?q=kassabon")[1]["pictures"]
        assert pic["name"] == "receipt.jpg" and call(port, "GET", "/api/pictures/status")[1]["pictures"] == 2
        status_code, body, headers = call(port, "GET", pic["thumb"])
        assert status_code == 200 and headers["Content-Type"] == "image/jpeg" and body[:2] == b"\xff\xd8"
        asked = post(port, "/api/ask", {"text": "show me the kassabon photos", "show": {"photos": True}})[1]
        assert asked["items"] and asked["items"][0]["kind"] == "photo" and asked["items"][0]["thumb"] == pic["thumb"]
        assert call(port, "GET", "/api/pictures/thumb/abc")[0] == 404 and json.dumps(1)
    finally:
        httpd.shutdown()
