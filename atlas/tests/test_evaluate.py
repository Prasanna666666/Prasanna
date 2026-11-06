import json

from atlas.evaluate import handled, load_cases, main, percentile, run, summarise, unreachable


def test_the_shipped_cases_cover_five_levels_and_say_what_each_expects():
    cases = load_cases(__import__("atlas.evaluate", fromlist=["DEFAULT_CASES"]).DEFAULT_CASES)
    assert {c["level"] for c in cases} == {1, 2, 3, 4, 5} and len(cases) >= 25
    for c in cases:
        assert set(c["expect"]) == {"apps", "chat", "show"} and set(c["expect"]["apps"]) <= {"finance", "documents"}


def test_a_case_is_handled_when_the_needed_parts_were_used_and_showing_was_asked_only_when_wanted():
    see = {"apps": ["documents"], "chat": False, "show": True}
    assert handled({"routed": ["documents"], "asked_to_show": True}, see)
    assert handled({"routed": ["documents", "finance"], "asked_to_show": True}, see)  # chaining uses more parts: fine
    assert not handled({"routed": ["documents"], "asked_to_show": False}, see)  # not asked to show when it should be
    assert not handled({"routed": ["finance"], "asked_to_show": True}, see)  # the needed part was not used
    assert not handled({"routed": ["documents"], "asked_to_show": True}, {**see, "show": False})  # shown when only a count was asked
    assert handled({"routed": []}, {"apps": [], "chat": True, "show": False})
    assert not handled({"routed": ["finance"]}, {"apps": [], "chat": True, "show": False})  # plain chat used a tool
    assert not handled(None, see)


def test_the_run_scores_real_questions_through_a_running_atlas_and_times_them(running):
    photos, money = running.apps["photos"], running.apps["money"]
    money.tools = [{"name": "spending_between", "description": "d", "parameters": {"type": "object", "properties": {}}}]
    money.tool_results["spending_between"] = {"ok": True, "data": {"spent": 5.0}}
    photos.script = [{"content": "", "tool_calls": [{"function": {"name": "money__spending_between", "arguments": {}}}]}, {"content": "5.00"}]
    cases = [{"level": 1, "text": "how much did I spend?", "expect": {"apps": ["money"], "chat": False, "show": False}}]
    results = run(f"http://atlas.localhost:{running.port}", cases)
    assert results[0]["ok"] is True and results[0]["answered"] is True and results[0]["seconds"] >= 0
    rows = summarise(results)
    assert [(r["level"], r["cases"], r["right"]) for r in rows] == [(1, 1, 1.0)]
    assert run("http://atlas.localhost:1", cases)[0]["ok"] is False  # not reachable: counted as wrong, not a crash


def test_percentiles():
    assert percentile([], 95) == 0.0 and percentile([3.0, 1.0, 2.0], 50) == 2.0 and percentile([1.0, 2.0, 3.0, 4.0], 95) == 4.0
    json.dumps(percentile([1.0], 50))


def test_a_stopped_app_is_reported_as_such_not_as_wrong_answers(capsys):
    assert "Is the app running" in unreachable("http://atlas.localhost:1")
    assert main(["--live", "http://atlas.localhost:1"]) == 2 and "Cannot evaluate" in capsys.readouterr().out
