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
    assert call(server, "POST", "/api/tool", {"name": "add_task", "args": {"title": "x"}}, headers={"X-Orbit": "1", "Origin": "http://evil.example.com"})[0] == 403
    assert call(server, "POST", "/api/tool", {"name": "add_task", "args": {"title": "x"}}, headers={"X-Orbit": "1", "Origin": f"http://127.0.0.1:{server}"})[0] == 200


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
    assert json.loads(call(server, "GET", "/api/settings")[1])["currency"] == "USD"
    home = json.loads(call(server, "GET", "/api/home")[1])
    assert home["ok"] and home["currency"] == "USD" and "briefing" in home


def test_chat_reports_a_missing_model_plainly(server, monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")  # nothing is listening
    status, body, _ = post(server, "/api/chat", {"text": "hello"})
    assert status == 502 and "Ollama" in json.loads(body)["error"]
