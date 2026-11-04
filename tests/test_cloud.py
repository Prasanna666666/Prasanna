"""The cloud option: names never leave the Mac, the gateway is strict, and a spending cap holds."""

import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from aperture.cloud import gateway as gw
from aperture.cloud.redact import Redactor


def test_names_from_the_library_are_swapped_for_placeholders_and_restored():
    r = Redactor(["Anna", "Maya Rao"], ["Nagoya", "New York", "York"])
    sent = r.redact("photos of anna and Maya Rao in Nagoya or New York, not York Minster")
    assert "Anna" not in sent.lower().replace("<person", "") and "nagoya" not in sent.lower() and "maya" not in sent.lower()
    assert sent.count("<PERSON_") == 2 and "<PLACE_1>" in sent
    plan = {"people": ["<PERSON_1>", "<PERSON_2>"], "places": ["<PLACE_1>", "<PLACE_2>"], "what": "temple"}
    back = r.restore(plan)
    assert back["people"] == ["anna", "Maya Rao"] and back["places"][0] == "Nagoya" and back["what"] == "temple"  # as typed, not as stored


def test_a_name_inside_another_word_is_left_alone():
    r = Redactor(["Ann"], ["Rome"])
    assert r.redact("a romeo and annual report") == "a romeo and annual report"


class Provider:
    """A fake provider over real HTTP that records exactly what it was sent."""

    def __init__(self, text, tokens=(100, 20)):
        self.seen, self.text, self.tokens = [], text, tokens
        owner = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.seen.append((dict(self.headers), body))
                data = json.dumps({"content": [{"type": "text", "text": owner.text}], "usage": {"input_tokens": owner.tokens[0], "output_tokens": owner.tokens[1]}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1/messages"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()


@pytest.fixture()
def provider():
    p = Provider('{"tool": "find_photos", "arguments": {"places": ["<PLACE_1>"], "what": "hockey stadium", "evil": "x", "year": "bad"}}')
    yield p
    p.stop()


def _gateway(tmp_path, provider, cap=5.0):
    return gw.Gateway("sk-test-key", gw.Usage(tmp_path / "usage.json"), cap_usd=cap, provider_url=provider.url)


def test_only_the_redacted_question_reaches_the_provider_and_the_plan_is_checked(tmp_path, provider):
    g = _gateway(tmp_path, provider)
    plan = g.interpret("<PLACE_1> hockey stadium", False, "2026-11-04")
    assert plan == {"tool": "find_photos", "arguments": {"places": ["<PLACE_1>"], "what": "hockey stadium"}}  # unknown and malformed fields are dropped
    headers, body = provider.seen[0]
    sent = json.dumps(body)
    assert "<PLACE_1> hockey stadium" in sent and "Nagoya" not in sent  # the placeholder is all the provider ever sees
    assert set(body) == {"model", "max_tokens", "temperature", "system", "messages"} and len(body["messages"]) == 1
    assert {k.lower(): v for k, v in headers.items()}["x-api-key"] == "sk-test-key" and "sk-test-key" not in sent  # the key is a header, never part of the content


def test_a_plan_with_an_unknown_tool_or_no_tool_is_refused():
    assert gw.clean_plan({"tool": "delete_everything", "arguments": {}}) is None
    assert gw.clean_plan({"tool": "none"}) is None and gw.clean_plan("find photos") is None
    assert gw.clean_plan({"tool": "find_photos", "arguments": {"folder": "x", "date_from": "2026-13-45", "date_to": "2026-10-31"}}) == \
        {"tool": "find_photos", "arguments": {"date_to": "2026-10-31"}}  # a folder only makes sense when copying; a bad date is dropped


def test_the_monthly_cap_stops_spending(tmp_path):
    p = Provider('{"tool": "find_photos", "arguments": {"what": "dog"}}', tokens=(1_000_000, 0))  # one call costs $1 at the default prices
    try:
        g = gw.Gateway("k", gw.Usage(tmp_path / "usage.json"), cap_usd=1.5, provider_url=p.url)
        assert g.interpret("dogs", False, "2026-11-04") is not None and g.status()["spent_usd"] == 1.0
        assert g.interpret("dogs", False, "2026-11-04") is not None  # $1.00 spent, still under the $1.50 cap
        with pytest.raises(gw.GatewayError, match="cap"):
            g.interpret("dogs", False, "2026-11-04")  # $2.00 spent: stopped, and nothing more was sent
        assert len(p.seen) == 2
    finally:
        p.stop()


def test_an_unreachable_provider_never_leaks_details_and_the_http_gateway_serves_only_its_own_host(tmp_path, provider):
    g = _gateway(tmp_path, provider)
    server = gw.ThreadingHTTPServer(("127.0.0.1", 0), gw.make_handler(g, 0))
    port = server.server_port
    server.RequestHandlerClass = gw.make_handler(g, port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        def call(path, data=None, host=None):
            req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(data).encode() if data is not None else None)
            req.add_header("Host", host or f"127.0.0.1:{port}")
            try:
                with urllib.request.urlopen(req) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())

        status, body = call("/interpret", {"question": "<PLACE_1> hockey stadium", "has_previous": False})
        assert status == 200 and body["plan"]["tool"] == "find_photos"
        assert call("/interpret", {"question": "x"}, host="evil.example.com")[0] == 404  # DNS-rebinding style access is refused
        assert call("/status")[1]["cap_usd"] == 5.0
        g._url = "http://127.0.0.1:9/v1/messages"  # nothing listens there
        status, body = call("/interpret", {"question": "dogs"})
        assert status == 503 and "sk-test-key" not in json.dumps(body) and "could not be reached" in body["error"]
    finally:
        server.shutdown()
