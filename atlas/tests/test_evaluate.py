import json

from atlas.evaluate import DEFAULT_CASES, load_cases, percentile, run_live, run_understanding, summarise, understood


def test_the_shipped_cases_are_well_formed_and_cover_every_level():
    cases = load_cases(DEFAULT_CASES)
    assert {c["level"] for c in cases} == {1, 2, 3, 4, 5} and len(cases) >= 25
    for c in cases:
        assert set(c["expect"]) == {"apps", "chat", "photos", "documents"} and set(c["expect"]["apps"]) <= {"finance", "photos"}
        assert c["expect"]["chat"] == (not c["expect"]["apps"])  # plain conversation means no app
        assert all(r in ("user", "assistant") for r, _ in c.get("history", []))


def test_a_plan_is_understood_only_when_apps_conversation_and_what_to_show_are_all_right(running):
    assistant = running.atlas.assistant
    running.apps["photos"].plan_reply = '{"apps": ["photos"], "chat": false, "show": {"photos": true, "documents": false}}'
    plan = assistant.model_plan("show me photos", [])
    assert understood(plan, {"apps": ["photos"], "chat": False, "photos": True, "documents": False})
    assert not understood(plan, {"apps": ["photos"], "chat": False, "photos": False, "documents": False})  # shown when it should not be
    assert not understood(plan, {"apps": ["money"], "chat": False, "photos": True, "documents": False})
    assert not understood(None, {"apps": [], "chat": True, "photos": False, "documents": False})


def test_the_understanding_run_scores_the_model_against_the_word_rules_and_times_it(running):
    running.apps["photos"].plan_reply = '{"apps": ["money"], "chat": false, "show": {}}'
    cases = [
        {"level": 1, "text": "how much money did I spend?", "expect": {"apps": ["money"], "chat": False, "photos": False, "documents": False}},
        {"level": 2, "text": "I would love to see the beach", "expect": {"apps": ["photos"], "chat": False, "photos": True, "documents": False}},
    ]
    results = run_understanding(running.atlas.assistant, cases)
    assert [r["model_ok"] for r in results] == [True, False] and results[0]["words_ok"] is True and results[1]["words_ok"] is False
    rows = summarise(results)
    assert [(r["level"], r["cases"], r["model"]) for r in rows] == [(1, 1, 1.0), (2, 1, 0.0)] and rows[0]["p50"] >= 0


def test_a_model_that_does_not_answer_is_counted_as_wrong_not_as_a_crash(running):
    running.atlas.assistant.model.url = "http://127.0.0.1:1"
    results = run_understanding(
        running.atlas.assistant, [{"level": 1, "text": "hello", "expect": {"apps": [], "chat": True, "photos": False, "documents": False}}]
    )
    assert results[0]["model_ok"] is False and results[0]["model_answered"] is False and summarise(results)[0]["p50"] == 0.0


def test_live_questions_report_which_path_answered_and_how_long(running):
    cases = [{"level": 1, "text": "tell me exactly what I spent"}, {"level": 2, "text": "how much money did I spend?"}]
    out = run_live(f"http://atlas.localhost:{running.port}", cases)
    assert [r["how"] for r in out] == ["instant", "words"] and all(r["answered"] >= 1 and r["seconds"] >= 0 for r in out)
    assert run_live("http://atlas.localhost:1", cases[:1])[0]["how"] == "unreachable"


def test_percentiles():
    assert percentile([], 95) == 0.0 and percentile([3.0, 1.0, 2.0], 50) == 2.0 and percentile([1.0, 2.0, 3.0, 4.0], 95) == 4.0
    json.dumps(percentile([1.0], 50))
