"""The web interface: the page is served, only local host names are answered, changes need the custom header, and the tools work."""

import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from orbit import db, web
from orbit.modules import ALL


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBIT_ALLOW_PLAIN", "1")
    monkeypatch.setenv("ORBIT_HOME", str(tmp_path))
    c = db.connect()
    db.migrate(c, ALL)
    c.close()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(web.State()))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()


def call(port, method, path, body=None, host=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"Host": host or f"127.0.0.1:{port}", **(headers or {})}
    if body is not None:
        h["Content-Type"] = "application/json"
    conn.request(method, path, json.dumps(body) if body is not None else None, h)
    r = conn.getresponse()
    data = r.read()
    conn.close()
    return r.status, data, dict(r.getheaders())


def post(port, path, body, **kw):
    return call(port, "POST", path, body, headers={"X-Orbit": "1"}, **kw)


def test_the_page_and_its_files_are_served_with_safe_headers(server):
    status, body, headers = call(server, "GET", "/")
    assert status == 200 and b"Orbit" in body and "default-src 'self'" in headers["Content-Security-Policy"]
    assert call(server, "GET", "/static/app.js")[0] == 200 and call(server, "GET", "/static/app.css")[0] == 200


def test_a_request_for_any_other_host_name_is_refused(server):
    assert call(server, "GET", "/api/home", host="evil.example.com")[0] == 403  # also stops DNS rebinding
    assert call(server, "GET", "/api/home", host=f"localhost:{server}")[0] == 200


def test_changes_need_the_custom_header_and_a_local_origin(server):
    assert call(server, "POST", "/api/tool", {"name": "add_task", "args": {"title": "x"}})[0] == 403  # a web page on another site cannot send this
    assert (
        call(server, "POST", "/api/tool", {"name": "add_task", "args": {"title": "x"}}, headers={"X-Orbit": "1", "Origin": "http://evil.example.com"})[0] == 403
    )
    assert (
        call(server, "POST", "/api/tool", {"name": "add_task", "args": {"title": "x"}}, headers={"X-Orbit": "1", "Origin": f"http://127.0.0.1:{server}"})[0]
        == 200
    )


def test_tools_run_through_the_same_code_as_the_assistant(server):
    status, body, _ = post(server, "/api/tool", {"name": "add_task", "args": {"title": "Pay rent", "due": "2026-11-01"}})
    assert status == 200 and json.loads(body)["ok"] is True
    listed = json.loads(post(server, "/api/tool", {"name": "list_tasks", "args": {"status": "open"}})[1])["data"]
    assert [t["title"] for t in listed] == ["Pay rent"]
    bad = json.loads(post(server, "/api/tool", {"name": "add_transaction", "args": {"amount": -5}})[1])
    assert bad["ok"] is False and "positive" in bad["error"]
    assert post(server, "/api/tool", {"name": "drop_everything", "args": {}})[0] == 400


def test_files_outside_the_static_folder_cannot_be_read(server):
    assert call(server, "GET", "/static/../web.py")[0] == 404
    assert call(server, "GET", "/static/%2e%2e/web.py")[0] == 404


def test_settings_and_the_home_summary(server):
    assert post(server, "/api/settings", {"currency": "usd", "model": "ministral-3:3b"})[0] == 200
    settings = json.loads(call(server, "GET", "/api/settings")[1])
    assert settings["main_currency"] == "USD" and settings["view"] == "USD" and settings["currency"] == "USD"  # the default: your main currency, as it is
    home = json.loads(call(server, "GET", "/api/home")[1])
    assert home["ok"] and home["currency"] == "USD" and "briefing" in home
    assert post(server, "/api/settings", {"view_currency": "all"})[0] == 200  # the option: convert everything to euros
    converted = json.loads(call(server, "GET", "/api/settings")[1])
    assert converted["view"] == "ALL" and converted["currency"] == "EUR"


def test_chat_reports_a_missing_model_plainly(server, monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")  # nothing is listening
    status, body, _ = post(server, "/api/chat", {"text": "hello"})
    assert status == 502 and "Ollama" in json.loads(body)["error"]


def test_with_a_token_nothing_is_served_without_the_cookie(tmp_path, monkeypatch):
    import http.client
    import threading
    from http.server import ThreadingHTTPServer

    from orbit import db, web
    from orbit.modules import ALL

    monkeypatch.setenv("ORBIT_HOME", str(tmp_path))
    monkeypatch.delenv("ORBIT_DB_KEY", raising=False)
    c = db.connect()
    db.migrate(c, ALL)
    c.close()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(web.State(token="s3cret-token")))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]

    def get(path, cookie=None):
        conn = http.client.HTTPConnection("127.0.0.1", port)
        conn.request("GET", path, headers={"Host": f"127.0.0.1:{port}", **({"Cookie": cookie} if cookie else {})})
        r = conn.getresponse()
        return r.status, r.getheader("Set-Cookie"), r.read()

    try:
        assert get("/")[0] == 401 and get("/api/home")[0] == 401 and get("/static/app.js")[0] == 401
        assert get("/?k=wrong")[0] == 401
        status, cookie, _ = get("/?k=s3cret-token")
        assert status == 303 and "orbit_k=s3cret-token" in cookie and "HttpOnly" in cookie and "SameSite=Strict" in cookie
        assert get("/api/home", "orbit_k=s3cret-token")[0] == 200
        assert get("/", "orbit_k=nope")[0] == 401
    finally:
        srv.shutdown()


def test_guessing_the_token_is_slowed_down(tmp_path, monkeypatch):
    import http.client
    import threading
    from http.server import ThreadingHTTPServer

    from orbit import web

    srv = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(web.State(token="x" * 20)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    try:
        codes = []
        for _ in range(14):
            conn = http.client.HTTPConnection("127.0.0.1", port)
            conn.request("GET", "/api/home", headers={"Host": f"127.0.0.1:{port}"})
            codes.append(conn.getresponse().status)
        assert codes[0] == 401 and codes[-1] == 429
    finally:
        srv.shutdown()


def test_settings_round_trip_and_history_and_unknown_routes(server):
    status, body, _ = call(server, "GET", "/api/settings")
    assert status == 200 and json.loads(body)["currency"]
    assert post(server, "/api/settings", {"currency": "usd", "model": "ministral-3:3b"})[0] == 200
    assert json.loads(call(server, "GET", "/api/settings")[1])["main_currency"] == "USD"
    assert json.loads(call(server, "GET", "/api/history")[1])["history"] == []
    assert call(server, "GET", "/api/nothing")[0] == 404
    assert post(server, "/api/nothing", {})[0] == 404
    assert call(server, "GET", "/no-such-page")[0] == 404


def test_a_tool_error_is_reported_not_crashed_and_bad_bodies_are_ignored(server):
    status, body, _ = post(server, "/api/tool", {"name": "no_such_tool"})
    assert status == 400 and not json.loads(body)["ok"]
    status, body, _ = post(server, "/api/tool", {"name": "add_transaction", "args": {"amount": "not a number"}})
    assert status == 200 and not json.loads(body)["ok"]  # the tool's own error comes back as data
    conn = http.client.HTTPConnection("127.0.0.1", server, timeout=10)
    conn.request("POST", "/api/tool", "{not json", {"Host": f"127.0.0.1:{server}", "X-Orbit": "1", "Content-Type": "application/json", "Content-Length": "9"})
    assert conn.getresponse().status == 400  # an unreadable body is an empty request: no tool name


def test_an_empty_chat_message_is_refused_and_reset_clears_history(server):
    assert post(server, "/api/chat", {"text": "   "})[0] == 400
    assert post(server, "/api/chat/reset", {})[0] == 200


def test_import_runs_in_the_background_and_reports_its_state(server, monkeypatch):
    from orbit import web as w

    monkeypatch.setenv("ORBIT_PARSED", "/nonexistent")
    started = json.loads(post(server, "/api/import", {})[1])
    assert started["ok"]
    for _ in range(50):
        state = json.loads(call(server, "GET", "/api/import")[1])
        if not state["running"]:
            break
        import time

        time.sleep(0.1)
    assert not state["running"] and (state["error"] or state["result"] is not None)
    assert w.parsed_dir().name == "nonexistent"


def test_notes_import_says_plainly_when_the_folder_is_missing(server, monkeypatch, tmp_path):
    monkeypatch.setenv("ORBIT_INBOX", str(tmp_path / "missing"))
    status, body, _ = post(server, "/api/notes/import", {})
    assert status == 404 and "export-notes" in json.loads(body)["error"]
    assert json.loads(post(server, "/api/notes/tag", {})[1])["ok"]
