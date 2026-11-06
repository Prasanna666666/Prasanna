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
    hits = store.passages(conn, "Albert Heijn kassabon", 5, more_sources=pictures.text_sources(engine))
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
        asked = post(port, "/api/tool", {"name": "find_pictures", "args": {"query": "kassabon", "show": True}})[1]
        assert asked["data"]["count"] == 1 and asked["items"][0]["kind"] == "photo" and asked["items"][0]["thumb"] == pic["thumb"]
        assert post(port, "/api/tool", {"name": "find_pictures", "args": {"query": "kassabon"}})[1]["items"] == []
        assert post(port, "/api/tool", {"name": "find_pictures", "args": {"from": "2000-01-01", "to": "2000-12-31"}})[1]["data"]["count"] == 0
        assert call(port, "GET", "/api/pictures/thumb/abc")[0] == 404 and json.dumps(1)
    finally:
        httpd.shutdown()


def test_pictures_taken_within_a_window_are_found_by_date(drive):
    engine = engine_with_fake_models()
    indexer.run_once(engine)
    conn = engine.db.connect()
    conn.execute("UPDATE items SET taken_at='2026-01-14T10:00:00' WHERE rel_path LIKE '%receipt%'")
    conn.execute("UPDATE items SET taken_at='2026-03-02T10:00:00' WHERE rel_path LIKE '%beach%'")
    conn.commit()
    conn.close()
    assert [p["name"] for p in pictures.find(engine, {"from": "2026-01-12", "to": "2026-01-30"})] == ["receipt.jpg"]
    assert pictures.find(engine, {"from": "2025-01-01", "to": "2025-12-31"}) == []
    assert [p["name"] for p in pictures.find(engine, {"query": "kassabon", "year": "2026"})] == ["receipt.jpg"]  # words and a year together
    assert pictures.find(engine, {}) == []  # nothing to look for: nothing returned, never everything


def test_the_library_can_be_browsed_as_pages_and_a_picture_is_described(drive):
    engine = engine_with_fake_models()
    indexer.run_once(engine)
    page = pictures.browse(engine, "library", {"year": "2026"})
    assert {"ids", "total", "offset", "more"} <= set(page) and page["total"] == 2
    assert pictures.browse(engine, "timeline", {})["total"] == 2
    assert isinstance(pictures.browse(engine, "trips", {}), list) and isinstance(pictures.browse(engine, "people", {}), list)
    try:
        pictures.browse(engine, "nonsense", {})
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown page must be refused")
    [first, *_] = page["ids"]
    assert pictures.item(engine, first)["name"].endswith(".jpg") and pictures.item(engine, 99999) is None
    assert pictures.preview_file(engine, first) is None or pictures.preview_file(engine, first).is_file()


def test_a_photographed_receipt_becomes_a_document_that_is_judged_like_any_other(drive, tmp_path):
    import json

    class ReceiptOCR(FakeOCR):
        def read(self, image_bytes):
            return "KASSABON bon betaling totaal EUR 23,45 Albert Heijn Utrecht" if super().read(image_bytes) else ""

    engine = pictures.build_engine()
    engine.services_for_stage = lambda stage: Services(ocr=ReceiptOCR()) if stage == STAGE_OCR else Services()
    indexer.run_once(engine)
    conn = db.connect(tmp_path / "docs.db")
    db.migrate(conn, [store.MODULE])
    index = engine.db.connect()
    assert store.ingest_pictures(conn, index) == 1  # only the picture with a receipt's text; the beach photo has none
    assert store.ingest_pictures(conn, index) == 0  # and never twice
    index.execute(
        "UPDATE items SET rel_path='Inbox/other.jpg' WHERE rel_path='beach.jpg'"
    )  # a picture that came with the inbox is read by the document reader already
    index.commit()

    class Model:
        def chat(self, model, messages, **kw):
            return {"content": json.dumps({"kind": "receipt", "title": "Albert Heijn", "party": "Albert Heijn", "total": "23,45", "currency": "EUR"})}

    assert store.judge_pending(conn, Model(), "fake")["read"] == 1
    [doc] = store.list_documents(conn, ["receipt"])
    assert doc["area"] == "pictures" and doc["name"] == "receipt.jpg" and float(doc["facts"]["total"]) == 23.45  # Finance takes it from here like any receipt
