import json
from datetime import date

import numpy as np
import pytest

from aperture.agent.executor import Executor
from aperture.agent.jsonutil import JSONExtractError, extract_json
from aperture.agent.llm import LLMUnavailable
from aperture.agent.planner import Planner
from aperture.agent.schema import plan_from_raw
from aperture.agent.service import AgentService
from aperture.search.dates import DateSpec, resolve


class ScriptedLLM:
    """Returns queued replies (strings) or raises queued exceptions."""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), 0

    def complete_json(self, system, user, schema):
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, str) else json.dumps(reply)


def service(ctx, *replies):
    llm = ScriptedLLM(*replies)

    def make():
        return Executor(ctx.db.connect(), ctx.embedding_index, ctx.search_embedder, strictness="balanced")

    return AgentService(Planner(llm), make, lambda: [], today=lambda: date(2026, 11, 2)), llm


def plan(intent="find", clauses=(), **extra):
    return {"intent": intent, "clauses": list(clauses), **extra}


@pytest.mark.parametrize(
    "text",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        'Sure! {"a": 1} hope that helps',
        '{"a": 1,}',
        "{'a': 1}".replace("'", '"'),
        '{"a": 1',
    ],
)
def test_extract_json_tolerates_model_noise(text):
    assert extract_json(text) == {"a": 1}


def test_extract_json_rejects_garbage():
    with pytest.raises(JSONExtractError):
        extract_json("no json here")


@pytest.mark.parametrize("raw", [None, [], "x", {"clauses": "oops"}, {"clauses": [None, 3, {"query": ""}]}, {"date": 5}])
def test_plan_from_raw_never_raises(raw):
    result, _ = plan_from_raw(raw)
    assert result.clauses == ()


def test_seasons_are_deterministic():
    assert resolve(DateSpec(season="winter", year=2021), date(2026, 1, 1)) == (date(2021, 12, 1), date(2022, 3, 1))


def test_visual_clause_matches_only_relevant(scanned):
    svc, _ = service(scanned, plan(clauses=[{"engines": ["visual"], "query": "red car"}]))
    reply = svc.ask("red things")
    assert reply.kind == "results" and len(reply.ids) == 3


def test_no_match_returns_zero_not_library(scanned):
    svc, _ = service(scanned, plan(clauses=[{"engines": ["visual"], "query": "green frog"}]))
    reply = svc.ask("green frogs")
    assert len(reply.ids) == 0 and "No photos found" in reply.text


def test_path_and_exclusion(scanned):
    clauses = [{"engines": ["path"], "query": "italy"}, {"engines": ["visual"], "query": "red", "exclude": True}]
    svc, _ = service(scanned, plan(clauses=clauses))
    assert len(svc.ask("italy but not red").ids) == 0


def test_text_engine_and_count(scanned):
    svc, _ = service(scanned, plan("count", [{"engines": ["text"], "query": "invoice"}]))
    reply = svc.ask("how many invoices")
    assert reply.kind == "count" and len(reply.ids) == 3


def test_follow_up_refines_previous(scanned):
    svc, _ = service(scanned, plan("find", [{"engines": ["path"], "query": "family"}], scope="previous"))
    prev = np.array([1, 2, 3], np.int64)
    assert len(svc.ask("only family", prev).ids) <= 3


def test_retries_then_succeeds(scanned):
    svc, llm = service(scanned, "not json", plan(clauses=[{"engines": ["path"], "query": "italy"}]))
    assert len(svc.ask("italy").ids) == 3 and llm.calls == 2


def test_unreachable_llm_is_a_clear_error_not_a_guess(scanned):
    svc, _ = service(scanned, LLMUnavailable("Ollama is not running"))
    reply = svc.ask("anything")
    assert reply.kind == "error" and len(reply.ids) == 0


def test_chat_and_empty_requests(scanned):
    svc, _ = service(scanned, plan("chat", message="Hello!"))
    assert svc.ask("hi").kind == "chat"
    assert svc.ask("   ").kind == "clarify"
