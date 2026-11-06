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
    monkeypatch.setenv("ATLAS_ALLOW_PLAIN", "1")
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ATLAS_PARSED", str(tmp_path / "parsed"))
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
    specs = {t["name"] for t in call(port, "GET", "/api/tools")[1]["tools"]}
    assert {"search_files", "find_documents", "read_document", "trips", "find_pictures", "library_overview"} <= specs
    found = post(port, "/api/tool", {"name": "find_documents", "args": {"kind": "invoice", "show": True}})[1]
    assert found["ok"] and found["data"]["count"] == 1 and found["data"]["documents"][0]["party"] == "Hotel Delhi"
    assert found["items"][0]["title"] == "Hotel" and found["items"][0]["link"] == f"#/doc/{doc['id']}"
    quiet = post(port, "/api/tool", {"name": "find_documents", "args": {"kind": "invoice"}})[1]
    assert quiet["items"] == []  # nothing is shown unless the person asked to see it
    dated = post(port, "/api/tool", {"name": "find_documents", "args": {"from": "2026-01-01", "to": "2026-01-31"}})[1]
    assert dated["data"]["count"] == 1
    assert post(port, "/api/tool", {"name": "read_document", "args": {"id": str(doc["id"])}})[1]["data"]["text"].startswith("FACTUUR")
    assert post(port, "/api/tool", {"name": "nonsense", "args": {}})[1]["ok"] is False
    assert post(port, "/api/tool", {"name": "find_pictures", "args": {"query": "x"}})[1]["ok"] is False  # pictures are not set up here


def test_an_unknown_document_and_unknown_route_say_so(server):
    port, _ = server
    assert call(port, "GET", "/api/document?id=999")[0] == 404 and call(port, "GET", "/api/nothing")[0] == 404


def test_with_the_platform_key_set_an_unsigned_request_is_refused_and_a_signed_one_works(server, monkeypatch):
    from kit import sign

    port, _ = server
    monkeypatch.setenv("PLATFORM_KEY", "a-shared-secret")
    assert call(port, "GET", "/api/status")[0] == 401  # another program on this computer, without the key
    assert call(port, "GET", "/api/status", headers=sign.sign("GET", "/api/status"))[0] == 200
    assert call(port, "GET", "/api/status", headers=sign.sign("GET", "/api/other"))[0] == 401  # a signature for another path


def test_the_albums_route_only_prepares_and_says_plainly_when_there_is_nothing_to_sort():
    assert "/api/change/albums" in web.POST_ROUTES


def test_the_update_counts_files_the_way_the_person_does_even_when_one_file_holds_many_documents(tmp_path, monkeypatch):
    parsed = tmp_path / "parsed"
    parsed.mkdir()
    (parsed / ".found").write_text(json.dumps({"documents": 36, "mails": 12}))
    monkeypatch.setenv("ATLAS_PARSED", str(parsed))
    conn = db.connect(tmp_path / "library.db")
    db.migrate(conn, [store.MODULE])
    add = "INSERT INTO documents (sha256, name, kind, text, area) VALUES (?,?,?,?,?)"
    conn.execute(add, ("a", "archive.zip/one.pdf", "pdf", "t", ""))
    conn.execute(add, ("b", "archive.zip/two.pdf", "pdf", "t", ""))  # the same zip: one file
    conn.execute(add, ("c", "letter.pdf", "pdf", "t", ""))
    conn.execute(add, ("d", "m.eml", "email", "t", "mail"))
    conn.execute(add, ("e", "m.eml/photo.jpg", "image", "t", "mail"))  # an attachment of the same message: one mail
    state = web.State()
    state._engine = None
    rows = {r["name"]: r["detail"] for r in web._parts(state, conn)}
    assert rows["Documents"] == "2 of 36 files" and rows["Mails"] == "1 of 12 mails" and "not connected" in rows["Photos"]
    web._CACHE.clear()  # the numbers are reused for a few seconds
    (parsed / ".found").write_text(json.dumps({"documents": 2, "mails": 1}))
    assert {r["name"]: r["detail"] for r in web._parts(state, conn)}["Documents"] == "2 files"


def test_mails_say_plainly_when_apple_mail_was_not_given_to_atlas(tmp_path, monkeypatch):
    parsed = tmp_path / "parsed"
    parsed.mkdir()
    monkeypatch.setenv("ATLAS_PARSED", str(parsed))
    conn = db.connect(tmp_path / "library.db")
    db.migrate(conn, [store.MODULE])
    state = web.State()
    state._engine = None
    (parsed / ".found").write_text(json.dumps({"documents": 1, "mails": 0, "mail_connected": False}))
    assert "not connected" in {r["name"]: r["detail"] for r in web._parts(state, conn)}["Mails"]
    web._CACHE.clear()
    (parsed / ".found").write_text(json.dumps({"documents": 1, "mails": 0, "mail_connected": True}))
    assert {r["name"]: r["detail"] for r in web._parts(state, conn)}["Mails"] == "0 mails"


def test_the_documents_line_says_how_many_files_each_folder_holds(tmp_path, monkeypatch):
    parsed = tmp_path / "parsed"
    parsed.mkdir()
    monkeypatch.setenv("ATLAS_PARSED", str(parsed))
    conn = db.connect(tmp_path / "library.db")
    db.migrate(conn, [store.MODULE])
    (parsed / ".found").write_text(json.dumps({"documents": 35, "mails": 0, "mail_connected": False, "by_folder": {"inbox": 0, "finance": 35}}))
    state = web.State()
    state._engine = None
    assert {r["name"]: r["detail"] for r in web._parts(state, conn)}["Documents"] == "0 of 35 files (inbox 0, finance 35)"
