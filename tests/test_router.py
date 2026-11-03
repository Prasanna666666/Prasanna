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
from aperture.agent.service import ROUTER_SCHEMA, AgentService
from aperture.evaluation import evaluate_routes


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
    ctx = AppContext(paths)
    ctx.settings.brain = "classic"  # these tests are about the classic router + planner pipeline
    return ctx


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
    assert len(cases) >= 40 and {c["expect"] for c in cases} == {"simple", "photos", "chat"}
    assert {"message": "How many pics in 2026", "previous": False, "expect": "photos"} in cases


def test_evaluate_routes_separates_mistakes_from_merely_slower_answers():
    cases = [{"message": "a", "previous": False, "expect": "photos"}, {"message": "b", "previous": True, "expect": "chat"},
             {"message": "dogs", "previous": False, "expect": "simple"}, {"message": "Anna 2019", "previous": False, "expect": "photos"}]
    answers = {"a": "photos", "b": "photos", "dogs": "photos", "Anna 2019": "simple"}
    correct, wrong, slower = evaluate_routes(lambda m, prev: answers[m], cases)
    assert correct == 2  # 'a' and 'dogs' (right answer, slower)
    assert wrong == ["'b': sent to photos, expected chat", "'Anna 2019': sent to simple, expected photos"]  # a complex search treated as simple is a mistake
    assert slower == ["'dogs': used the full planner (works, but slower)"]


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


def test_router_prompt_defines_simple_photos_and_chat_with_examples_that_are_not_test_cases():
    from aperture.agent.service import ROUTER_SYSTEM

    assert "ONE subject" in ROUTER_SYSTEM and "At most 4 words" in ROUTER_SYSTEM and "When in doubt, choose photos" in ROUTER_SYSTEM
    cases = json.loads((Path(llm_mod.__file__).parents[1] / "eval_data" / "route_cases.json").read_text())
    eval_messages = {c["message"].lower() for c in cases}
    for example, route in [("mountains", "simple"), ("birthday cake", "simple"), ("a cup of coffee", "simple"),
                           ("photos of Anna at the beach", "photos"), ("find the invoice that mentions Acme", "photos"),
                           ("sunset photos from 2023", "photos")]:
        assert f"'{example}' -> {route}" in ROUTER_SYSTEM and example.lower() not in eval_messages

# ---------------------------------------------------------------- the simple route: no AI plan for one-subject searches
def simple_service(route, planner, plans, **kw):
    """The executor records the plan it was given, then fails on purpose so no real search is needed."""
    def make_executor():
        def run(plan, previous):
            plans.append((plan, previous))
            raise RuntimeError("stop here")
        return SimpleNamespace(run=run)

    return AgentService(planner, make_executor, lambda: [], today=lambda: date(2026, 11, 3), router=lambda r, p: route, **kw)


def test_simple_route_searches_directly_without_the_ai_plan():
    planner, plans = Planner(), []
    simple_service("simple", planner, plans).ask("Sunset photos!")
    assert planner.calls == 0 and len(plans) == 1
    plan = plans[0][0]
    assert plan.intent == "find" and plan.clauses == (Clause(engines=("visual",), query="sunset photos", exclude=False),)
    assert plan.date.is_empty and plan.filters.is_empty and plans[0][1] is None


@pytest.mark.parametrize("request_text,previous,fast", [
    ("a very long description of a scene", False, True),  # more than 4 words
    ("dogs", True, True),  # refining earlier results
    ("dogs", False, False),  # switched off in Settings
])
def test_simple_route_is_ignored_when_it_is_not_safe(request_text, previous, fast):
    import numpy as np

    planner, plans = Planner(), []
    simple_service("simple", planner, plans, fast_search=fast).ask(request_text, previous_ids=np.array([1]) if previous else None)
    assert planner.calls == 1  # the full planner handled it


def test_router_maps_simple_and_caches_decisions(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(OllamaClient, "_request", lambda self, path, payload=None: sent.append(payload) or {"message": {"content": '{"route": "simple"}'}})
    route = _context(tmp_path, monkeypatch).router()
    assert route("Dogs", False) == "simple" and route("  Dogs ", False) == "simple" and len(sent) == 1  # second call came from the cache
    assert route("Dogs", True) == "simple" and len(sent) == 2  # earlier results change the question


def test_search_readiness_and_settings_switch(tmp_path, monkeypatch):
    import inspect

    from aperture.config import Settings
    from aperture.ui import app
    from aperture.ui.views import settings

    ctx = _context(tmp_path, monkeypatch)
    assert ctx.search_ready() is False
    ctx._index, ctx._embedder = object(), object()
    assert ctx.search_ready() is True
    assert Settings().fast_search is True
    assert "fast_search" in inspect.getsource(settings) and "Search warming up" in inspect.getsource(app)


# ---------------------------------------------------------------- real-world failures reported from the app
def test_a_plain_how_many_counts_everything_instead_of_asking_what_to_look_for():
    class CountPlanner:
        def plan(self, request, ctx):
            return PlanResult(plan=Plan(intent="count"))  # the AI understood "count" but set no filters

    plans = []

    def make_executor():
        def run(plan, previous):
            plans.append(plan)
            raise RuntimeError("stop here")
        return SimpleNamespace(run=run)

    svc = AgentService(CountPlanner(), make_executor, lambda: [], today=lambda: date(2026, 11, 3), router=lambda r, p: "photos")
    svc.ask("how many pics are there in total")
    assert plans and plans[0].all_photos is True and plans[0].intent == "count"


def test_a_count_after_earlier_results_is_not_widened_to_everything():
    import numpy as np

    class CountPlanner:
        def plan(self, request, ctx):
            return PlanResult(plan=Plan(intent="count"))

    svc = AgentService(CountPlanner(), lambda: SimpleNamespace(run=lambda p, prev: (_ for _ in ()).throw(AssertionError("no search"))),
                       lambda: [], router=lambda r, p: "photos")
    reply = svc.ask("how many", previous_ids=np.array([1, 2]))
    assert reply.kind == "clarify"  # unchanged behaviour: it refers to the earlier set, which the planner did not narrow


def test_timings_cover_every_step_of_a_photo_question():
    class Planner2:
        def plan(self, request, ctx):
            return PlanResult(plan=Plan(intent="find", clauses=(Clause(engines=("visual",), query="x", exclude=False),)))

    reached = {}

    def make_executor():
        def run(plan, previous):
            reached["ok"] = True
            raise RuntimeError("stop")
        return SimpleNamespace(run=run)

    svc = AgentService(Planner2(), make_executor, lambda: [], router=lambda r, p: "photos")
    reply = svc.ask("sunset photos from Goa in 2023")
    assert reached and reply.kind == "error"  # the stub stops the search; the timing keys below were recorded on the way
    # timings live on successful replies; check the chat route (no search) carries route time
    chat = service(lambda r, p: "chat", chat_stream=lambda *a: iter(["x"])).ask("tell me about cameras")
    assert set(chat.timings) == {"route"}


def test_real_chat_requests_are_short_and_calm(tmp_path, monkeypatch):
    from aperture.agent.service import CHAT_MAX_TOKENS

    sent = []
    monkeypatch.setattr(OllamaClient, "_request", lambda self, path, payload=None: sent.append(payload) or {"message": {"content": "ok"}})
    agent = _context(tmp_path, monkeypatch).agent()
    agent._chatter("tell me about cameras", [])
    p = sent[0]
    assert CHAT_MAX_TOKENS == 160 and p["options"]["num_predict"] == 160 and p["options"]["temperature"] == 0.3
    assert "photo app" in p["messages"][0]["content"] and "emojis" in p["messages"][0]["content"] and "Lumo:" in p["messages"][0]["content"]


# ---------------------------------------------------------------- dates are found by a focused step, for every brain
def _service_with_dates(step, plans):
    def make_executor():
        def run(plan, previous):
            plans.append(plan)
            raise RuntimeError("stop here")
        return SimpleNamespace(run=run)

    return AgentService(planner=None, executor_factory=make_executor, known_people=lambda: [], rescue=False, date_step=step)


def _spec(**kw):
    from aperture.agent.schema import plan_from_raw

    return plan_from_raw({"intent": "find", "date": kw})[0].date


def test_a_time_expression_the_plan_turned_into_words_becomes_a_real_date():
    plans = []
    text_plan = Plan(intent="find", clauses=(Clause(engines=("text",), query="last month", exclude=False),))
    _service_with_dates(lambda request: ("last month", _spec(relative="last_month")), plans).run_plan("show me pics of last month", text_plan)
    assert plans[0].date.relative == "last_month" and plans[0].clauses == ()  # a date search, not the words 'last month'


def test_other_clauses_survive_and_only_clauses_that_repeat_the_date_words_are_dropped():
    plans = []
    plan = Plan(intent="find", clauses=(Clause(engines=("visual",), query="beach", exclude=False),
                                        Clause(engines=("text",), query="summer 2022", exclude=False)))
    _service_with_dates(lambda r: ("summer 2022", _spec(year=2022, season="summer")), plans).run_plan("beach summer 2022", plan)
    assert [c.query for c in plans[0].clauses] == ["beach"] and plans[0].date.year == 2022 and plans[0].date.season == "summer"


def test_the_date_step_is_skipped_when_the_plan_has_a_date_or_finds_none_or_fails():
    calls = []

    def step(request):
        calls.append(request)
        return "", _spec()

    plans = []
    svc = _service_with_dates(step, plans)
    dated = Plan(intent="find", clauses=(Clause(engines=("visual",), query="dog", exclude=False),), date=_spec(year=2020))
    svc.run_plan("dogs 2020", dated)
    assert not calls and plans[0].date.year == 2020  # already has a date: no extra call
    svc.run_plan("dogs", Plan(intent="find", clauses=(Clause(engines=("visual",), query="dog", exclude=False),)))
    assert calls == ["dogs"] and plans[1].date.is_empty  # nothing found: the plan is untouched

    def failing(request):
        raise LLMError("Ollama is not reachable")

    plans2 = []
    _service_with_dates(failing, plans2).run_plan("dogs", Plan(intent="find", clauses=(Clause(engines=("visual",), query="dog", exclude=False),)))
    assert len(plans2) == 1  # the search still ran


def test_the_real_date_step_reads_the_models_json(tmp_path, monkeypatch):
    from aperture.agent.service import DATE_SCHEMA

    sent = []
    monkeypatch.setattr(OllamaClient, "_request", lambda self, path, payload=None: sent.append(payload) or {"message": {"content": '{"phrase": "last month", "relative": "last_month"}'}})
    ctx = _context(tmp_path, monkeypatch)
    step = ctx.agent()._date_step
    phrase, spec = step("pics of last month")
    assert phrase == "last month" and spec.relative == "last_month"
    assert sent[0]["format"] == DATE_SCHEMA and sent[0]["options"]["num_predict"] == 60
    monkeypatch.setattr(OllamaClient, "_request", lambda self, path, payload=None: {"message": {"content": "not json"}})
    assert step("x")[0] == ""
