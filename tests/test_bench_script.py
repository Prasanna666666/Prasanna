"""The benchmark script runs on a Mac; here it is checked against a fake Ollama (no model, no macOS)."""

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "bench-models.py"
spec = importlib.util.spec_from_file_location("bench", SCRIPT)
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


class FakeOllama(BaseHTTPRequestHandler):
    loaded: set = set()

    def log_message(self, *a):
        pass

    def _send(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.do_POST()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/api/tags":
            return self._send({"models": [{"name": "fast:3b"}, {"name": "slow:3b"}]})
        if self.path == "/api/ps":
            return self._send({"models": [{"name": m, "size": 2_500_000_000} for m in self.loaded]})
        if self.path == "/api/generate":
            if body.get("keep_alive") == 0:
                self.loaded.discard(body["model"])
            else:
                self.loaded.add(body["model"])
            rate = 40 if body["model"] == "fast:3b" else 10
            return self._send({"eval_count": 80, "eval_duration": int(80 / rate * 1e9), "response": "x"})
        self._send({})


@pytest.fixture
def url():
    srv = HTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_benchmark_runs_and_picks_the_faster_model(url, capsys):
    assert bench.main(["fast:3b", "slow:3b", "missing:3b", "--url", url, "--no-plan"]) == 0
    out = capsys.readouterr().out
    assert "SKIPPED missing:3b" in out and "fast:3b" in out and "slow:3b" in out
    assert "Fastest: fast:3b (40.0 tok/s)" in out and "model MB" in out and "2500" in out


def test_verdict_flags_swapping_and_pressure():
    rows = [{"model": "a", "tok_s": 20, "peak_mb": 3000, "swap_mb": 900, "min_free": 8},
            {"model": "b", "tok_s": 15, "peak_mb": 2500, "swap_mb": 10, "min_free": 40}]
    v = bench.verdict(rows)
    assert "a: RISK of hanging the system: started swapping (+900 MB), memory free dropped to 8%" in v
    assert "b: stayed comfortable." in v and "Lightest on memory: b" in v


def test_unreachable_ollama_is_a_clear_message(capsys):
    assert bench.main(["x", "--url", "http://127.0.0.1:9"]) == 2
    assert "Open the Ollama app" in capsys.readouterr().out
