import json
from datetime import date

import numpy as np

from aperture.agent.llm import LLMUnavailable
from aperture.agent.loop import AgentLoop, LoopPlanner, Toolbox
from aperture.agent.planner import PlannerContext
from aperture.evaluation import evaluate_plans, load_plan_cases

from .test_agent import ScriptedLLM
from .test_evaluation import OracleLLM


class FakeVision:
    """Says yes only to red photos (the thumbnail's centre pixel)."""

    def __init__(self):
        self.calls = 0

    def judge(self, image, question):
        from io import BytesIO

        from PIL import Image

        self.calls += 1
        r, *_ = Image.open(BytesIO(image)).convert("RGB").getpixel((5, 5))
        return (r > 150, "red" if r > 150 else "not red")


def step(tool, thought="x", **args):
    return json.dumps({"thought": thought, "tool": tool, "args": args})


def make_loop(ctx, llm, vision=None):
    from aperture.agent.executor import Executor

    def make_executor():
        return Executor(ctx.db.connect(), ctx.embedding_index, ctx.search_embedder, strictness="balanced")

    def toolbox(previous):
        return Toolbox(
            ctx.db.connect(), ctx.paths, ctx.settings, make_executor, ctx.embedding_index, ctx.search_embedder, vision, previous
        )

    return AgentLoop(llm, toolbox, lambda: [], max_steps=6, today=lambda: date(2026, 11, 2))


def test_two_step_search_then_finish(scanned):
    llm = ScriptedLLM(
        step("plan_search", clauses=[{"engines": ["visual"], "query": "red", "exclude": False}]),
        step("finish", **{"set": "A", "message": "Here you go.", "show": "photos", "folder_name": ""}),
    )
    reply = make_loop(scanned, llm).ask("red photos")
    assert reply.kind == "results" and len(reply.ids) == 3 and "**3** photos" in reply.text
    assert [t["tool"] for t in reply.trace] == ["plan_search", "finish"]


def test_model_cannot_invent_photos_or_counts(scanned):
    llm = ScriptedLLM(step("plan_search", clauses=[{"engines": ["visual"], "query": "green frog", "exclude": False}]),
                      step("finish", **{"set": "A", "message": "I found 500 frogs!", "show": "photos"}))  # fmt: skip
    reply = make_loop(scanned, llm).ask("frogs")
    assert len(reply.ids) == 0 and reply.text.startswith("No photos")


def test_agent_verifies_with_vision_then_filters(scanned):
    vision = FakeVision()
    llm = ScriptedLLM(
        step(
            "plan_search",
            match="any",
            clauses=[
                {"engines": ["visual"], "query": "red", "exclude": False},
                {"engines": ["visual"], "query": "blue", "exclude": False},
            ],
        ),
        step("verify_visually", **{"set": "A", "question": "is it red?", "n": 5}),
        step("filter_visually", **{"set": "A", "question": "is it red?"}),
        step("finish", **{"set": "B", "message": "Only the red ones.", "show": "photos"}),
    )
    reply = make_loop(scanned, llm, vision).ask("red things, double-check")
    assert len(reply.ids) == 3 and vision.calls == 5 + 5
    assert ("confirmed" in reply.trace[1]["observation"] and "3/5" in reply.trace[1]["observation"]) or "2/" in reply.trace[1][
        "observation"
    ]


def test_combine_sets(scanned):
    llm = ScriptedLLM(
        step("search_visual", query="red", strictness="balanced"),
        step("plan_search", clauses=[{"engines": ["path"], "query": "italy", "exclude": False}]),
        step("combine", op="and", a="A", b="B"),
        step("finish", **{"set": "C", "message": "ok", "show": "count"}),
    )
    reply = make_loop(scanned, llm).ask("red photos from italy, how many")
    assert reply.kind == "count" and len(reply.ids) == 3


def test_bad_tool_use_is_reported_to_model_and_recovered(scanned):
    llm = ScriptedLLM(
        step("combine", op="and", a="Z", b="Q"),
        step("search_visual", query="red", strictness="extreme"),
        step("plan_search", clauses=[{"engines": ["path"], "query": "family", "exclude": False}]),
        step("finish", **{"set": "A", "message": "ok", "show": "photos"}),
    )
    reply = make_loop(scanned, llm).ask("family")
    assert reply.trace[0]["observation"].startswith("error") and reply.trace[1]["observation"].startswith("error")
    assert len(reply.ids) == 2


def test_garbage_replies_then_valid(scanned):
    llm = ScriptedLLM("nonsense", '{"tool": "rm -rf"}', step("finish", set="", message="Hi!", show="none"))
    assert make_loop(scanned, llm).ask("hello").kind == "chat"


def test_step_budget_returns_latest_set_flagged(scanned):
    plan = step("plan_search", clauses=[{"engines": ["path"], "query": "italy", "exclude": False}])
    reply = make_loop(scanned, ScriptedLLM(*[plan] * 8)).ask("italy")
    assert len(reply.ids) == 3 and reply.warnings


def test_unreachable_llm_and_ask_user(scanned):
    assert make_loop(scanned, ScriptedLLM(LLMUnavailable("down"))).ask("x").kind == "error"
    assert make_loop(scanned, ScriptedLLM(step("ask_user", question="Which year?"))).ask("old photos").kind == "clarify"


def test_vision_missing_is_a_tool_error_not_a_crash(scanned):
    llm = ScriptedLLM(step("plan_search", clauses=[{"engines": ["path"], "query": "italy", "exclude": False}]),
                      step("verify_visually", **{"set": "A", "question": "q"}), step("finish", **{"set": "A", "message": "", "show": "photos"}))  # fmt: skip
    reply = make_loop(scanned, llm, vision=None).ask("italy")
    assert "no vision model" in reply.trace[1]["observation"] and len(reply.ids) == 3


def test_suggest_defects_tool(scanned):
    llm = ScriptedLLM(
        step("suggest_defects", sensitivity="high"), step("finish", **{"set": "A", "message": "candidates", "show": "photos"})
    )
    assert len(make_loop(scanned, llm).ask("find bad photos").ids) == 5  # flat test photos are all 'blurry/blank'


def test_loop_planner_adapter_scores_like_planner():
    """The agent loop's first plan is measured by the same plan-accuracy harness."""

    class LoopOracle(OracleLLM):
        def complete_json(self, system, user, schema):
            plan = json.loads(super().complete_json(system, "User: " + user.split("User: ", 1)[1].split("\nPROGRESS")[0], schema))
            self.queue = getattr(self, "queue", [])
            if "PROGRESS" not in user:
                if plan["intent"] in ("chat", "clarify"):
                    return (
                        step("finish", set="", message="m", show="none")
                        if plan["intent"] == "chat"
                        else step("ask_user", question="Which?")
                    )
                return step("plan_search", **plan)
            show = {"count": "count", "export": "export"}.get(plan["intent"], "photos")
            return step("finish", **{"set": "A", "message": "m", "show": show, "folder_name": plan["folder_name"]})

    cases = load_plan_cases()
    result = evaluate_plans(LoopPlanner(LoopOracle(cases)), cases, date(2026, 11, 2))
    assert result.accuracy == 1.0, result.failures[:3]
    assert isinstance(np.zeros(1), np.ndarray) and PlannerContext
