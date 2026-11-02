import json
import random
import string
import time
from datetime import date

import pytest

from aperture.agent.jsonutil import JSONExtractError, extract_json
from aperture.agent.planner import Planner
from aperture.agent.schema import plan_from_raw
from aperture.evaluation import GOLDEN_TEMPLATE, evaluate_plans, evaluate_retrieval, load_plan_cases, plan_mismatches
from aperture.search.visual import STRICTNESS

from .test_agent import ScriptedLLM


class OracleLLM:
    """Answers each request with the expected plan (proves the scorer and schema agree)."""

    def __init__(self, cases, wrong_every=0):
        self.by_request = {c["request"]: c["expect"] for c in cases}
        self.calls, self.wrong_every = 0, wrong_every

    def complete_json(self, system, user, schema):
        request = user.rsplit("User: ", 1)[1]
        e = self.by_request[request]
        self.calls += 1
        if self.wrong_every and self.calls % self.wrong_every == 0:
            return json.dumps({"intent": "find", "clauses": [{"engines": ["visual"], "query": "banana", "exclude": False}]})
        d = {"year": 0, "month": 0, "season": "none", "relative": "none", "start": "", "end": ""} | e["date"]
        return json.dumps(
            {"intent": e["intent"], "message": "hi", "scope": e["scope"], "match": e["match"], "all_photos": e["all_photos"],
             "clauses": e["clauses"], "date": d, "filters": e["filters"], "folder_name": "Folder" if e["folder_name"] else ""}
        )  # fmt: skip


def test_plan_cases_are_well_formed_and_varied():
    cases = load_plan_cases()
    assert len(cases) >= 40 and len({c["request"] for c in cases}) == len(cases)
    assert {c["expect"]["intent"] for c in cases} >= {"find", "count", "export", "chat", "clarify"}


def test_scorer_accepts_correct_plans_and_rejects_wrong_ones():
    cases = load_plan_cases()
    assert evaluate_plans(Planner(OracleLLM(cases)), cases, date(2026, 11, 2)).accuracy == 1.0
    degraded = evaluate_plans(Planner(OracleLLM(cases, wrong_every=5)), cases, date(2026, 11, 2))
    assert 0.7 < degraded.accuracy < 0.9 and degraded.failures


def test_scorer_penalises_invented_constraints():
    plan, _ = plan_from_raw(
        {
            "intent": "find",
            "clauses": [
                {"engines": ["visual"], "query": "dog", "exclude": False},
                {"engines": ["visual"], "query": "cat", "exclude": False},
            ],
        }
    )
    expect = {"intent": "find", "scope": "library", "match": "all", "all_photos": False, "date": {}, "filters": {}, "folder_name": False,
              "clauses": [{"engines": ["visual"], "query": "dog", "exclude": False}]}  # fmt: skip
    assert any("invented" in p for p in plan_mismatches(plan, expect))


def test_unreachable_llm_counts_as_failure_not_crash():
    from aperture.agent.llm import LLMUnavailable

    cases = load_plan_cases()[:3]
    result = evaluate_plans(Planner(ScriptedLLM(*[LLMUnavailable("down")] * 3)), cases)
    assert result.correct == 0 and len(result.failures) == 3


def test_retrieval_scores():
    golden = {"cases": [{"request": "a", "relevant": ["x.jpg", "y.jpg"]}, {"request": "b", "relevant": []}]}
    answers = {"a": ["x.jpg", "z.jpg"], "b": []}
    result = evaluate_retrieval(lambda r: answers[r], golden)
    assert result.cases[0].precision == 0.5 and result.cases[0].recall == 0.5
    assert result.cases[1].precision == 1.0  # correctly returning nothing
    assert GOLDEN_TEMPLATE["cases"]


def test_strictness_sweep_on_synthetic_library(scanned):
    """Strictest preset must give perfect precision on the colour library; it is a regression guard."""
    from aperture.evaluation import evaluate_retrieval
    from aperture.library import items_by_ids

    from .test_agent import plan, service

    golden = {"cases": [{"request": "red", "relevant": [r[0] for r in scanned.db.connect().execute("SELECT rel_path FROM items WHERE rel_path LIKE '%red_%'")]},
                        {"request": "green frog", "relevant": []}]}  # fmt: skip
    for level in STRICTNESS:
        scanned.settings.visual_strictness = level
        replies = {
            "red": plan(clauses=[{"engines": ["visual"], "query": "red"}]),
            "green frog": plan(clauses=[{"engines": ["visual"], "query": "green frog"}]),
        }

        def ask(request):
            svc, _ = service(scanned, replies[request])
            ids = svc.ask(request).ids.tolist()
            return [i.rel_path for i in items_by_ids(scanned.db.connect(), ids).values()]

        result = evaluate_retrieval(ask, golden)
        assert result.precision == 1.0 and result.recall == 1.0, level


# ---------------------------------------------------------------- robustness
def test_fuzzed_model_output_never_crashes_the_parser():
    rng = random.Random(7)
    alphabet = string.printable + "{}[]\"':,\u201c\u201d\u00e9\u4e2d"
    for _ in range(3000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 200)))
        try:
            extract_json(text)
        except JSONExtractError:
            pass


def test_fuzzed_plans_never_raise_and_stay_valid():
    rng = random.Random(11)
    junk = [None, 0, -5, 3.5, "x", "", [], {}, [None], {"a": 1}, True, "2024-13-45", 10**30, float("nan")]
    keys = ["intent", "clauses", "match", "date", "filters", "scope", "all_photos", "folder_name", "message"]
    for _ in range(3000):
        raw = {k: rng.choice(junk) for k in rng.sample(keys, rng.randint(0, len(keys)))}
        if rng.random() < 0.5:
            raw["clauses"] = [
                {"engines": rng.choice(junk), "query": rng.choice(junk), "exclude": rng.choice(junk)} for _ in range(3)
            ]
            raw["date"] = {k: rng.choice(junk) for k in ("year", "month", "season", "relative", "start", "end")}
            raw["filters"] = {
                k: rng.choice(junk) for k in ("time_of_day", "hour_from", "hour_to", "min_people", "near", "radius_km")
            }
        plan, _ = plan_from_raw(raw)
        assert plan.intent in ("find", "count", "export", "chat", "clarify")
        from aperture.search.dates import resolve

        resolve(plan.date, date(2026, 11, 2))  # must not raise either


@pytest.mark.parametrize("n", [30_000])
def test_scales_to_tens_of_thousands_of_photos(paths, n):
    """Synthetic library: text/path search, filters and listing stay fast and unbounded."""
    import numpy as np

    from aperture.db import Database
    from aperture.library import item_ids
    from aperture.search.filters import Filters, apply_filters
    from aperture.search.metadata import path_ids

    conn = Database(paths.db).connect()
    rows = [
        (f"/p/{i}.jpg", f"Trips/{'Italy' if i % 3 == 0 else 'Spain'}/{i}.jpg", f" trips {'italy' if i % 3 == 0 else 'spain'} {i}", "image", 1000 + i,
         f"2024-0{1 + i % 9}-{1 + i % 28:02d} {i % 24:02d}:00:00", 1, 4000, 3000, 1, 1)
        for i in range(n)
    ]  # fmt: skip
    conn.executemany(
        "INSERT INTO items(path, rel_path, meta_text, kind, size, taken_at, taken_exif, width, height, meta_done, clip_done) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    start = time.perf_counter()
    assert len(item_ids(conn)) == n
    assert len(path_ids(conn, "italy")) == n // 3
    found, _ = apply_filters(conn, Filters(time_of_day="night", day_type="weekend", orientation="landscape"), None)
    assert isinstance(found, np.ndarray)
    assert time.perf_counter() - start < 5.0
