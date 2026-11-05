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
    running.apps["photos"].model_reply = "photos"  # the fake server doubles as the model
    status, reply = chat(running, "anything from last summer?")
    assert reply["how"] == "model" and reply["routed"] == ["photos"] and running.apps["photos"].asked


def test_plain_conversation_is_answered_by_the_model_without_asking_any_app(running):
    running.apps["photos"].model_reply = "Hello! What can I help with?"
    status, reply = chat(running, "hello")
    assert reply["how"] == "chat" and reply["routed"] == [] and reply["parts"][0]["text"] == "Hello! What can I help with?"
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


def test_a_rambling_answer_from_the_model_is_treated_as_chat_not_as_a_choice_of_app(running):
    running.apps["photos"].model_reply = "Hello! I can look up your money or your photos. What would you like?"
    status, reply = chat(running, "hello")
    assert reply["how"] == "chat" and reply["routed"] == [] and running.apps["money"].asked == [] and running.apps["photos"].asked == []


def test_the_model_may_name_several_apps_or_both(running):
    running.apps["photos"].model_reply = "money, photos"
    assert chat(running, "anything from last summer?")[1]["routed"] == ["money", "photos"]
    running.apps["photos"].model_reply = "both"
    assert chat(running, "anything from last summer?")[1]["routed"] == ["money", "photos"]
