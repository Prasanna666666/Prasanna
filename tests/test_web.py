"""Lumo's web app: real server, real files, scripted agent."""

import json
import urllib.error
import urllib.request

import pytest
from web_fixture import make_ctx, start_server


@pytest.fixture
def app(tmp_path):
    ctx, agent, ids = make_ctx(tmp_path)
    web, server = start_server(ctx)
    yield SimpleApp(web, server, agent, ids)
    server.shutdown()


class SimpleApp:
    def __init__(self, web, server, agent, ids):
        self.web, self.server, self.agent, self.ids = web, server, agent, ids
        self.base = f"http://127.0.0.1:{server.server_port}"

    def get(self, path, token=True, host=None, origin=None):
        req = urllib.request.Request(self.base + path, headers={"X-Lumo-Token": self.web.token} if token else {})
        if host:
            req.add_header("Host", host)
        if origin:
            req.add_header("Origin", origin)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def chat(self, message, conv="c1", history=None, token=True):
        body = json.dumps({"message": message, "conv": conv, "history": history or []}).encode()
        req = urllib.request.Request(self.base + "/api/chat", body, {"Content-Type": "application/json", **({"X-Lumo-Token": self.web.token} if token else {})})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, parse_sse(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, []


def parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        name, data = "message", ""
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data += line[5:].strip()
        events.append((name, json.loads(data) if data else {}))
    return events


def test_page_loads_with_the_token_and_strict_security_headers(app):
    status, body, headers = app.get("/", token=False)
    html = body.decode()
    assert status == 200 and app.web.token in html and "__TOKEN__" not in html
    assert "default-src 'none'" in headers["Content-Security-Policy"] and "script-src 'self'" in headers["Content-Security-Policy"]
    assert headers["X-Content-Type-Options"] == "nosniff" and headers["Cache-Control"] == "no-store"
    assert "onclick" not in html and "<style" not in html and "https://" not in html  # nothing inline, nothing external
    assert app.get("/static/app.js", token=False)[0] == 200 and app.get("/static/app.css", token=False)[0] == 200
    assert app.get("/static/../server.py", token=False)[0] == 404


def test_api_needs_the_token_and_the_right_host_and_origin(app):
    assert app.get("/api/status", token=False)[0] == 403
    assert app.get("/api/status")[0] == 200
    assert app.get("/api/status", host="evil.example.com")[0] == 403  # DNS rebinding
    assert app.get("/api/status", origin="http://evil.example.com")[0] == 403  # another website
    assert app.get("/api/status", host=f"localhost:{app.web.port}")[0] == 200
    assert app.chat("hello", token=False)[0] == 403
    assert app.get(f"/api/photo/1/thumb?t={app.web.token}", token=False)[0] == 200  # images carry the token in the address


def test_status_reports_the_state_and_counts(app):
    import time

    first = json.loads(app.get("/api/status")[1])  # counts are gathered in the background, never while a request waits
    assert first["ai"] is True and first["search_ready"] is True and first["indexing"] is False
    assert first["brain"] == "classic" and first["warm_problem"] == ""  # the page can say which brain answers and why it is not ready
    for _ in range(40):
        d = json.loads(app.get("/api/status")[1])
        if d["photos"] == 70:
            break
        time.sleep(0.05)
    assert d["photos"] == 70 and d["indexed"] == 70
    assert json.loads(app.get("/api/suggestions")[1])["ideas"]


def test_photos_are_served_by_number_only(app):
    status, body, headers = app.get("/api/photo/5/thumb")
    assert status == 200 and headers["Content-Type"] == "image/jpeg" and body[:2] == b"\xff\xd8" and "max-age" in headers["Cache-Control"]
    assert app.get("/api/photo/5/preview")[0] == 200
    assert app.get("/api/photo/999/thumb")[0] == 404
    for bad in ("/api/photo/../../etc/passwd/thumb", "/api/photo/5/original", "/api/photo/abc/thumb", "/api/photo/5/thumb/../../x"):
        assert app.get(bad)[0] == 404


def test_item_details_hide_the_folder_path(app):
    d = json.loads(app.get("/api/item/3")[1])
    assert d["name"] == "IMG_0003.jpg" and d["camera"] == "iPhone 15 Pro" and "/photos" not in json.dumps(d) and "Trips" not in json.dumps(d)
    assert app.get("/api/item/9999")[0] == 404


def test_photo_question_streams_ack_reply_results_done_and_remembers_the_set(app):
    status, events = app.chat("beach photos", conv="a")
    names = [n for n, _ in events]
    assert status == 200 and names[0] == "ack" and names[-1] == "done" and "reply" in names and "results" in names
    results = dict(events)["results"]
    assert results["total"] == 41 and len(results["ids"]) == 41 and results["notes"] == ["3 photos have no GPS, so the place could not be checked."]
    assert dict(events)["done"]["kind"] == "results"
    # the next message in the same conversation gets the earlier result set; another conversation does not
    app.chat("only the ones from March", conv="a")
    app.chat("only the ones from March", conv="b")
    assert len(app.agent.asked[1][1]) == 41 and app.agent.asked[2][1] is None


def test_results_are_paged(app):
    app.chat("all photos", conv="p")
    events = dict(app.chat("all photos", conv="p")[1])
    assert events["results"]["total"] == 70 and len(events["results"]["ids"]) == 60
    page = json.loads(app.get("/api/results?conv=p&offset=60")[1])
    assert page["total"] == 70 and len(page["ids"]) == 10 and page["ids"][0] == 61
    assert json.loads(app.get("/api/results?conv=unknown&offset=0")[1]) == {"ids": [], "total": 0}


def test_conversation_streams_word_by_word_without_photos(app):
    status, events = app.chat("tell me about RAW", history=[["user", "hi"], ["assistant", "Hello!"]])
    deltas = [d["text"] for n, d in events if n == "delta"]
    assert len(deltas) >= 5 and "".join(deltas).startswith("Sure, happy to help.")
    assert not any(n in ("results", "preview") for n, _ in events) and events[-1][1]["text"].endswith("sensor data.")
    assert app.agent.asked[-1][2] == [("user", "hi"), ("assistant", "Hello!")]


def test_errors_reach_the_page_as_a_message_not_a_crash(app):
    status, events = app.chat("boom")
    assert status == 200 and events[-1] == ("error", {"message": "Ollama is not reachable"})
    assert app.chat("still alive")[0] == 200  # the server survived


def test_bad_requests_are_rejected(app):
    base = app.base
    for body, expected in ((b"not json", 400), (b"{}", 400), (json.dumps({"message": "   "}).encode(), 400), (b"x" * 70_000, 413)):
        req = urllib.request.Request(base + "/api/chat", body, {"Content-Type": "application/json", "X-Lumo-Token": app.web.token})
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req)
        assert err.value.code == expected
