"""The Documents service over HTTP: only this computer's names, changes need its own header, an Update reads and judges everything, and apps can ask by kind."""

import http.client
import json
import threading
import time
from http.server import ThreadingHTTPServer

import pytest
from kit import db

from library import appstate, judging, parser, reading, scanstatus, store, web
from library.appstate import State


class Model:
    def chat(self, model, messages, schema=None, **kw):
        if schema:
            return {
                "content": json.dumps(
                    {
                        "kind": "invoice",
                        "apps": ["finance"],
                        "title": "Hotel",
                        "what": "A hotel",
                        "party": "Hotel Delhi",
                        "date": "2026-01-12",
                        "total": "480,00",
                        "currency": "EUR",
                    }
                )
            }
        return {"content": "You paid 480 euros for the hotel."}


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_ALLOW_PLAIN", "1")
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ATLAS_PARSED", str(tmp_path / "parsed"))
    monkeypatch.setattr(reading, "SETTLE_SECONDS", 0.05)
    monkeypatch.setattr(reading, "READER_START_SECONDS", 0.2)  # no reader runs in these tests
    monkeypatch.setattr(appstate, "model_client", lambda: (Model(), "fake"))
    (tmp_path / "home").mkdir()
    state = State()
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
    found = post(port, "/api/tool", {"name": "find_documents", "args": {"kind": "invoice", "apps": ["finance"], "show": True}})[1]
    assert found["ok"] and found["data"]["count"] == 1 and found["data"]["documents"][0]["party"] == "Hotel Delhi"
    assert found["items"][0]["title"] == "Hotel · Hotel Delhi" and found["items"][0]["link"] == f"#/doc/{doc['id']}"
    quiet = post(port, "/api/tool", {"name": "find_documents", "args": {"kind": "invoice", "apps": ["finance"]}})[1]
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
    state = State()
    state._engine = None
    rows = {r["name"]: r["detail"] for r in scanstatus._parts(state, conn)}
    assert (
        rows["Documents"] == "2 of 36 files · 0 sorted · 2 to do"
        and rows["Mails"] == "1 of 12 mails · 0 sorted · 1 to do"
        and "not connected" in rows["Photos"]
    )
    scanstatus._CACHE.clear()  # the numbers are reused for a few seconds
    (parsed / ".found").write_text(json.dumps({"documents": 2, "mails": 1}))
    assert {r["name"]: r["detail"] for r in scanstatus._parts(state, conn)}["Documents"] == "2 files · 0 sorted · 2 to do"


def test_mails_say_plainly_when_apple_mail_was_not_given_to_atlas(tmp_path, monkeypatch):
    parsed = tmp_path / "parsed"
    parsed.mkdir()
    monkeypatch.setenv("ATLAS_PARSED", str(parsed))
    conn = db.connect(tmp_path / "library.db")
    db.migrate(conn, [store.MODULE])
    state = State()
    state._engine = None
    (parsed / ".found").write_text(json.dumps({"documents": 1, "mails": 0, "mail_connected": False}))
    assert "not connected" in {r["name"]: r["detail"] for r in scanstatus._parts(state, conn)}["Mails"]
    scanstatus._CACHE.clear()
    (parsed / ".found").write_text(json.dumps({"documents": 1, "mails": 0, "mail_connected": True}))
    assert {r["name"]: r["detail"] for r in scanstatus._parts(state, conn)}["Mails"] == "0 mails"


def test_the_documents_line_says_how_many_files_each_folder_holds(tmp_path, monkeypatch):
    parsed = tmp_path / "parsed"
    parsed.mkdir()
    monkeypatch.setenv("ATLAS_PARSED", str(parsed))
    conn = db.connect(tmp_path / "library.db")
    db.migrate(conn, [store.MODULE])
    (parsed / ".found").write_text(json.dumps({"documents": 35, "mails": 0, "mail_connected": False, "by_folder": {"inbox": 0, "finance": 35}}))
    state = State()
    state._engine = None
    assert {r["name"]: r["detail"] for r in scanstatus._parts(state, conn)}["Documents"] == "0 of 35 files"


def test_the_documents_line_names_each_category_and_leaves_out_empty_folders(tmp_path, monkeypatch):
    parsed = tmp_path / "parsed"
    parsed.mkdir()
    monkeypatch.setenv("ATLAS_PARSED", str(parsed))
    conn = db.connect(tmp_path / "library.db")
    db.migrate(conn, [store.MODULE])
    (parsed / ".found").write_text(
        json.dumps(
            {
                "documents": 339,
                "mails": 0,
                "mail_connected": True,
                "by_folder": {"inbox": 0, "finance": 156, "health": 37, "travel": 42, "personal": 104, "others": 0},
            }
        )
    )
    state = State()
    state._engine = None
    assert {r["name"]: r["detail"] for r in scanstatus._parts(state, conn)}[
        "Documents"
    ] == "0 of 339 files · Finance 156 · Health 37 · Travel 42 · Personal 104"
    scanstatus._CACHE.clear()
    (parsed / ".found").write_text(json.dumps({"documents": 5, "mails": 0, "mail_connected": True, "by_folder": {"inbox": 5}}))
    assert {r["name"]: r["detail"] for r in scanstatus._parts(state, conn)}["Documents"] == "0 of 5 files"  # one folder only: nothing to break down


def test_pause_really_waits_resume_carries_on_and_stop_really_ends_a_running_read(tmp_path, monkeypatch):
    """The whole path over HTTP, with a model that takes a moment per document: the buttons change what the reader does, not only what the page says."""
    monkeypatch.setenv("ATLAS_ALLOW_PLAIN", "1")
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ATLAS_PARSED", str(tmp_path / "parsed"))
    monkeypatch.setattr(reading, "SETTLE_SECONDS", 0.05)
    monkeypatch.setattr(reading, "READER_START_SECONDS", 0.2)  # no reader runs in these tests
    monkeypatch.setattr(store, "GENTLE_SECONDS", 0)
    (tmp_path / "home").mkdir()
    (tmp_path / "parsed").mkdir()
    asked = []

    class Slow:
        def chat(self, model, messages, schema=None, **kw):
            asked.append(1)
            time.sleep(0.05)
            return {"content": json.dumps({"kind": "other", "title": "x"})}

    monkeypatch.setattr(appstate, "model_client", lambda: (Slow(), "fake"))
    state = State()
    c = state.connect()
    db.migrate(c, [store.MODULE])
    for i in range(400):  # a folder of its own (a category folder): every file goes to the model
        c.execute("INSERT INTO documents (sha256, name, kind, text, area) VALUES (?,?,?,?,?)", (f"{i:064x}", f"f{i}.txt", "text", f"note {i}", "personal"))
    c.commit()
    c.close()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(state))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]

    def status():
        return call(port, "GET", "/api/scan")[1]

    def waiting():
        conn = state.connect()
        try:
            return conn.execute("SELECT COUNT(*) FROM documents WHERE judged=0").fetchone()[0]
        finally:
            conn.close()

    assert post(port, "/api/scan", {})[1]["started"] is True
    deadline = time.monotonic() + 10
    while len(asked) < 5 and time.monotonic() < deadline:
        time.sleep(0.02)
    assert len(asked) >= 5 and status()["running"] is True
    assert post(port, "/api/scan/pause", {})[1] == {"ok": True, "control": "pause"}
    time.sleep(0.4)  # whatever was in flight finishes
    frozen = len(asked)
    time.sleep(1.0)
    assert len(asked) == frozen and status()["paused"] is True and status()["running"] is True  # paused: no more documents are read, the read is still there
    assert post(port, "/api/scan/resume", {})[1]["control"] == "run"
    time.sleep(0.6)
    assert len(asked) > frozen + 3 and status()["paused"] is False  # carried on
    before_stop = waiting()
    assert post(port, "/api/scan/stop", {})[1] == {"ok": True, "control": "stop"}
    deadline = time.monotonic() + 5
    while status()["running"] and time.monotonic() < deadline:
        time.sleep(0.05)
    done = status()
    assert done["running"] is False and done["summary"].startswith("Stopped")  # it really ended, within a moment, and says so
    after = waiting()
    assert 0 < after <= before_stop  # the rest is still waiting for the next read; nothing was lost
    reads = len(asked)
    time.sleep(0.5)
    assert len(asked) == reads  # and nothing keeps working in the background
    assert post(port, "/api/scan/stop", {})[1]["ok"] is False  # nothing is running now: it says so instead of pretending
    httpd.shutdown()


def test_a_status_question_is_answered_at_once_from_the_last_answer_and_refreshed_in_the_background(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_PARSED", str(tmp_path / "parsed"))
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path))
    monkeypatch.setenv("ATLAS_ALLOW_PLAIN", "1")
    (tmp_path / "parsed").mkdir()
    state = State()
    conn = state.connect()
    db.migrate(conn, [store.MODULE])
    scanstatus._CACHE.clear()
    gate = threading.Event()
    calls = []

    def make(c):
        calls.append(1)
        if len(calls) > 1:
            gate.wait(5)  # the second look is slow, as when a big read keeps the database busy
        return {"n": len(calls)}

    assert scanstatus._cached("k", make, state, conn) == {"n": 1}  # the first time: worked out on the spot
    monkeypatch.setattr(scanstatus, "STATUS_TTL", 0.0)  # now every answer is "old"
    started = time.monotonic()
    assert scanstatus._cached("k", make, state, conn) == {"n": 1} and time.monotonic() - started < 0.5  # given at once, not after the slow look
    deadline = time.monotonic() + 5
    while len(calls) < 2 and time.monotonic() < deadline:
        time.sleep(0.02)  # the background look has started
    assert scanstatus._cached("k", make, state, conn) == {"n": 1} and scanstatus._cached("k", make, state, conn) == {"n": 1}
    assert len(calls) == 2  # one refresh at a time, however often it is asked
    gate.set()
    deadline = time.monotonic() + 5
    while scanstatus._CACHE["k"][1] != {"n": 2} and time.monotonic() < deadline:
        time.sleep(0.02)
    assert scanstatus._CACHE["k"][1] == {"n": 2}  # and the background look brought it up to date
    conn.close()


def test_automatic_reading_only_starts_for_a_small_backlog_and_never_before_a_first_read(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from library import flags

    parsed = tmp_path / "parsed"
    monkeypatch.setattr(appstate, "parsed_dir", lambda: parsed)
    started = []
    monkeypatch.setattr(reading, "_read_all", lambda state: started.append(1))
    state = State()
    conn = SimpleNamespace()
    monkeypatch.setattr(scanstatus, "backlog", lambda c: 5)
    monkeypatch.setattr(scanstatus, "_found", dict)
    assert reading._post_auto(state, conn, {})["started"] is False  # no first read yet: that one is the person's
    monkeypatch.setattr(scanstatus, "_found", lambda: {"documents": 10, "mails": 0})
    monkeypatch.setattr(scanstatus, "backlog", lambda c: reading.AUTO_LIMIT + 1)
    out = reading._post_auto(state, conn, {})
    assert out["started"] is False and out["reason"] == "large" and "fewer than" in state.scan["summary"]
    monkeypatch.setattr(scanstatus, "backlog", lambda c: 5)
    out = reading._post_auto(state, conn, {})
    assert out["started"] is True and (parsed / flags.AUTO_LIMIT).read_text() == str(reading.AUTO_LIMIT)


def test_percentages_never_round_up_to_a_finish_that_has_not_happened():
    assert (
        scanstatus._percent(17, 1201) == "1.4%"
        and scanstatus._percent(600, 1201) == "50%"
        and scanstatus._percent(1200, 1201) == "99%"
        and scanstatus._percent(1201, 1201) == "100%"
    )
    assert scanstatus._percent(0, 0) == "0%"


def test_the_file_being_read_shows_exact_progress_for_parts_and_only_an_estimate_for_a_single_call(conn):
    import time

    now = time.monotonic()
    running = {"running": True, "run": "r1", "now_since": now - 10}
    medical = scanstatus._file_now({**running, "now": ("report.pdf", "reading part", "reading part 3 of 9")}, conn)
    assert medical["step"] == "reading part 3 of 9" and medical["estimated"] is True  # not "reading part: reading part 3 of 9"
    assert medical["percent"] == 29.6  # two parts are done, and 10 s of a first guess of 15 s into the third: (2 + 0.67) / 9
    later = scanstatus._file_now({**running, "now_since": now - 400, "now": ("report.pdf", "reading part", "reading part 1 of 2")}, conn)
    assert later["percent"] == 47.5  # a long wait inside part 1 of 2 never reaches the end of the part: (0 + 0.95) / 2
    first = scanstatus._file_now({**running, "now": ("a.pdf", "sorting", "31 characters")}, conn)
    assert first["estimated"] is True and first["percent"] == 66.7  # no file has finished yet: 10 s of a first guess of 15 s, marked as an estimate
    conn.execute("INSERT INTO trace (run, at, name, step, detail, seconds) VALUES ('r1','12:00:00','x.pdf','sorted','invoice',20)")
    guess = scanstatus._file_now({**running, "now": ("a.pdf", "sorting", "31 characters")}, conn)
    assert guess["estimated"] is True and guess["percent"] == 50.0  # 10 s of the usual 20 s
    assert scanstatus._file_now({**running, "running": False, "now": ("a.pdf", "sorting", "")}, conn) is None
    assert (
        scanstatus._share(17, 1201) == 1.4
        and scanstatus._share(1201, 1201) == 100.0
        and scanstatus._share(1200, 1201) == 99.9
        and scanstatus._share(0, 0) == 0.0
    )


def test_the_report_names_the_files_waiting_and_counts_set_aside_files_apart_from_identified_ones(conn):
    for i, area in enumerate(("finance", "", "mail", "finance")):
        conn.execute("INSERT INTO documents (sha256, name, kind, text, area, judged) VALUES (?,?,?,?,?,0)", (f"{i:064x}", f"f{i}.pdf", "pdf", "text", area))
    conn.execute("INSERT INTO documents (sha256, name, kind, text, area, judged) VALUES ('z','done.pdf','pdf','text','finance',1)")
    conn.execute("INSERT INTO documents (sha256, name, kind, text, area, judged) VALUES ('y','junk.eml','email','','mail',2)")
    conn.commit()
    assert judging.waiting_files(conn, current="f0.pdf", limit=3) == [
        "f3.pdf",
        "f1.pdf",
        "f2.pdf",
    ]  # named folders first, then loose files, then mail; not the one being read
    assert scanstatus._states(conn, "1=1") == {"identified": 1, "aside": 1, "waiting": 4, "unclear": 0}  # a file skipped is not counted as identified
    steps = scanstatus._steps(conn, {"phase": 2})
    assert [(x["n"], x["name"], x["state"]) for x in steps][1] == (2, "Sort", "running")
    assert {c["key"]: (c["done"], c["total"]) for c in steps[1]["counts"]} == {
        "documents": (1, 4),
        "mails": (1, 1),
        "attachments": (0, 1),
    }  # each kind of file is counted on its own
    assert len(steps) == 3 and steps[2]["state"] == "waiting"
    assert scanstatus._steps(conn, {"phase": 4})[2]["state"] == "running"


def test_the_status_counts_through_the_database_once_not_at_every_question(conn, monkeypatch):
    calls = []
    real = scanstatus._steps
    monkeypatch.setattr(scanstatus, "_steps", lambda c, s: calls.append(1) or real(c, s))
    scanstatus._CACHE.clear()
    state = type("S", (), {"connect": staticmethod(lambda: conn)})()
    running = {"running": True, "phase": 2, "app": "", "run": "r", "now": None}
    for _ in range(5):
        scanstatus._counted(state, conn, running)  # a status question every two seconds while a read goes on
    assert len(calls) == 1
