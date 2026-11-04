"""The tool-using agent: the model decides (tool call or words); our code only carries it out."""

import json
import pathlib
import urllib.request
from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest

from aperture.agent.llm import LLMError, OllamaClient
from aperture.agent.schema import Plan
from aperture.agent.service import AgentReply, AgentService
from aperture.agent.toolagent import FILTER_KEYS, MAX_STEPS, PARAMS, TOOL_DEFS, TOOLS, ToolAgent, close_matches, plan_from_tool


# ------------------------------------------------------------------ tool calls become exact search plans
def test_last_month_becomes_a_date_not_words():
    plan = plan_from_tool("find_photos", {"relative": "last_month"})
    assert plan.intent == "find" and plan.date.relative == "last_month" and plan.clauses == () and plan.has_constraints


def test_a_rich_request_maps_to_clauses_dates_and_filters():
    plan = plan_from_tool("find_photos", {"what": "beach", "people": ["Anna", "Raj"], "places": "Goa", "year": "2023", "season": "summer",
                                          "not_people": ["Dev"], "time_of_day": "evening", "min_people": 2, "near": "Eindhoven", "radius_km": 20})
    queries = {(tuple(c.engines), c.query, c.exclude) for c in plan.clauses}
    assert queries == {(("visual",), "beach", False), (("person",), "Anna", False), (("person",), "Raj", False),
                       (("place", "path"), "Goa", False), (("person",), "Dev", True)}
    assert plan.date.year == 2023 and plan.date.season == "summer"
    assert plan.filters.time_of_day == "evening" and plan.filters.min_people == 2 and plan.filters.near == "Eindhoven"


def test_counting_with_no_filters_means_all_photos_but_narrowing_does_not():
    assert plan_from_tool("count_photos", {}).all_photos is True
    assert plan_from_tool("count_photos", {"year": 2026}).all_photos is False
    narrowed = plan_from_tool("count_photos", {"narrow_previous": True})
    assert narrowed.scope == "previous" and narrowed.all_photos is False


def test_bad_values_are_dropped_instead_of_crashing():
    plan = plan_from_tool("find_photos", {"relative": "last mounth", "year": "soon", "min_people": "lots", "people": 42, "what": None})
    assert plan.date.is_empty and not plan.has_constraints


def test_copying_to_a_folder_is_an_export():
    plan = plan_from_tool("find_photos", {"places": ["Rome"], "copy_to_folder": "Italy"})
    assert plan.intent == "export" and plan.folder_name == "Italy"


def test_tool_descriptions_are_the_only_identity_and_the_choices_are_clean():
    names = [t["function"]["name"] for t in TOOLS]
    assert names == ["find_photos", "count_photos", "copy_photos", "library_overview", "show_results", "probe", "inspect_results", "calc_date", "look_up", "read_photo_text", "look_at_photos"]
    assert "photo library" in TOOLS[0]["function"]["description"]
    assert "last_month" in PARAMS["relative"]["enum"] and "none" not in PARAMS["relative"]["enum"] and "none" not in PARAMS["season"]["enum"]
    assert all(k in PARAMS for k in FILTER_KEYS) and "required" not in TOOLS[0]["function"]["parameters"]
    assert TOOLS[8]["function"]["parameters"]["required"] == ["kind", "text"] and TOOLS[2]["function"]["parameters"]["required"] == ["folder"]
    assert TOOLS[10]["function"]["parameters"]["required"] == ["question"]


# ------------------------------------------------------------------ the agent loop
def tool(name, **arguments):
    return ("tool", {"name": name, "arguments": arguments})


class FakeLLM:
    """A scripted model: each call to chat_events plays the next 'turn' (a list of events), and records what it was shown."""

    def __init__(self, turns):
        self.turns, self.calls = list(turns), []

    def chat_events(self, system, messages, tools, max_tokens=400):
        self.calls.append((system, [dict(m) for m in messages], tools, max_tokens))
        turn = self.turns.pop(0) if self.turns else []
        if callable(turn):
            turn = turn()
        return iter(turn)


FOUND = SimpleNamespace(ids=np.array([11, 12, 13]), reports=[], notes=[], date_range="2026-10-01 to 2026-10-31")


def agent_with(turns, outcome=FOUND, facts="PLACES IN THIS LIBRARY: Goa", overview=None, lookup=None):
    plans = []

    def make_executor():
        def run(plan, previous):
            plans.append((plan, previous))
            if outcome is None:
                raise RuntimeError("stop here")
            return outcome
        return SimpleNamespace(run=run)

    service = AgentService(planner=None, executor_factory=make_executor, known_people=lambda: [], today=lambda: date(2026, 11, 3), rescue=False)
    llm = FakeLLM(turns)
    return ToolAgent(llm, service, lambda request: facts, overview=overview, lookup=lookup, today=lambda: date(2026, 11, 3)), llm, plans


def test_the_model_decides_to_talk_and_words_stream_without_a_search():
    agent, llm, plans = agent_with([[("delta", "Doing "), ("delta", "well.")]])
    reply = agent.ask("how are you?", history=[("user", "hi"), ("assistant", "Hello")])
    assert reply.kind == "chat" and "".join(reply.stream) == "Doing well." and not plans and len(reply.ids) == 0
    system, messages, tools, max_tokens = llm.calls[0]
    assert [m["role"] for m in messages] == ["user", "assistant", "user"] and tools == TOOLS and max_tokens == 160
    assert reply.timings.keys() >= {"context", "decide"}


def test_the_model_is_not_told_what_the_app_is_only_given_data():
    agent, llm, _ = agent_with([[("delta", "x")]])
    agent.ask("hello")
    system = llm.calls[0][0]
    assert "Today is Tuesday 03 November 2026." in system and "LIBRARY FACTS" in system and "PLACES IN THIS LIBRARY: Goa" in system
    for persona in ("photo app", "You are", "Lumo", "assistant inside"):
        assert persona not in system


def test_the_model_reads_the_search_result_before_it_answers_and_the_photos_stay_on_screen():
    agent, llm, plans = agent_with([[tool("find_photos", relative="last_month")], [("delta", "Found "), ("delta", "3 from October.")]])
    reply = agent.ask("Show me pics of last month")
    assert plans[0][0].date.relative == "last_month" and plans[0][0].clauses == ()  # a date search, not a word search
    # round 2: the model was shown its own tool call and the observation of the real search
    second = llm.calls[1][1]
    assert second[-2]["role"] == "assistant" and second[-2]["tool_calls"][0]["function"]["name"] == "find_photos"
    observation = json.loads(second[-1]["content"])
    assert second[-1]["role"] == "tool" and observation["matched"] == 3 and observation["date_range"] == "2026-10-01 to 2026-10-31"
    # the model writes the words; the found photos are attached to the streamed reply
    assert reply.text.startswith("**3** photo") and reply.kind == "results" and list(reply.ids) == [11, 12, 13]
    assert reply.timings.keys() >= {"context", "decide", "tools", "search"}


def test_an_empty_result_is_told_plainly_by_the_app_not_improvised_by_the_model():
    empty = SimpleNamespace(ids=np.zeros(0, np.int64), reports=[], notes=[], date_range="2026-10-01 to 2026-10-31")
    agent, llm, plans = agent_with([[tool("find_photos", relative="last_month")], [("delta", "Nothing from October.")]], outcome=empty)
    reply = agent.ask("pics of last month")
    observation = json.loads(llm.calls[1][1][-1]["content"])
    assert observation["matched"] == 0 and observation["summary"].startswith("No photos found")
    assert len(plans) == 1 and len(reply.ids) == 0 and reply.text.startswith("No photos found") and "Nothing from October" not in reply.text


def test_counting_everything_and_the_overview_tool_feed_the_model_real_data():
    agent, llm, plans = agent_with([[tool("count_photos")], [("delta", "49,743.")]])
    reply = agent.ask("how many pics are there in total")
    assert plans[0][0].all_photos is True and plans[0][0].intent == "count"
    assert json.loads(llm.calls[1][1][-1]["content"])["matched"] == 3 and reply.text.startswith("**3** photo")
    agent2, llm2, plans2 = agent_with([[tool("library_overview")], [("delta", "A big library.")]], overview=lambda previous: "FACTS: 49,743 files from 2012 to 2025")
    agent2.ask("what is in my library?")
    assert llm2.calls[1][1][-1] == {"role": "tool", "tool_name": "library_overview", "content": "FACTS: 49,743 files from 2012 to 2025"} and not plans2


def test_look_up_lets_the_model_check_real_names_before_searching():
    asked = []
    agent, llm, plans = agent_with([[tool("look_up", kind="place", text="goa")], [tool("find_photos", places=["Goa, India"])], [("delta", "ok")]],
                                   lookup=lambda kind, text: asked.append((kind, text)) or ["Goa, India"])
    agent.ask("photos from goa")
    assert asked == [("place", "goa")] and json.loads(llm.calls[1][1][-1]["content"]) == {"matches": ["Goa, India"]}
    assert plans[0][0].clauses[0].query == "Goa, India"  # the second round searched with the exact name the library uses


def test_close_matches_finds_substrings_and_misspellings():
    names = ["Goa, India", "Eindhoven, Netherlands", "Lisbon, Portugal"]
    assert close_matches(names, "goa") == ["Goa, India"]
    assert close_matches(names, "eindhovn") == []  # no whole-name close match: substring and fuzzy are on the full name
    assert close_matches(["Anna", "Raj"], "Ana") == ["Anna"] and close_matches(names, "") == []


def test_bad_tool_calls_become_observations_the_model_can_recover_from():
    agent, llm, plans = agent_with([[tool("find_photos")], [("delta", "What should I look for?")]])
    reply = agent.ask("show me stuff")
    assert "no search conditions" in json.loads(llm.calls[1][1][-1]["content"])["error"] and not plans
    assert "".join(reply.stream) == "What should I look for?"
    agent2, llm2, _ = agent_with([[tool("delete_everything")], [("delta", "I can't do that.")]])
    agent2.ask("delete it all")
    assert "no tool called" in json.loads(llm2.calls[1][1][-1]["content"])["error"]


def test_the_agent_has_a_step_budget_so_it_can_never_loop_forever():
    agent, llm, plans = agent_with([[tool("find_photos", what="dog")]] * 10)
    reply = agent.ask("dogs")
    assert reply.text.startswith("I could not finish") and len(llm.calls) == MAX_STEPS + 1 and len(plans) == MAX_STEPS
    assert llm.calls[-1][2] == [] and all(c[2] == TOOLS for c in llm.calls[:-1])  # the last round has no tools: it must answer


def test_iterating_is_bounded_by_time_so_it_never_makes_the_app_slow(monkeypatch):
    from aperture.agent import toolagent

    clock = {"now": 100.0}
    monkeypatch.setattr(toolagent.time, "monotonic", lambda: clock["now"])

    def slow_turn():  # the first round takes 20 simulated seconds
        clock["now"] += 20.0
        return [tool("find_photos", what="dog")]

    agent, llm, plans = agent_with([slow_turn, [("delta", "Here is what I found.")]])
    reply = agent.ask("dogs")
    assert len(plans) == 1 and reply.text.startswith("**")
    assert llm.calls[1][2] == []  # over budget: no more tools, the model answers with what it has


def test_the_slow_vision_tool_is_refused_when_little_time_is_left_and_capped_otherwise(monkeypatch):
    from aperture.agent import toolagent

    asked = []
    look = lambda ids, question: asked.append((ids, question)) or [{"photo": i, "answer": "yes"} for i in ids]
    agent, llm, _ = agent_with([[tool("find_photos", what="sunset")], [tool("look_at_photos", question="is it a sunset?", count=3)], [("delta", "Yes.")]])
    agent._look = look
    agent.ask("sunsets")
    assert asked == [([11, 12, 13], "is it a sunset?")] and json.loads(llm.calls[2][1][-1]["content"])["photos"][0]["answer"] == "yes"

    clock = {"now": 0.0}
    monkeypatch.setattr(toolagent.time, "monotonic", lambda: clock["now"])
    def slow_look():  # nine simulated seconds pass before the model asks to look: only six of the fifteen remain
        clock["now"] += 9
        return [tool("look_at_photos", question="x")]

    agent2, llm2, _ = agent_with([[tool("find_photos", what="sunset")], slow_look, [("delta", "ok")]])
    agent2._look = look
    asked.clear()
    agent2.ask("sunsets")
    assert not asked and "not enough time" in json.loads(llm2.calls[2][1][-1]["content"])["error"]


def test_the_agent_can_read_the_text_inside_photos_and_iterate_after_an_empty_search():
    empty = SimpleNamespace(ids=np.zeros(0, np.int64), reports=[], notes=[], date_range="")
    outcomes = iter([empty, FOUND])
    plans = []

    def make_executor():
        return SimpleNamespace(run=lambda plan, previous: plans.append(plan) or next(outcomes))

    service = AgentService(planner=None, executor_factory=make_executor, known_people=lambda: [], rescue=False)
    llm = FakeLLM([[tool("find_photos", text_in_photo=["Starbux"])], [tool("find_photos", text_in_photo=["Starbucks"])],
                   [tool("read_photo_text", count=2)], [("delta", "The total was 4.50.")]])
    read = []
    agent = ToolAgent(llm, service, lambda r: "", read_text=lambda ids: read.append(ids) or [{"photo": ids[0], "text": "STARBUCKS TOTAL 4.50"}],
                      today=lambda: date(2026, 11, 3))
    reply = agent.ask("what was the total on my Starbucks receipt?")
    assert [p.clauses[0].query for p in plans] == ["Starbux", "Starbucks"]  # the empty search was retried with different conditions
    assert read == [[11, 12]] and json.loads(llm.calls[3][1][-1]["content"])["photos"][0]["text"] == "STARBUCKS TOTAL 4.50"
    assert "".join(reply.stream) == "The total was 4.50." and list(reply.ids) == [11, 12, 13]


def test_read_and_look_tools_need_a_search_first_and_observations_explain_each_condition():
    agent, llm, _ = agent_with([[tool("read_photo_text")], [("delta", "Search first.")]])
    agent.ask("read it")
    assert "search for photos first" in json.loads(llm.calls[1][1][-1]["content"])["error"]
    from aperture.agent.executor import ClauseReport
    from aperture.agent.toolagent import observation_of

    reply = AgentReply("results", "No photos found.", reports=[ClauseReport("person Anna", 420, 420), ClauseReport("place Goa", 90, 0)])
    assert json.loads(observation_of(reply))["conditions"] == [
        {"condition": "person Anna", "matched_alone": 420, "left_after_combining": 420},
        {"condition": "place Goa", "matched_alone": 90, "left_after_combining": 0}]


def test_narrow_previous_without_earlier_results_falls_back_to_the_whole_library_and_says_so():
    agent, llm, plans = agent_with([[tool("find_photos", what="dog", narrow_previous=True)], [("delta", "ok")]])
    agent.ask("only those")
    assert plans[0][0].scope == "library" and "whole library was searched" in json.loads(llm.calls[1][1][-1]["content"])["notes"][0]
    agent2, llm2, plans2 = agent_with([[tool("find_photos", year=2020, narrow_previous=True)], [("delta", "ok")]])
    agent2.ask("only 2020", previous_ids=np.array([1, 2, 3]))
    assert plans2[0][0].scope == "previous" and "previous message are on the user's screen" in llm2.calls[0][0]


def test_model_errors_and_silence_are_reported_not_raised():
    def boom():
        raise LLMError("Ollama is not reachable")
        yield  # pragma: no cover

    agent, _, _ = agent_with([boom])
    assert agent.ask("hi").kind == "error"
    agent2, _, _ = agent_with([[]])
    assert "could not finish" in agent2.ask("hi").text
    agent3, _, _ = agent_with([[("delta", "x")]])
    agent3._context = lambda request: (_ for _ in ()).throw(RuntimeError("db busy"))  # a failing facts lookup must not stop the answer
    assert agent3.ask("hello").kind == "chat"


def test_a_specialised_agent_is_only_a_goal_and_a_tool_list():
    from aperture.agent.toolagent import AgentSpec

    spec = AgentSpec("counter", ("count_photos",), goal="Your only job is to count photos.")
    agent, llm, plans = agent_with([[tool("find_photos", what="dog")], [("delta", "no")]])
    agent.spec, agent._tools = spec, [TOOL_DEFS["count_photos"]]
    agent.ask("dogs")
    system, _, tools, _ = llm.calls[0]
    assert [t["function"]["name"] for t in tools] == ["count_photos"] and "Your only job is to count photos." in system
    assert "no tool called" in json.loads(llm.calls[1][1][-1]["content"])["error"] and not plans  # find_photos was not allowed


def test_the_real_chat_events_stream_parses_tool_calls_and_text(monkeypatch):
    class Resp:
        def __init__(self, chunks):
            self.chunks = chunks

        def __iter__(self):
            return iter(json.dumps(c).encode() + b"\n" for c in self.chunks)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    call = {"message": {"content": "", "tool_calls": [{"function": {"name": "find_photos", "arguments": {"relative": "last_month"}}}]}}
    stringy = {"message": {"content": "", "tool_calls": [{"function": {"name": "count_photos", "arguments": '{"year": 2026}'}}]}}
    sent = {}

    def fake(req, timeout=None):
        sent["body"] = json.loads(req.data)
        return Resp([{"message": {"content": "Hi"}}, call, stringy, {"message": {"content": ""}, "done": True}])

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    client = OllamaClient("http://127.0.0.1:11434", "ministral-3:3b")
    events = list(client.chat_events("sys", [{"role": "user", "content": "x"}], TOOLS, 160))
    assert events == [("delta", "Hi"), ("tool", {"name": "find_photos", "arguments": {"relative": "last_month"}}),
                      ("tool", {"name": "count_photos", "arguments": {"year": 2026}})]
    assert sent["body"]["tools"] == TOOLS and sent["body"]["stream"] is True and sent["body"]["options"]["num_ctx"] == 4096


# ------------------------------------------------------------------ the real app wiring
def test_the_default_brain_is_the_measured_pipeline_and_the_tool_agent_is_one_setting_away(tmp_path, monkeypatch):
    from aperture.bootstrap import AppContext
    from aperture.config import Paths

    monkeypatch.setenv("APERTURE_ALLOW_INTERNAL", "1")
    paths = Paths(tmp_path / "Expansion")
    paths.ensure()
    ctx = AppContext(paths)
    assert not isinstance(ctx.agent(), AgentService)  # the default is the tool-using agent
    agent = ctx.agent()
    assert isinstance(agent, ToolAgent) and agent._service._rescue is False  # no word-matching fallback


def test_the_agent_is_shown_how_requests_become_tool_calls_but_never_told_what_the_app_is():
    from aperture.agent.toolagent import EXAMPLES

    agent, llm, _ = agent_with([[("delta", "x")]])
    agent.ask("hello")
    system = llm.calls[0][0]
    assert EXAMPLES in system and "search for pictures showing a mountain" in system and "(" not in EXAMPLES.split("Always call")[0].replace("(results are on screen)", "").replace("(results from another place are on screen)", "").replace("(a bare word)", "") and "reply in words, no tool" in system
    for persona in ("photo app", "You are", "Lumo", "assistant inside"):
        assert persona not in system
    eval_requests = {c["request"].lower() for c in __import__("aperture.evaluation", fromlist=["x"]).load_plan_cases()}
    routes = {c["message"].lower() for c in json.loads((pathlib.Path(__file__).parent.parent / "src" / "aperture" / "eval_data" / "route_cases.json").read_text())}
    for line in EXAMPLES.splitlines():
        quoted = line.split("'")[1].lower() if line.startswith("'") else ""
        assert quoted not in eval_requests and quoted not in routes  # the examples teach the pattern, not the test


def test_library_context_is_retrieved_for_the_request(tmp_path, monkeypatch):
    from aperture.bootstrap import AppContext
    from aperture.config import Paths

    monkeypatch.setenv("APERTURE_ALLOW_INTERNAL", "1")
    paths = Paths(tmp_path / "Expansion")
    paths.ensure()
    conn = AppContext(paths).db.connect()
    conn.execute("INSERT INTO items(id, path, rel_path, kind, taken_at, place, meta_done) VALUES (1,'/p/a.jpg','a.jpg','image','2025-05-01 10:00:00','Goa, India',1)")
    conn.commit()
    conn.close()
    ctx = AppContext(paths)
    facts = ctx.agent()._context("photos from Goa")
    assert "PLACES IN THIS LIBRARY: Goa, India" in facts and "PHOTOS SPAN: 2025-05-01" in facts and "LIBRARY SIZE: 1 files, 1 indexed" in facts


# ------------------------------------------------------------------ the note that kept appearing after indexing finished
def test_indexing_note_only_counts_photos_that_are_really_waiting(tmp_path, monkeypatch):
    from aperture.agent.executor import ExecResult, Executor
    from aperture.bootstrap import AppContext
    from aperture.config import Paths

    monkeypatch.setenv("APERTURE_ALLOW_INTERNAL", "1")
    paths = Paths(tmp_path / "Expansion")
    paths.ensure()
    ctx = AppContext(paths)
    conn = ctx.db.connect()
    rows = [(i, f"/p/{i}.jpg", f"{i}.jpg", "image", None, 1) for i in range(1, 11)]
    conn.executemany("INSERT INTO items(id, path, rel_path, kind, error, meta_done) VALUES (?,?,?,?,?,?)", rows)
    conn.execute("UPDATE items SET meta_done=0, error='cannot read file' WHERE id IN (9, 10)")  # failed for good: not 'in progress'
    conn.commit()
    ex = Executor(conn, lambda: None, lambda: None)
    result = ExecResult(ids=np.zeros(0, np.int64))
    ex._coverage_note(result)
    assert result.notes == []  # 8 indexed + 2 that failed: nothing is waiting, so no note, ever
    conn.execute("UPDATE items SET meta_done=0 WHERE id IN (7, 8)")  # two genuinely still waiting
    conn.commit()
    ex._coverage_note(result)
    assert result.notes == ["2 of 10 photos not indexed yet."]


# ------------------------------------------------------------------ the holistic measure
def test_evaluate_tool_agent_scores_whole_sets_with_the_same_expectations_as_eval_plans():
    from aperture.evaluation import evaluate_tool_agent, load_plan_cases

    plans = load_plan_cases()
    routes = json.loads((pathlib.Path(__file__).parent.parent / "src" / "aperture" / "eval_data" / "route_cases.json").read_text())

    def silent(request, previous, people):  # an agent that never uses a tool
        return "words", "hello", {}

    def always_finds(request, previous, people):  # an agent that always runs an empty search
        return "tool", "find_photos", {}

    quiet = evaluate_tool_agent(silent, plans, routes)
    assert quiet.plan_total == len(plans) and quiet.route_total == len(routes)
    wanted_words = sum(1 for c in plans if c["expect"]["intent"] in ("chat", "clarify", "question"))
    assert quiet.plan_correct == wanted_words and quiet.route_correct == sum(1 for c in routes if c["expect"] == "chat")
    eager = evaluate_tool_agent(always_finds, plans, routes)
    assert eager.route_correct == sum(1 for c in routes if c["expect"] != "chat") and eager.plan_correct < len(plans)


def test_a_perfect_agent_scores_perfectly_against_the_expected_plans():
    from aperture.evaluation import evaluate_tool_agent, load_plan_cases

    cases = [c for c in load_plan_cases() if c["request"] == "photos taken at night"]
    assert cases, "expected case missing"

    def decide(request, previous, people):
        return "tool", "find_photos", {"time_of_day": "night"}

    result = evaluate_tool_agent(decide, cases, [])
    assert result.plan_correct == 1 and not result.failures


def test_optional_parameters_say_so_and_required_ones_do_not():
    find = TOOL_DEFS["find_photos"]["function"]["parameters"]["properties"]
    assert "optional" in TOOL_DEFS["find_photos"]["function"]["description"] and "optional" not in json.dumps(find)
    look = TOOL_DEFS["look_up"]["function"]["parameters"]["properties"]
    assert "Leave out" not in json.dumps(look) and look["kind"]["enum"] == ["place", "person", "folder"]
    assert TOOL_DEFS["copy_photos"]["function"]["parameters"]["required"] == ["folder"]
    assert plan_from_tool("copy_photos", {"places": ["Paris"], "folder": "Paris Trip"}).intent == "export"
    assert plan_from_tool("copy_photos", {"places": ["Paris"], "folder": "Paris Trip"}).folder_name == "Paris Trip"


def test_calc_date_does_the_calendar_maths_for_any_offset():
    from datetime import date

    from aperture.agent.toolagent import calc_date

    today = date(2026, 11, 3)
    assert calc_date(today, {"months": -2, "period": "month"}) == {"date_from": "2026-09-01", "date_to": "2026-09-30"}
    assert calc_date(today, {"weeks": -3, "period": "day", "until_today": True}) == {"date_from": "2026-10-13", "date_to": "2026-11-03"}
    assert calc_date(today, {"years": -2, "months": -1, "period": "month"})["date_from"] == "2024-10-01"
    assert calc_date(today, {"period": "year"}) == {"date_from": "2026-01-01", "date_to": "2026-12-31"}


def test_a_tool_call_with_explicit_dates_becomes_that_date_range():
    from aperture.agent.toolagent import plan_from_tool

    plan = plan_from_tool("find_photos", {"date_from": "2026-09-01", "date_to": "2026-09-30"})
    assert (plan.date.start, plan.date.end) == ("2026-09-01", "2026-09-30")


def test_all_tool_definitions_fit_in_a_small_part_of_the_context_window():
    """The model's context is 4096 tokens. Tool definitions that fill it push the conversation out and the model stops answering."""
    from aperture.agent.llm import NUM_CTX

    assert len(json.dumps(TOOLS)) / 3.5 < NUM_CTX * 0.75


def test_a_tool_call_typed_out_as_text_is_not_accepted_the_model_must_really_call_the_tool():
    agent, llm, plans = agent_with([
        [("delta", 'probe(term="tokyo") -> No results.')],  # text that looks like a call: it did nothing
        [tool("find_photos", places=["Tokyo"])],
        [("delta", "ok")],
    ])
    reply = agent.ask("Tokyo")
    assert len(plans) == 1 and plans[0][0].clauses and list(reply.ids) == [11, 12, 13]
    assert "never write a tool call" in llm.calls[0][0]


def test_a_call_typed_out_in_pieces_is_caught_and_a_second_failure_falls_back_to_the_planner():
    pieces = [("delta", "`"), ("delta", "probe"), ("delta", '("'), ("delta", 'tokyo")` -> 12 occurrences found.')]
    agent, llm, plans = agent_with([pieces, pieces])  # told to act, and it types the call out again
    sentinel = object()
    agent._service.ask = lambda request, previous_ids=None, history=None: sentinel  # the planner pipeline
    assert agent.ask("Tokyo") is sentinel and not plans
    assert len(llm.calls) == 2  # asked once, nudged once, then handed to the planner


def test_a_normal_reply_is_shown_in_full_after_the_peek():
    agent, _, _ = agent_with([[("delta", "Hello "), ("delta", "there, "), ("delta", "this is a long enough friendly greeting to pass the peek window, "), ("delta", "and more.")]])
    reply = agent.ask("hi")
    assert "".join(reply.stream) == "Hello there, this is a long enough friendly greeting to pass the peek window, and more."


def test_when_the_model_call_fails_the_planner_still_does_a_real_search():
    from aperture.agent.llm import LLMError

    class Broken:
        def chat_events(self, *a, **k):
            raise LLMError("Ollama returned HTTP 500")

    agent, _, _ = agent_with([[("delta", "x")]])
    agent._llm = Broken()
    agent._probe = lambda term: {"term": term, "photos_with_this_word_written_in_them": 25}
    sentinel = object()
    agent._service.ask = lambda request, previous_ids=None, history=None: sentinel
    assert agent.ask("Tokyo") is sentinel


def test_a_greeting_costs_no_extra_model_call_and_warm_up_uses_the_real_prompt():
    agent, llm, _ = agent_with([[("delta", "Hello! What can I help you find today? " * 3)]], facts="PLACES IN THIS LIBRARY: Goa")
    reply = agent.ask("Hi")
    assert "".join(reply.stream).startswith("Hello") and len(llm.calls) == 1  # no router call, no nudge: nothing from the message is in the library
    agent2, llm2, _ = agent_with([[("delta", "x")]])
    agent2.warm()
    system, messages, tools, max_tokens = llm2.calls[0]
    assert "ACT FIRST" in system and tools == agent2._tools and max_tokens == 1


def test_a_server_error_before_the_first_word_is_retried_once(monkeypatch):
    from aperture.agent import llm as llm_mod
    from aperture.agent.llm import LLMError, OllamaClient

    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)
    client = OllamaClient("http://127.0.0.1:11434", "m")
    calls = []

    def chunks(payload):
        calls.append(1)
        if len(calls) == 1:
            raise LLMError("Ollama returned HTTP 500: runner stopped")
        yield {"message": {"content": "ok"}}

    monkeypatch.setattr(client, "_stream_chunks", chunks)
    assert list(client.chat_events("s", [], [], 5)) == [("delta", "ok")] and len(calls) == 2


def test_words_before_a_real_tool_call_are_dropped_and_the_call_still_runs():
    agent, llm, plans = agent_with([[("delta", "Let me find all photos for you. "), tool("find_photos", places=["Tokyo"])], [("delta", "ok")]])
    reply = agent.ask("Tokyo")
    assert len(plans) == 1 and list(reply.ids) == [11, 12, 13] and "Let me find" not in reply.text
    assert "friendly person" in llm.calls[0][0] and "say nothing before you search" in llm.calls[0][0]


def test_model_words_after_tools_without_any_photos_are_never_shown_the_real_search_answers():
    agent, _, _ = agent_with([[tool("probe", term="Tokyo")], [("delta", "Let me check where and when those photos were taken ... " * 2)]])
    agent._probe = lambda term: {"term": term, "photos_with_this_word_written_in_them": 25}
    sentinel = object()
    agent._service.ask = lambda request, previous_ids=None, history=None: sentinel
    assert agent.ask("Tokyo") is sentinel


def test_show_them_puts_the_photos_on_screen_back_and_a_model_that_only_talks_is_replaced_by_the_search():
    agent, _, plans = agent_with([[tool("show_results")], [("delta", "ok")]])
    reply = agent.ask("Show them", previous_ids=np.array([5, 6, 7]))
    assert list(reply.ids) == [5, 6, 7] and reply.text.startswith("**3** photos") and not plans  # no new search was needed
    # the model keeps talking instead of acting, even after being told: the app searches
    talk = [("delta", "Here are your photos from Tokyo: 27 cityscapes, 15 street scenes and more. " * 2)]
    agent2, _, _ = agent_with([talk, talk])
    sentinel = object()
    agent2._service.ask = lambda request, previous_ids=None, history=None: sentinel
    assert agent2.ask("Show them", previous_ids=np.array([5, 6, 7])) is sentinel


def test_the_start_of_the_prompt_never_changes_so_the_model_can_reuse_what_it_processed():
    agent, _, _ = agent_with([[("delta", "x")]])
    a = agent.system_message("", False)
    b = agent.system_message("DATA MATCHES: 'tokyo' -> text in photos: 25", True)
    shared = len(a.split("Today is")[0])
    assert a[:shared] == b[:shared] and shared > 1000  # examples and rules come first; date, screen and facts come last
    assert b.index("LIBRARY FACTS") > b.index("Today is") > b.index("ACT FIRST")


def test_a_search_flagged_as_narrowing_without_conditions_never_replays_the_old_photos():
    agent, llm, plans = agent_with([[tool("find_photos", narrow_previous=True)], [("delta", "ok")]])
    reply = agent.ask("Germany pics", previous_ids=np.array([5, 6, 7]))
    assert not plans and list(reply.ids) != [5, 6, 7]  # no conditions: an error for the model, not the Tokyo photos again
    assert "no search conditions" in json.loads(llm.calls[1][1][-1]["content"])["error"]
