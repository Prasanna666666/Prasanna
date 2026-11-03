"""Fast routing: greetings answer instantly; a tiny router sends photo questions to the planner and the rest to conversation."""

import json
import urllib.request
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from aperture.agent import llm as llm_mod
from aperture.agent.llm import LLMError, OllamaClient
from aperture.agent.planner import PlanResult
from aperture.agent.schema import Clause, Plan
from aperture.agent.service import ROUTER_SCHEMA, AgentService, instant_reply
from aperture.evaluation import evaluate_routes


@pytest.mark.parametrize("text,expected", [
    ("hello", True), ("Hi!", True), ("hey there", True), ("Thanks!", True), ("thank you so much", True), ("bye", True),
    ("good morning", True),
    ("hello, how many pics in 2026", False), ("how many pics in 2026", False), ("hi anna photos", False), ("thanks for the beach photos", False),
])
def test_instant_replies_only_for_plain_greetings(text, expected):
    assert (instant_reply(text) is not None) is expected


class Planner:
    def __init__(self):
        self.calls = 0

    def plan(self, request, ctx):
        self.calls += 1
        return PlanResult(plan=Plan(intent="count", clauses=()))


def service(router, planner=None, executor_called=None, **kw):
    def make_executor():
        raise RuntimeError("executor reached")

    return AgentService(planner or Planner(), make_executor, lambda: [], today=lambda: date(2026, 11, 3), router=router, **kw)


def test_greeting_never_calls_the_router_or_the_planner():
    def router(request, has_previous):
        raise AssertionError("no AI call for a plain greeting")

    planner = Planner()
    reply = service(router, planner).ask("hello")
    assert reply.kind == "chat" and "Lumo" in reply.text and planner.calls == 0


def test_chat_route_skips_the_planner_and_streams():
    planner = Planner()
    reply = service(lambda r, p: "chat", planner, chat_stream=lambda req, hist: iter(["Sure", "!"])).ask("tell me a joke")
    assert planner.calls == 0 and reply.kind == "chat" and "".join(reply.stream) == "Sure!"


def test_photos_route_goes_to_the_planner():
    planner = Planner()
    seen = []
    svc = service(lambda r, p: seen.append((r, p)) or "photos", planner, chat_stream=lambda *a: iter(["WRONG"]))
    try:
        svc.ask("How many pics in 2026", previous_ids=None)
    except RuntimeError as exc:  # the stub executor is reached only after planning
        assert "executor reached" in str(exc)
    assert planner.calls == 1 and seen == [("How many pics in 2026", False)]


def test_router_tells_whether_earlier_results_exist():
    import numpy as np

    seen = []
    svc = service(lambda r, p: seen.append(p) or "chat", chat_stream=lambda *a: iter(["x"]))
    svc.ask("only the ones from March", previous_ids=np.array([1, 2, 3]))
    assert seen == [True]


def test_router_errors_are_reported():
    def router(request, has_previous):
        raise LLMError("Ollama is not reachable")

    reply = service(router).ask("show me dogs")
    assert reply.kind == "error" and "not reachable" in reply.text


def _context(tmp_path, monkeypatch):
    from aperture.bootstrap import AppContext
    from aperture.config import Paths

    monkeypatch.setenv("APERTURE_ALLOW_INTERNAL", "1")
    paths = Paths(tmp_path / "Expansion")
    paths.ensure()
    return AppContext(paths)


@pytest.mark.parametrize("reply,expected", [('{"route": "chat"}', "chat"), ('{"route": "photos"}', "photos"),
                                            ("not json at all", "photos"), ('{"route": "banana"}', "photos"), ("{}", "photos")])
def test_router_defaults_to_photos_when_unsure(tmp_path, monkeypatch, reply, expected):
    sent = []
    monkeypatch.setattr(OllamaClient, "_request", lambda self, path, payload=None: sent.append(payload) or {"message": {"content": reply}})
    route = _context(tmp_path, monkeypatch).router()
    assert route("whatever", False) == expected
    p = sent[0]
    assert p["format"] == ROUTER_SCHEMA and p["options"]["num_predict"] == 16 and p["options"]["num_ctx"] == llm_mod.NUM_CTX
    assert "Message: whatever" in p["messages"][1]["content"] and "EARLIER RESULTS: no" in p["messages"][1]["content"]


def test_chat_replies_know_todays_date(tmp_path, monkeypatch):
    bodies = []

    class Resp:
        def __iter__(self):
            return iter([json.dumps({"message": {"content": "ok"}, "done": True}).encode() + b"\n"])

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: bodies.append(json.loads(req.data)) or Resp())
    agent = _context(tmp_path, monkeypatch).agent()
    assert "".join(agent._chat_stream("what day is it?", [])) == "ok"
    system = bodies[0]["messages"][0]["content"]
    assert "Today's date is" in system and str(date.today().year) in system


def test_route_cases_file_is_valid_and_includes_the_real_failure():
    cases = json.loads((Path(llm_mod.__file__).parents[1] / "eval_data" / "route_cases.json").read_text())
    assert len(cases) >= 30 and {c["expect"] for c in cases} == {"photos", "chat"}
    assert {"message": "How many pics in 2026", "previous": False, "expect": "photos"} in cases


def test_evaluate_routes_counts_and_explains_mistakes():
    cases = [{"message": "a", "previous": False, "expect": "photos"}, {"message": "b", "previous": True, "expect": "chat"}]
    correct, wrong = evaluate_routes(lambda m, prev: "photos", cases)
    assert correct == 1 and wrong == ["'b': sent to photos, expected chat"]


def test_indexing_unloads_the_ai_model_first(monkeypatch):
    from aperture.ui import state

    events = []
    ctx = SimpleNamespace(paths=SimpleNamespace(scan_pid="x"), llm=lambda: SimpleNamespace(unload=lambda: events.append("unload")))
    monkeypatch.setattr(state.ScanLock, "running", lambda self: False)
    monkeypatch.setattr(state.subprocess, "Popen", lambda *a, **k: events.append("scan"))
    assert state.start_scan(ctx) is True and events == ["unload", "scan"]


def test_unload_sends_keep_alive_zero(monkeypatch):
    sent = []
    monkeypatch.setattr(OllamaClient, "_request", lambda self, path, payload=None: sent.append((path, payload)) or {})
    OllamaClient("http://127.0.0.1:11434", "ministral-3:3b").unload()
    assert sent == [("/api/generate", {"model": "ministral-3:3b", "prompt": "", "keep_alive": 0, "stream": False})]
    assert Clause  # imported for readability of the plan stubs above


def test_router_prompt_treats_short_things_and_find_requests_as_photo_searches():
    from aperture.agent.service import ROUTER_SYSTEM

    assert "single word naming something you could photograph" in ROUTER_SYSTEM and "any request to find or look for something" in ROUTER_SYSTEM
    cases = json.loads((Path(llm_mod.__file__).parents[1] / "eval_data" / "route_cases.json").read_text())
    eval_messages = {c["message"].lower() for c in cases}
    for example in ("mountains", "birthday cake", "find the invoice that mentions Acme"):
        assert f"'{example}' -> photos" in ROUTER_SYSTEM and example.lower() not in eval_messages  # teaches the principle, not the test
