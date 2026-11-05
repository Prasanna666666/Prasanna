import json

from atlas.assistant import clean_history, match_by_words


def chat(running, text, history=None, origin=True, header=True):
    headers = {}
    if origin:
        headers["Origin"] = f"http://atlas.localhost:{running.port}"
    if header:
        headers["X-Atlas"] = "1"
    body = json.dumps({"text": text, "conv": "t", "history": history or []}).encode()
    status, _, data = running.request("POST", "/_atlas/api/chat", f"atlas.localhost:{running.port}", body, headers)
    return status, json.loads(data) if data.startswith(b"{") else data


def test_a_question_is_matched_to_the_app_whose_own_words_it_uses(running):
    modules = list(running.atlas.modules.values())
    assert [m.id for m in match_by_words("How much did I spend on money stuff?", modules)] == ["money"]
    assert [m.id for m in match_by_words("show me a PHOTO of the beach", modules)] == ["photos"]
    assert [m.id for m in match_by_words("my photo and money from India", modules)] == ["money", "photos"]
    assert match_by_words("hello there", modules) == []
    assert match_by_words("photographer", modules) == []  # whole words only


def test_history_keeps_only_well_formed_recent_turns():
    raw = [["user", "a"], ["assistant", "b"], ["system", "x"], "junk", ["user", 5]] + [["user", str(i)] for i in range(20)]
    cleaned = clean_history(raw)
    assert len(cleaned) == 8 and cleaned[-1] == ["user", "19"] and all(r in ("user", "assistant") for r, _ in cleaned)


def test_one_question_is_answered_by_the_app_it_is_about_and_says_which(running):
    status, reply = chat(running, "how much money did I spend?")
    assert status == 200 and reply["how"] == "words" and reply["routed"] == ["money"]
    part = reply["parts"][0]
    assert part["module"] == "money" and part["name"] == "Money" and part["text"] == "answer to: how much money did I spend?" and part["ok"] is True
    assert running.apps["photos"].asked == []  # the other app was never asked


def test_a_question_about_two_apps_asks_both_and_returns_one_part_each(running):
    status, reply = chat(running, "my photo and my money from India", history=[["user", "hi"], ["assistant", "hello"]])
    assert status == 200 and reply["routed"] == ["money", "photos"] and [p["module"] for p in reply["parts"]] == ["money", "photos"]
    assert running.apps["money"].asked[0]["history"] == [["user", "hi"], ["assistant", "hello"]]  # the conversation so far reaches the app
    photos = reply["parts"][1]
    assert photos["total"] == 41 and photos["notes"] == ["one note"]
    assert photos["items"] == [{"kind": "photo", "thumb": "/_atlas/api/media/photos/api/photo/1/thumb", "link": "#/library"}]  # the unsafe path was dropped


def test_when_the_words_do_not_say_the_model_picks_the_app(running):
    running.apps[
        "photos"
    ].plan_reply = '{"apps": ["photos"], "chat": false, "show": {"photos": false, "documents": false}}'  # the fake server doubles as the model
    status, reply = chat(running, "anything from last summer?")
    assert reply["how"] == "model" and reply["routed"] == ["photos"] and running.apps["photos"].asked


def test_plain_conversation_is_answered_by_the_model_without_asking_any_app(running):
    running.apps["photos"].plan_reply = '{"apps": [], "chat": true, "show": {}}'
    running.apps["photos"].model_reply = "Hello! What can I help with?"
    status, reply = chat(running, "hello")
    assert reply["how"] == "model" and reply["routed"] == [] and reply["parts"][0]["text"] == "Hello! What can I help with?"
    assert running.apps["money"].asked == [] and running.apps["photos"].asked == []
    system = running.apps["photos"].model_calls[-1]["messages"][0]["content"]
    assert "cannot see any of their data" in system and running.apps["photos"].model_calls[-1]["options"]["num_ctx"] == 4096


def test_without_the_model_an_unclear_question_says_so_instead_of_guessing(running):
    running.atlas.assistant.model.url = "http://127.0.0.1:1"
    status, reply = chat(running, "hello")
    assert reply["how"] == "unsure" and reply["parts"][0]["ok"] is False and "Try saying which" in reply["parts"][0]["error"]
    status, reply = chat(running, "how much money did I spend?")  # a clear question still works: the apps do not need Atlas's model
    assert reply["parts"][0]["ok"] is True


def test_an_app_that_is_down_answers_with_a_plain_error_and_the_other_still_answers(running):
    running.apps["money"].close()
    status, reply = chat(running, "my photo and my money")
    by = {p["module"]: p for p in reply["parts"]}
    assert by["money"]["ok"] is False and "not running" in by["money"]["error"] and by["photos"]["ok"] is True


def test_only_the_pages_own_origin_and_header_can_ask_and_the_message_must_not_be_empty(running):
    assert chat(running, "x", origin=False)[0] == 403
    assert chat(running, "x", header=False)[0] == 403
    assert chat(running, "   ")[0] == 400
    assert running.apps["money"].asked == [] and running.apps["photos"].asked == []


def test_pictures_come_through_atlas_and_only_from_the_apps_declared_picture_path(running):
    status, headers, data = running.shell("/_atlas/api/media/photos/api/photo/1/thumb")
    assert status == 200 and headers["content-type"] == "image/png" and data.startswith(b"\x89PNG") and headers["cache-control"] == "private, max-age=3600"
    assert running.shell("/_atlas/api/media/photos/etc/passwd")[0] == 404
    assert running.shell("/_atlas/api/media/photos/api/photo/../secret")[0] == 404
    assert running.shell("/_atlas/api/media/money/api/photo/1/thumb")[0] == 404  # this app declares no pictures
    assert running.shell("/_atlas/api/media/nothing/x")[0] == 404


def test_a_plan_that_is_not_the_expected_shape_falls_back_to_simple_word_rules(running):
    for broken in ("Hello! I can look up your money or your photos.", "[1, 2]", '{"apps": "photos"}'):
        running.apps["photos"].plan_reply = broken
        _, reply = chat(running, "hello")
        assert reply["how"] == "unsure" and reply["routed"] == []  # nothing in the words either: it says so instead of guessing
        _, reply = chat(running, "how much money did I spend?")
        assert reply["how"] == "words" and reply["routed"] == ["money"]
    assert running.apps["photos"].asked == []


def test_the_model_may_name_several_apps(running):
    running.apps["photos"].plan_reply = '{"apps": ["money", "photos"], "chat": false, "show": {}}'
    assert chat(running, "anything from last summer?")[1]["routed"] == ["money", "photos"]


def test_the_model_decides_what_to_show_not_a_word_list(running):
    plan = '{"apps": ["photos"], "chat": false, "show": {"photos": %s, "documents": false}}'
    running.apps["photos"].plan_reply = plan % "true"
    _, reply = chat(running, "I would love to see Goa again")  # no showing word anywhere: the words alone would say no
    assert reply["how"] == "model" and reply["show"]["photos"] is True and reply["parts"][0]["show"]["photos"] is True
    running.apps["photos"].plan_reply = plan % "false"
    _, reply = chat(running, "what is the best way to send pictures to my mum?")  # showing words and a picture word: the words alone would say yes
    assert reply["show"]["photos"] is False


def test_only_real_booleans_and_known_apps_are_accepted_from_the_model(running):
    running.apps["photos"].plan_reply = '{"apps": ["photos", "bank"], "chat": false, "show": {"photos": "yes", "documents": 1}}'
    _, reply = chat(running, "anything from last summer?")
    assert reply["routed"] == ["photos"] and reply["show"] == {"photos": False, "documents": False}


def test_the_planner_sees_the_conversation_so_that_show_me_those_works(running):
    running.apps["photos"].plan_reply = '{"apps": ["photos"], "chat": false, "show": {"photos": true}}'
    chat(running, "show me those", history=[["user", "how many beach shots do I have?"], ["assistant", "41"]])
    sent = running.apps["photos"].model_calls[-1]
    assert (
        sent["format"] == "json" and "how many beach shots do I have?" in sent["messages"][1]["content"] and "show me those" in sent["messages"][1]["content"]
    )


def test_a_question_an_app_recognises_is_answered_instantly_with_no_model_call(running):
    running.apps["photos"].plan_reply = '{"apps": ["photos"], "chat": false, "show": {}}'
    status, reply = chat(running, "tell me exactly what I spent")
    assert reply["how"] == "instant" and reply["routed"] == ["money"] and reply["parts"][0]["text"] == "the exact answer"
    assert running.apps["photos"].model_calls == []  # the model was never asked: not to plan, not to answer
    assert running.apps["money"].asked == [] and running.apps["photos"].asked == []  # and no app's assistant ran either


def test_every_app_is_asked_whether_it_recognises_the_question_before_the_model_plans(running):
    running.apps["photos"].plan_reply = '{"apps": ["money"], "chat": false, "show": {}}'
    _, reply = chat(running, "anything from last summer?")
    assert running.apps["money"].fast_calls == ["anything from last summer?"] and running.apps["photos"].fast_calls == ["anything from last summer?"]
    assert reply["how"] == "model" and reply["routed"] == ["money"] and running.apps["money"].asked  # nobody recognised it, so the model planned


def test_the_model_supplies_search_phrasings_in_both_languages_and_they_reach_the_app(running):
    running.apps["photos"].plan_reply = json.dumps(
        {"apps": ["money"], "chat": False, "show": {"documents": True}, "search": ["flight", " vlucht ", "reservering", "ticket", "a fifth is dropped", 7, ""]}
    )
    _, reply = chat(running, "show me the email about my flight")
    assert running.apps["money"].asked[-1]["search"] == ["flight", "vlucht", "reservering", "ticket"]  # strings only, trimmed, at most four
    assert reply["parts"][0]["show"]["documents"] is True


def test_without_a_model_there_are_no_extra_phrasings_and_the_literal_words_are_used(running):
    running.atlas.assistant.model.url = "http://127.0.0.1:1"
    chat(running, "show me the money invoices")
    assert running.apps["money"].asked[-1]["search"] == []
