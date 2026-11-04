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


def test_clause_in_the_wrong_engine_falls_back_to_the_right_one(scanned):
    """A city searched by 'visual' must still find the city: the model picked the wrong engine."""
    from aperture.agent.schema import Clause, Plan

    ctx = scanned
    conn = ctx.db.connect()
    item_id = conn.execute("SELECT id FROM items WHERE missing=0 LIMIT 1").fetchone()[0]
    conn.execute("UPDATE items SET place='Testville, Nowhere', place_text=' testville nowhere' WHERE id=?", (item_id,))
    conn.commit()
    executor = Executor(ctx.db.connect(), ctx.embedding_index, ctx.search_embedder, strictness="strict")
    result = executor.run(Plan(intent="find", clauses=[Clause(engines=["visual"], query="Testville")]))
    assert result.ids.tolist() == [item_id]
    assert any("found by place instead" in note for note in result.notes)


def test_misspelled_or_alternate_place_names_find_the_library_spelling(scanned):
    from aperture.agent.schema import Clause, Plan

    ctx = scanned
    conn = ctx.db.connect()
    item_id = conn.execute("SELECT id FROM items WHERE missing=0 LIMIT 1").fetchone()[0]
    conn.execute("UPDATE items SET place='Bengaluru, India', place_text=' bengaluru india' WHERE id=?", (item_id,))
    conn.commit()
    executor = Executor(ctx.db.connect(), ctx.embedding_index, ctx.search_embedder, strictness="strict")
    result = executor.run(Plan(intent="find", clauses=[Clause(engines=["place"], query="Bangalore")]))
    assert result.ids.tolist() == [item_id]
    assert any("bengaluru" in note for note in result.notes)


def test_rescue_never_runs_for_plans_with_exclusions_or_dates(scanned):
    from aperture.agent.schema import Clause, Plan
    from aperture.agent.service import _only_plain_clauses

    assert _only_plain_clauses(Plan(intent="find", clauses=[Clause(engines=["place"], query="x")]))
    assert not _only_plain_clauses(Plan(intent="find", clauses=[Clause(engines=["place"], query="x", exclude=True)]))


def test_every_reading_of_the_search_words_is_listed_with_its_own_photos(scanned):
    """A word may be a folder, words in a photo, a place...: each meaning is searched separately and shown, not swapped silently."""
    svc, _ = service(scanned, plan(clauses=[{"engines": ["path"], "query": "italy"}]))
    reply = svc.ask("italy")
    labels = [label for label, _ in reply.groups]
    assert labels[0] == "In folders named italy"  # one thing asked: its most reliable reading leads
    assert all(len(ids) for _, ids in reply.groups)


def test_a_written_word_that_matches_nothing_is_not_silently_dropped(scanned):
    clauses = [{"engines": ["place"], "query": "italy"}, {"engines": ["text"], "query": "zzzqqq"}]
    svc, _ = service(scanned, plan(clauses=clauses))
    reply = svc.ask("italy zzzqqq")
    assert len(reply.ids) == 0  # the word is an exact requirement: nothing is shown instead of something that ignores it


def test_photos_with_gps_but_no_place_name_get_one_without_reading_files(scanned):
    from aperture.search.geo import GeoIndex, fill_missing_places

    conn = scanned.db.connect()
    conn.execute("UPDATE items SET gps_lat=35.68, gps_lon=139.76, place=NULL, place_text='' WHERE id=1")
    geo = GeoIndex(["Shinjuku"], ["Japan"], ["shinjuku tokyo japan"], np.array([35.69]), np.array([139.70]))
    assert fill_missing_places(conn, geo) == 1
    assert conn.execute("SELECT place FROM items WHERE id=1").fetchone()[0] == "Shinjuku, Japan"
    assert fill_missing_places(conn, geo) == 0  # nothing left to name


def test_asking_for_one_thing_leads_with_the_most_reliable_reading_not_a_mixed_search(scanned):
    clauses = [{"engines": ["path"], "query": "italy"}]
    svc, _ = service(scanned, plan(clauses=clauses))
    reply = svc.ask("italy")
    assert reply.text.startswith("**") and "Best match" not in [label for label, _ in reply.groups]
    assert reply.groups[0][0] == "In folders named italy"


def test_when_nothing_looks_right_the_place_is_kept_and_only_the_look_is_relaxed(scanned):
    clauses = [{"engines": ["path"], "query": "italy"}, {"engines": ["visual"], "query": "yellow"}]  # no italy photo is yellow
    svc, _ = service(scanned, plan(clauses=clauses))
    reply = svc.ask("yellow things in italy")
    conn = scanned.db.connect()
    italy = {r[0] for r in conn.execute("SELECT id FROM items WHERE meta_text LIKE '% italy%'")}
    assert len(reply.ids) and set(reply.ids.tolist()) <= italy  # only Italy photos, never the whole library
    assert any("No photo clearly shows yellow" in n for n in reply.notes)
    outside = {r[0] for r in conn.execute("SELECT id FROM items WHERE meta_text NOT LIKE '% italy%'")}
    for _, ids in reply.groups:
        assert not (set(ids.tolist()) & outside)  # and no tab shows the look from everywhere
