"""Plans are written token by token at ~19 tokens/s on an 8 GB Mac: keep them short, without changing their meaning."""

import json

from aperture.agent import planner, schema


def _examples(text):
    return [json.loads(line) for line in text.split("\n") if line.startswith("{")]


def test_slim_examples_mean_the_same_plan_but_are_much_shorter():
    full, slim = _examples(planner._PROMPT_TEXT), _examples(planner.SYSTEM_PROMPT)
    assert len(full) == len(slim) >= 8
    for f, s in zip(full, slim, strict=True):
        assert schema.plan_from_raw(f)[0] == schema.plan_from_raw(s)[0]
    size = lambda rows: sum(len(json.dumps(r, separators=(",", ":"))) for r in rows)  # noqa: E731
    assert size(slim) < 0.5 * size(full)


def test_schema_only_requires_intent_and_clauses():
    assert schema.PLAN_JSON_SCHEMA["required"] == ["intent", "clauses"]
    assert schema.PLAN_JSON_SCHEMA["properties"]["clauses"]["items"]["required"] == ["engines", "query"]
    assert "required" not in schema.PLAN_JSON_SCHEMA["properties"]["date"]


def test_minimal_model_output_still_gives_a_valid_plan():
    plan, warnings = schema.plan_from_raw({"intent": "find", "clauses": [{"engines": ["visual"], "query": "sunset"}]})
    assert not warnings and plan.scope == "library" and plan.match == "all" and plan.date.is_empty
    assert plan.clauses[0].exclude is False
