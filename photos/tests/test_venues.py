"""The vision model reads photos that look like a sports venue once; the answer becomes searchable labels like 'hockey stadium'."""

import json
import sqlite3

from PIL import Image

from aperture.config import preview_rel
from aperture.db import MIGRATIONS
from aperture.indexing import venues


class Vision:
    def __init__(self, answers):
        self.answers, self.calls = answers, 0

    def extract(self, image, prompt, schema, max_tokens=700):
        self.calls += 1
        return json.dumps(self.answers.pop(0))


def _db(tmp_path, n=4):
    conn = sqlite3.connect(":memory:")
    for s in MIGRATIONS:
        conn.executescript(s)
    for i in range(1, n + 1):
        conn.execute(
            "INSERT INTO items(id, path, rel_path, kind, mtime, size, meta_done) VALUES (?,?,?,?,?,?,1)",
            (i, f"/p/{i}", f"{i}", "image", 0, 0),
        )
        path = tmp_path / preview_rel(i)
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (40, 30), (10, 10, 10)).save(path, "JPEG")
    return conn


def test_only_photos_that_already_look_like_a_venue_are_looked_at_and_never_twice(tmp_path):
    conn = _db(tmp_path)
    for item, label, score in (
        (1, "stadium", 0.9),
        (2, "ice rink", 0.7),
        (3, "dog", 0.9),
        (4, "arena", 0.3),
    ):  # photo 4 is too uncertain
        conn.execute("INSERT INTO photo_labels VALUES (?,?,?,'vision')", (item, label, score))
    assert venues.candidates(conn) == [1, 2]  # most likely first; the dog and the doubtful one are never sent to the slow model
    vision = Vision(
        [
            {"sports_venue": True, "sport": "Hockey", "venue_type": "rink", "evidence": "boards, blue lines and goals"},
            {"sports_venue": False, "sport": "unknown", "venue_type": "other", "evidence": "a shopping mall"},
        ]
    )
    out = venues.run(conn, tmp_path, vision)
    assert out == {"looked_at": 2, "sports_venues": 1, "failed": 0, "left": 0, "error": ""} and vision.calls == 2
    assert venues.candidates(conn) == []  # read once, kept for good
    labels = {r[0] for r in conn.execute("SELECT label FROM photo_labels WHERE item_id=1 AND source='venue'")}
    assert labels == {"sports venue", "rink", "hockey", "hockey rink"}
    assert not conn.execute(
        "SELECT 1 FROM photo_labels WHERE item_id=2 AND source='venue'"
    ).fetchone()  # not a venue: nothing is made up


def test_an_answer_without_evidence_or_without_a_known_sport_is_not_over_claimed():
    assert venues.labels_of({"sports_venue": True, "sport": "hockey", "venue_type": "arena", "evidence": ""}) == []
    assert venues.labels_of(
        {"sports_venue": True, "sport": "unknown", "venue_type": "stadium", "evidence": "tiered seating"}
    ) == ["sports venue", "stadium"]


def test_the_sport_labels_make_hockey_stadium_an_instant_exact_lookup(tmp_path):
    from aperture.agent.executor import Executor

    conn = _db(tmp_path, 2)
    conn.row_factory = sqlite3.Row
    conn.execute("INSERT INTO photo_labels VALUES (1, 'stadium', 0.9, 'vision')")
    venues.run(
        conn,
        tmp_path,
        Vision([{"sports_venue": True, "sport": "hockey", "venue_type": "stadium", "evidence": "hockey nets and ice"}]),
    )
    assert Executor(conn, lambda: None, lambda: None)._tag_ids("hockey stadium").tolist() == [1]


def test_a_failure_is_reported_with_its_reason_not_swallowed(tmp_path):
    conn = _db(tmp_path, 2)
    conn.execute("INSERT INTO photo_labels VALUES (1, 'stadium', 0.9, 'vision')")

    class Broken:
        def extract(self, *args, **kwargs):
            raise RuntimeError("Ollama returned HTTP 500: model requires more system memory")

    out = venues.run(conn, tmp_path, Broken())
    assert out["failed"] == 1 and out["looked_at"] == 0 and "requires more system memory" in out["error"]


def test_a_little_text_around_the_models_json_is_tolerated(tmp_path):
    conn = _db(tmp_path, 1)
    conn.execute("INSERT INTO photo_labels VALUES (1, 'arena', 0.9, 'vision')")

    class Chatty:
        def extract(self, *args, **kwargs):
            return 'Sure! {"sports_venue": true, "sport": "hockey", "venue_type": "arena", "evidence": "nets"} Hope that helps.'

    assert venues.run(conn, tmp_path, Chatty())["sports_venues"] == 1


def test_the_real_vision_client_asks_ollama_for_a_constrained_answer_about_one_picture(monkeypatch):
    """The stand-in model above hides a missing method: this uses the real OllamaVision class."""
    from aperture.agent.llm import OllamaVision

    sent = {}

    def fake_request(self, path, payload=None):
        sent["path"], sent["payload"] = path, payload
        return {"message": {"content": '{"sports_venue": true}'}}

    monkeypatch.setattr(OllamaVision, "_request", fake_request)
    client = OllamaVision("http://127.0.0.1:11434", "ministral-3:3b")
    assert client.extract(b"jpegbytes", "look", venues.SCHEMA, 500) == '{"sports_venue": true}'
    message = sent["payload"]["messages"][0]
    assert sent["path"] == "/api/chat" and sent["payload"]["format"] == venues.SCHEMA and sent["payload"]["stream"] is False
    assert message["content"] == "look" and len(message["images"]) == 1  # one picture, as base64
