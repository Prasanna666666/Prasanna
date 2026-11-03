"""Plans are written token by token (~19 tokens/s on an 8 GB Mac): the lean style keeps them short without changing meaning,
the full style is the original. APERTURE_PLAN_STYLE picks; `aperture eval-plans` measures."""

import json
from datetime import date

import pytest

from aperture.agent import planner, schema


def _examples(text):
    return [json.loads(line) for line in text.split("\n") if line.startswith("{")]


def test_lean_examples_mean_the_same_plan_but_are_shorter():
    full, lean = _examples(planner.system_prompt("full")), _examples(planner.system_prompt("lean"))
    assert len(full) == len(lean) >= 8
    for f, s in zip(full, lean, strict=True):
        assert schema.plan_from_raw(f)[0] == schema.plan_from_raw(s)[0]
    size = lambda rows: sum(len(json.dumps(r, separators=(",", ":"))) for r in rows)  # noqa: E731
    assert size(lean) < 0.9 * size(full)
    assert all({"scope", "match", "all_photos", "date", "filters"} <= set(r) for r in lean)  # the decision checklist stays


def test_full_style_is_the_original():
    assert planner.system_prompt("full") == planner._PROMPT_TEXT
    assert schema.plan_schema("full")["required"] == ["intent", "message", "scope", "match", "all_photos", "clauses", "date", "folder_name"]


def test_lean_schema_keeps_decision_fields_and_drops_empty_ones():
    s = schema.plan_schema("lean")
    assert set(s["required"]) == {"intent", "scope", "match", "all_photos", "clauses", "date", "filters"}
    assert s["properties"]["clauses"]["items"]["required"] == ["engines", "query"]
    assert s["properties"]["date"]["required"] == ["year", "month", "season", "relative"]
    assert schema.plan_schema("full")["properties"]["date"]["required"] != s["properties"]["date"]["required"]  # copy, not alias


def test_minimal_output_still_gives_a_valid_plan():
    plan, warnings = schema.plan_from_raw({"intent": "find", "clauses": [{"engines": ["visual"], "query": "sunset"}]})
    assert not warnings and plan.scope == "library" and plan.match == "all" and plan.date.is_empty


@pytest.mark.parametrize("env,expected", [(None, "full"), ("full", "full"), ("FULL", "full"), ("lean", "lean"), ("LEAN", "lean"), ("junk", "full")])
def test_style_selection(monkeypatch, env, expected):
    monkeypatch.delenv("APERTURE_PLAN_STYLE", raising=False)
    if env:
        monkeypatch.setenv("APERTURE_PLAN_STYLE", env)
    assert planner.plan_style() == expected


def test_planner_uses_the_selected_style(monkeypatch):
    seen = {}

    class Fake:
        def complete_json(self, system, user, sch):
            seen["required"], seen["system"] = sch["required"], system
            return '{"intent":"find","clauses":[{"engines":["visual"],"query":"x","exclude":false}]}'

    ctx = planner.PlannerContext(today=date(2026, 11, 3))
    monkeypatch.setenv("APERTURE_PLAN_STYLE", "full")
    planner.Planner(Fake()).plan("x", ctx)
    assert "message" in seen["required"] and seen["system"] == planner._PROMPT_TEXT
    monkeypatch.setenv("APERTURE_PLAN_STYLE", "lean")
    planner.Planner(Fake()).plan("x", ctx)
    assert "message" not in seen["required"] and seen["system"] != planner._PROMPT_TEXT


def test_prompt_does_not_contain_todays_date():
    """Models copy 'TODAY: 2026-11-03' into the forced year/month fields; dates are resolved in code instead."""
    ctx = planner.PlannerContext(today=date(2026, 11, 3), known_people=("Anna",))
    text = planner.Planner._user_prompt("sunset photos", ctx)
    assert "2026" not in text and "TODAY" not in text
    assert "Anna" in text and "sunset photos" in text
