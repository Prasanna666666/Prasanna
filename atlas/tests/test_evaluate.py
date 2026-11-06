import json

from atlas.evaluate import handled, load_cases, percentile, run, summarise


def test_the_shipped_cases_cover_five_levels_and_say_what_each_expects():
    cases = load_cases(__import__("atlas.evaluate", fromlist=["DEFAULT_CASES"]).DEFAULT_CASES)
    assert {c["level"] for c in cases} == {1, 2, 3, 4, 5} and len(cases) >= 25
    for c in cases:
        assert set(c["expect"]) == {"apps", "chat", "photos", "documents"} and set(c["expect"]["apps"]) <= {"finance", "photos", "documents"}


def test_a_case_is_handled_when_the_needed_parts_were_used_and_pictures_were_shown_only_when_asked():
    ask_for_photos = {"apps": ["photos"], "chat": False, "photos": True, "documents": False}
    assert handled({"routed": ["photos"], "show": {"photos": True}}, ask_for_photos)
    assert handled({"routed": ["documents", "photos"], "show": {"photos": True}}, ask_for_photos)  # chaining uses more parts: fine
    assert not handled({"routed": ["photos"], "show": {"photos": False}}, ask_for_photos)  # not shown when it should be
    assert not handled({"routed": ["finance"], "show": {"photos": True}}, ask_for_photos)  # the needed part was not used
    assert handled({"routed": [], "show": {}}, {"apps": [], "chat": True, "photos": False, "documents": False})
    assert not handled({"routed": ["finance"], "show": {}}, {"apps": [], "chat": True, "photos": False, "documents": False})  # plain chat used a tool
    assert not handled(None, ask_for_photos)


def test_the_run_scores_real_questions_through_a_running_atlas_and_times_them(running):
    photos, money = running.apps["photos"], running.apps["money"]
    money.tools = [{"name": "spending_between", "description": "d", "parameters": {"type": "object", "properties": {}}}]
    money.tool_results["spending_between"] = {"ok": True, "data": {"spent": 5.0}}
    photos.script = [{"content": "", "tool_calls": [{"function": {"name": "money__spending_between", "arguments": {}}}]}, {"content": "5.00"}]
    cases = [{"level": 1, "text": "how much did I spend?", "expect": {"apps": ["money"], "chat": False, "photos": False, "documents": False}}]
    results = run(f"http://atlas.localhost:{running.port}", cases)
    assert results[0]["ok"] is True and results[0]["answered"] is True and results[0]["seconds"] >= 0
    rows = summarise(results)
    assert [(r["level"], r["cases"], r["right"]) for r in rows] == [(1, 1, 1.0)]
    assert run("http://atlas.localhost:1", cases)[0]["ok"] is False  # not reachable: counted as wrong, not a crash


def test_percentiles():
    assert percentile([], 95) == 0.0 and percentile([3.0, 1.0, 2.0], 50) == 2.0 and percentile([1.0, 2.0, 3.0, 4.0], 95) == 4.0
    json.dumps(percentile([1.0], 50))


def test_a_stopped_app_is_reported_as_such_not_as_wrong_answers(capsys):
    assert "Is the app running" in evaluate.unreachable("http://atlas.localhost:1")
    assert evaluate.main(["--live", "http://atlas.localhost:1"]) == 2 and "Cannot evaluate" in capsys.readouterr().out
