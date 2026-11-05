"""The Documents service over HTTP: only this computer's names, changes need its own header, an Update reads and judges everything, and apps can ask by kind."""

import http.client
import json
import threading
import time
from http.server import ThreadingHTTPServer

import pytest
from kit import db

from library import parser, store, web


class Model:
    def chat(self, model, messages, schema=None, **kw):
        if schema:
            return {
                "content": json.dumps({"kind": "invoice", "title": "Hotel", "party": "Hotel Delhi", "date": "2026-01-12", "total": "480,00", "currency": "EUR"})
            }
        return {"content": "You paid 480 euros for the hotel."}


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBIT_ALLOW_PLAIN", "1")
    monkeypatch.setenv("ORBIT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ORBIT_PARSED", str(tmp_path / "parsed"))
    monkeypatch.setattr(web, "SETTLE_SECONDS", 0.05)
    monkeypatch.setattr(web, "model_client", lambda: (Model(), "fake"))
    (tmp_path / "home").mkdir()
    state = web.State()
    c = state.connect()
    db.migrate(c, [store.MODULE])
    c.close()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(state))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1], tmp_path
    httpd.shutdown()


def call(port, method, path, body=None, host=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(method, path, json.dumps(body) if body is not None else None, {"Host": host or f"127.0.0.1:{port}", **(headers or {})})
    r = conn.getresponse()
    data = r.read()
    conn.close()
    return r.status, json.loads(data) if data.startswith((b"{", b"[")) else data, dict(r.getheaders())


def post(port, path, body):
    return call(port, "POST", path, body, headers={"X-Library": "1"})


def test_the_page_is_served_and_other_host_names_are_refused(server):
    port, _ = server
    status, body, headers = call(port, "GET", "/")
    assert status == 200 and b"Documents" in body and "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert call(port, "GET", "/api/status", host="evil.example.com")[0] == 403
    assert call(port, "GET", "/api/status", host="library.internal:8502")[0] == 200  # how the other apps reach it inside Docker


def test_changes_need_the_services_own_header_and_a_local_origin(server):
    port, _ = server
    assert call(port, "POST", "/api/scan", {})[0] == 403
    assert call(port, "POST", "/api/scan", {}, headers={"X-Library": "1", "Origin": "http://evil.example.com"})[0] == 403


def test_one_update_reads_judges_and_serves_everything(server):
    port, tmp = server
    inbox = tmp / "in"
    inbox.mkdir()
    (inbox / "hotel.txt").write_text("FACTUUR Hotel Delhi 12-01-2026 totaal 480,00 EUR betaling ontvangen")
    parser.process_inbox(inbox, tmp / "parsed", isolated=False)
    assert post(port, "/api/scan", {})[1]["started"] is True
    for _ in range(100):
        state = call(port, "GET", "/api/scan")[1]
        if not state["running"]:
            break
        time.sleep(0.05)
    assert not state["running"] and state["problems"] == [] and "1 new file" in state["summary"]
    [doc] = call(port, "GET", "/api/documents?kind=invoice&full=1")[1]["documents"]
    assert doc["facts"]["party"] == "Hotel Delhi" and "FACTUUR" in doc["text"]
    assert call(port, "GET", "/api/documents?kind=ticket")[1]["documents"] == []
    assert call(port, "GET", f"/api/document?id={doc['id']}")[1]["name"] == "hotel.txt"
    assert call(port, "GET", "/api/search?q=hotel")[1]["results"][0]["link"] == f"#/doc/{doc['id']}"
    asked = post(port, "/api/ask", {"text": "what did the hotel cost", "show": {"documents": True}})[1]
    assert asked["items"][0]["title"] == "hotel.txt" and "1 file" in asked["text"]
    in_words = post(port, "/api/ask", {"text": "what did the hotel cost"})[1]
    assert "480" in in_words["text"] and in_words["items"] == []


def test_an_unknown_document_and_unknown_route_say_so(server):
    port, _ = server
    assert call(port, "GET", "/api/document?id=999")[0] == 404 and call(port, "GET", "/api/nothing")[0] == 404
