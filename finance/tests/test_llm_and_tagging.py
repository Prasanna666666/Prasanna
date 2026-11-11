import pytest
from kit import llm

from finance import tagging
from finance.modules import notes, people


def test_rule_tags_and_people(conn):
    people.add_person(conn, {"name": "Ramesh Kumar", "relation": "father"})
    notes.add_note(conn, {"body": "Ramesh BP tablet after breakfast, doctor visit Friday"})
    notes.add_note(conn, {"body": "random thought", "tags": "mine"})
    notes.add_note(conn, {"body": "zzz"})
    assert tagging.autotag_notes(conn) == 1
    got = {n["body"][:6]: n["tags"] for n in notes.search_notes(conn, {})}
    assert got["Ramesh"] == "family,health,ramesh"
    assert got["random"] == "mine"  # user tags are never overwritten


def test_model_tags_limited_to_vocabulary(conn):
    class M:
        def chat(self, model, messages, tools=None):
            return {"content": 'Sure! ["travel", "hacked", "ideas"]'}

    notes.add_note(conn, {"body": "zzz"})
    assert tagging.autotag_notes(conn, M(), "m") == 1
    assert notes.search_notes(conn, {})[0]["tags"] == "ideas,travel"


class FakeOllama(llm.OllamaClient):
    def __init__(self, names):
        self.names = names

    def installed(self):
        return self.names


def test_model_resolution_is_mistral_only():
    assert FakeOllama(["ministral-3:3b"]).resolve("ministral-3:3b") == "ministral-3:3b"
    assert FakeOllama(["ministral-3:3b-instruct-q4"]).resolve("ministral-3:3b") == "ministral-3:3b-instruct-q4"
    for other in (["llama3.2:3b"], ["qwen2.5:3b", "moondream"], []):  # never falls back to another model family
        with pytest.raises(RuntimeError, match="ollama pull ministral-3:3b"):
            FakeOllama(other).resolve("ministral-3:3b")
    with pytest.raises(RuntimeError, match="Several"):
        FakeOllama(["ministral-3:3b-a", "ministral-3:3b-b"]).resolve("ministral-3:3b")


def test_same_context_and_keepalive_in_every_part_so_one_loaded_model_is_shared(monkeypatch):
    """Ollama reloads a model when num_ctx changes; every part must send the same value (4096)."""
    seen = {}
    monkeypatch.setattr(llm.OllamaClient, "_call", lambda self, path, body=None, timeout=300: seen.update(body=body) or {"message": {}})
    llm.OllamaClient("http://127.0.0.1:11434").chat("ministral-3:3b", [], None)
    assert seen["body"]["options"]["num_ctx"] == 4096 and seen["body"]["keep_alive"] == llm.KEEP == "2m"


def test_the_client_refuses_to_start_a_call_after_the_deadline(monkeypatch):
    import time as _t

    c = llm.OllamaClient("http://127.0.0.1:11434")
    c.deadline = _t.monotonic() - 1
    with pytest.raises(llm.Slow):
        c._call("/api/chat", {})
