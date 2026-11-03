"""Replies appear piece by piece (first words in about a second) and photo matches can appear instantly."""

import inspect
import json
import urllib.error
import urllib.request
from datetime import date

import pytest

from aperture.agent.llm import LLMError, LLMUnavailable, OllamaClient
from aperture.agent.planner import PlanResult
from aperture.agent.schema import Plan
from aperture.agent.service import AgentService
from aperture.config import Paths, Settings


class FakeResponse:
    def __init__(self, lines):
        self.lines = lines

    def __iter__(self):
        return iter(self.lines)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def ndjson(*chunks):
    return [json.dumps(c).encode() + b"\n" for c in chunks]


def client():
    return OllamaClient("http://127.0.0.1:11434", "ministral-3:3b")


def test_stream_chat_yields_pieces_and_stops_at_done(monkeypatch):
    sent = {}

    def fake_urlopen(req, timeout=None):
        sent["body"] = json.loads(req.data)
        return FakeResponse(ndjson({"message": {"content": "Hel"}}, {"message": {"content": "lo!"}}, {"message": {"content": ""}, "done": True},
                                   {"message": {"content": "NEVER SEEN"}}))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert list(client().stream_chat("sys", [{"role": "user", "content": "hi"}])) == ["Hel", "lo!"]
    b = sent["body"]
    assert b["stream"] is True and b["options"]["num_ctx"] == 4096 and b["messages"][0]["role"] == "system"


@pytest.mark.parametrize("error,expected", [
    (urllib.error.HTTPError("u", 404, "nf", {}, None), (LLMError, "not installed")),
    (urllib.error.URLError("refused"), (LLMUnavailable, "not reachable")),
])
def test_stream_chat_errors_are_friendly(monkeypatch, error, expected):
    def boom(req, timeout=None):
        raise error

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(expected[0], match=expected[1]):
        list(client().stream_chat("s", []))


def test_unreadable_stream_is_reported(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResponse([b"not json\n"]))
    with pytest.raises(LLMError, match="unreadable"):
        list(client().stream_chat("s", []))


class FakePlanner:
    def plan(self, request, ctx):
        return PlanResult(plan=Plan(intent="chat"))


def test_chat_reply_carries_a_stream_and_never_runs_a_search():
    def boom():
        raise AssertionError("no photo search for a chat message")

    seen = {}

    def chat_stream(request, history):
        seen.update(request=request, history=history)
        yield from ["Sure", ", ", "happy to help."]

    svc = AgentService(FakePlanner(), boom, lambda: [], today=lambda: date(2026, 11, 3), chat_stream=chat_stream)
    reply = svc.ask("tell me about RAW", history=[("user", "hi")])
    assert reply.kind == "chat" and reply.text == "" and len(reply.ids) == 0
    assert "".join(reply.stream) == "Sure, happy to help." and seen["history"] == [("user", "hi")]


def test_instant_word_matches_are_off_by_default_and_the_old_choice_resets_once(tmp_path):
    paths = Paths(tmp_path)
    assert Settings().quick_preview is False and Settings().brain == "classic" and Settings().rescue_search is False
    paths.settings_file.parent.mkdir(parents=True, exist_ok=True)
    paths.settings_file.write_text(json.dumps({"schema": 7, "quick_preview": True, "brain": "tools", "rescue_search": True}))
    s = Settings.load(paths)
    assert (s.quick_preview, s.brain, s.rescue_search) == (False, "classic", False)  # reset once by the v8 migration
    paths.settings_file.write_text(json.dumps({"schema": 8, "quick_preview": True, "brain": "tools"}))
    s = Settings.load(paths)
    assert s.quick_preview is True and s.brain == "tools"  # a deliberate choice made after v8 is kept


def test_chat_view_shows_the_message_at_once_and_streams_the_reply():
    from aperture.ui.views import chat

    src = inspect.getsource(chat.render)
    assert "_render_message(ctx, len(history) - 1, history[-1])" in src
    assert "st.write_stream(reply.stream)" in src and "if ctx.settings.quick_preview:" in src


def test_settings_page_has_the_instant_matches_switch():
    from aperture.ui.views import settings

    src = inspect.getsource(settings)
    assert "quick_preview" in src and "Show instant photo matches" in src


def test_the_real_agent_streams_through_the_model(tmp_path, monkeypatch):
    from aperture.bootstrap import AppContext

    monkeypatch.setenv("APERTURE_ALLOW_INTERNAL", "1")
    paths = Paths(tmp_path / "Expansion")
    paths.ensure()
    ctx = AppContext(paths)
    ctx.settings.brain = "classic"
    agent = ctx.agent()
    assert agent._chat_stream is not None
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResponse(
        ndjson({"message": {"content": "Hi"}}, {"message": {"content": " there"}, "done": True})))
    assert "".join(agent._chat_stream("hello", [("user", "x"), ("assistant", "y")])) == "Hi there"
