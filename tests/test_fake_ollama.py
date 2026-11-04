"""The real client classes talk to a fake Ollama over real HTTP: no stand-in objects, so a missing method or a wrong request shape fails here,
not on the user's Mac."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from PIL import Image

from aperture.agent.llm import OllamaClient, OllamaVision
from aperture.config import preview_rel


class FakeOllama:
    """Answers /api/chat the way Ollama does: JSON when stream is false, newline-delimited JSON when it is true."""

    def __init__(self):
        self.requests = []
        self.answers = {"vision": '{"sports_venue": true, "sport": "hockey", "venue_type": "arena", "evidence": "goals and boards"}',
                        "decide": '{"tool": "find_photos", "arguments": {"places": ["Nagoya"], "what": "stadium"}}'}

        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.requests.append((self.path, body))
                has_image = any(m.get("images") for m in body["messages"])
                content = owner.answers["vision" if has_image else "decide"]
                final = {"message": {"role": "assistant", "content": content}, "done": True, "prompt_eval_count": 10, "eval_count": 5}
                if body.get("stream"):
                    data = (json.dumps({"message": {"content": content[:15]}}) + "\n" + json.dumps({**final, "message": {"content": content[15:]}}) + "\n").encode()
                else:
                    data = json.dumps(final).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()


@pytest.fixture()
def ollama(monkeypatch):
    monkeypatch.setenv("APERTURE_ALLOW_INTERNAL", "1")
    server = FakeOllama()
    yield server
    server.stop()


def _library(tmp_path):
    import sqlite3

    from aperture.db import MIGRATIONS

    conn = sqlite3.connect(":memory:")
    for s in MIGRATIONS:
        conn.executescript(s)
    for i in (1, 2):
        conn.execute("INSERT INTO items(id, path, rel_path, kind, mtime, size, meta_done) VALUES (?,?,?,?,?,?,1)", (i, f"/p/{i}", f"{i}", "image", 0, 0))
        path = tmp_path / preview_rel(i)
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (80, 60), (30, 30, 30)).save(path, "JPEG")
    conn.execute("INSERT INTO photo_labels VALUES (1, 'stadium', 0.9, 'vision')")
    return conn


def test_the_venue_pass_runs_end_to_end_through_the_real_vision_client(ollama, tmp_path):
    from aperture.indexing import venues

    conn = _library(tmp_path)
    out = venues.run(conn, tmp_path, OllamaVision(ollama.url, "ministral-3:3b"))
    assert out["looked_at"] == 1 and out["failed"] == 0 and out["error"] == "" and out["sports_venues"] == 1
    path, body = ollama.requests[0]
    assert path == "/api/chat" and body["stream"] is False and body["format"] == venues.SCHEMA and len(body["messages"][0]["images"]) == 1
    assert {r[0] for r in conn.execute("SELECT label FROM photo_labels WHERE source='venue'")} >= {"hockey arena", "hockey"}


def test_the_vision_judge_runs_end_to_end_through_the_real_vision_client(ollama, tmp_path):
    from aperture.indexing import judge

    ollama.answers["vision"] = json.dumps({"caption": "an arena", "scene": "arena", "objects": ["goal"], "place": {"city": "", "country": "", "evidence": "", "sure": False}})
    conn = _library(tmp_path)
    data = judge.analyse(OllamaVision(ollama.url, "ministral-3:3b"), (tmp_path / preview_rel(1)).read_bytes())
    assert data["caption"] == "an arena" and ollama.requests[0][1]["format"] == judge.SCHEMA
    out = judge.run(conn, tmp_path, OllamaVision(ollama.url, "ministral-3:3b"), None)
    assert out["failed"] == 0 and out["error"] == "" and out["analysed"] == 2


def test_the_chat_decision_runs_end_to_end_through_the_real_client_and_agent(ollama, tmp_path):
    from datetime import date
    from types import SimpleNamespace

    import numpy as np

    from aperture.agent.service import AgentService
    from aperture.agent.toolagent import ToolAgent

    seen = []

    def make_executor():
        def run(plan, previous):
            seen.append(plan)
            return SimpleNamespace(ids=np.array([5, 6]), reports=[], notes=[], date_range="")
        return SimpleNamespace(run=run)

    service = AgentService(planner=None, executor_factory=make_executor, known_people=lambda: [], rescue=False)
    agent = ToolAgent(OllamaClient(ollama.url, "ministral-3:3b"), service, lambda r: "", today=lambda: date(2026, 11, 4))
    reply = agent.ask("Nagoya stadium pictures")
    assert list(reply.ids) == [5, 6] and {c.query for c in seen[0].clauses} == {"Nagoya", "stadium"}
    path, body = ollama.requests[0]
    assert path == "/api/chat" and "tools" not in body and body["format"]["properties"]["tool"]["enum"][0] == "find_photos"
    assert len(body["messages"][0]["content"]) < 6500  # the prompt the model really receives stays small
