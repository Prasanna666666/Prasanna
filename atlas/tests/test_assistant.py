import json

from atlas.assistant import clean_history


def chat(running, text, history=None, origin=True, header=True):
    headers = {}
    if origin:
        headers["Origin"] = f"http://atlas.localhost:{running.port}"
    if header:
        headers["X-Atlas"] = "1"
    body = json.dumps({"text": text, "conv": "t", "history": history or []}).encode()
    status, _, data = running.request("POST", "/_atlas/api/chat", f"atlas.localhost:{running.port}", body, headers)
    return status, json.loads(data) if data.startswith(b"{") else data


def test_history_keeps_only_well_formed_recent_turns():
    raw = [["user", "a"], ["assistant", "b"], ["system", "x"], "junk", ["user", 5]] + [["user", str(i)] for i in range(20)]
    cleaned = clean_history(raw)
    assert len(cleaned) == 8 and cleaned[-1] == ["user", "19"] and all(r in ("user", "assistant") for r, _ in cleaned)


def tool(name, **properties):
    return {"name": name, "description": f"the {name} tool", "parameters": {"type": "object", "properties": {k: {"type": "string"} for k in properties}}}


def call(name, **args):
    return {"content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}


def text(content):
    return {"content": content}


def loop_calls(app):
    """The calls of the answering loop (not the question of which tools to carry)."""
    return [c for c in app.model_calls if not isinstance(c.get("format"), dict)]


def offered(app_call):
    return {t["function"]["name"] for t in app_call.get("tools", [])}


def test_a_question_uses_the_tool_it_needs_and_the_answer_says_which_part_was_used(running):
    money, photos = running.apps["money"], running.apps["photos"]
    money.tools = [tool("spending_between", **{"from": 1, "to": 1})]
    money.tool_results["spending_between"] = {"ok": True, "data": {"spent": 290.0, "payments": 2}}
    photos.script = [call("money__spending_between", **{"from": "2026-01-12", "to": "2026-01-30"}), text("You spent 290.00 in those days.")]
    status, reply = chat(running, "what did I spend between 12 and 30 January?")
    assert status == 200 and reply["how"] == "agent" and reply["routed"] == ["money"]
    assert reply["parts"][0]["text"] == "You spent 290.00 in those days." and money.asked[-1]["args"] == {"from": "2026-01-12", "to": "2026-01-30"}
    assert money.asked[-1]["user_text"] == "what did I spend between 12 and 30 January?"
    assert "money__spending_between" in offered(loop_calls(photos)[0])


def test_one_answer_can_chain_tools_of_different_parts(running):
    money, photos = running.apps["money"], running.apps["photos"]
    money.tools = [tool("trip_dates", place=1)]
    money.tool_results["trip_dates"] = {"ok": True, "data": {"start": "2026-01-12", "end": "2026-01-30"}}
    photos.tools = [tool("find_photos", request=1, show=1)]
    photos.tool_results["find_photos"] = {"ok": True, "data": {"count": 41}, "items": [{"kind": "photo", "thumb": "/api/photo/1/thumb", "link": "#/library"}]}
    photos.script = [
        call("money__trip_dates", place="India"),
        call("photos__find_photos", request="taken between 2026-01-12 and 2026-01-30", show=True),
        text("Here are your India photos: 41 of them."),
    ]
    status, reply = chat(running, "show me the photos of my India trip")
    assert reply["routed"] == ["money", "photos"] and reply["show"] == {"photos": True, "documents": False}
    assert reply["parts"][0]["items"] == [
        {"kind": "photo", "thumb": "/_atlas/api/media/photos/api/photo/1/thumb", "link": "#/library", "module": "photos"}
    ]  # each item says which part it came from
    second = loop_calls(photos)[1]["messages"]
    assert any(m["role"] == "tool" and "2026-01-12" in m["content"] for m in second)  # the result of the first tool reached the model before the second call


def test_pictures_are_shown_only_when_the_model_says_the_person_asked_to_see_them(running):
    photos = running.apps["photos"]
    photos.tools = [tool("find_photos", request=1, show=1)]
    photos.tool_results["find_photos"] = {"ok": True, "data": {"count": 41}, "items": [{"kind": "photo", "thumb": "/api/photo/1/thumb", "link": "#/library"}]}
    photos.script = [call("photos__find_photos", request="beach"), text("You have 41 beach photos.")]
    _, reply = chat(running, "how many beach photos do I have?")
    assert reply["parts"][0]["items"] == [] and reply["show"] == {"photos": False, "documents": False}


def test_plain_conversation_uses_no_tool(running):
    running.apps["money"].tools = [tool("spending_between")]
    running.apps["photos"].script = [text("Hello! What can I help with?")]
    _, reply = chat(running, "hello")
    assert reply["routed"] == [] and reply["parts"][0]["text"] == "Hello! What can I help with?" and running.apps["money"].asked == []


def test_the_conversation_so_far_reaches_the_model(running):
    running.apps["photos"].script = [text("Those are from Goa.")]
    chat(running, "show me those", history=[["user", "how many beach shots do I have?"], ["assistant", "41"]])
    sent = loop_calls(running.apps["photos"])[0]["messages"]
    assert [m["content"] for m in sent[1:]] == ["how many beach shots do I have?", "41", "show me those"]


def test_without_the_model_the_answer_says_so_and_nothing_is_guessed(running):
    running.atlas.assistant.model.url = "http://127.0.0.1:1"
    _, reply = chat(running, "how much money did I spend?")
    assert reply["how"] == "down" and reply["routed"] == [] and "not running" in reply["parts"][0]["error"]
    assert running.apps["money"].asked == []


def test_a_part_that_is_down_gives_the_model_a_plain_error_and_the_rest_still_works(running):
    money, photos = running.apps["money"], running.apps["photos"]
    money.tools, photos.tools = [tool("spending_between")], [tool("find_photos")]
    running.atlas.assistant.tools()  # both parts are known while they are up
    money.close()
    photos.script = [call("money__spending_between"), call("photos__find_photos", request="x"), text("I could not reach your money, but you have 41 photos.")]
    _, reply = chat(running, "money and photos please")
    tool_messages = [m["content"] for m in loop_calls(photos)[1]["messages"] if m["role"] == "tool"]
    assert "not running" in tool_messages[0] and reply["parts"][0]["ok"] is True and "41 photos" in reply["parts"][0]["text"]


def test_a_figure_no_tool_returned_is_corrected_once_and_refused_if_it_stays(running):
    money, photos = running.apps["money"], running.apps["photos"]
    money.tools = [tool("spending_between")]
    money.tool_results["spending_between"] = {"ok": True, "data": {"spent": 290.0}}
    photos.script = [call("money__spending_between"), text("You spent 1,234.56."), text("You spent 290.00.")]
    _, reply = chat(running, "how much did I spend?")
    assert reply["parts"][0]["text"] == "You spent 290.00." and "1234.56" in loop_calls(photos)[2]["messages"][-1]["content"].replace(",", "")
    photos.script = [call("money__spending_between"), text("You spent 1,234.56."), text("Still 1,234.56.")]
    _, reply = chat(running, "how much did I spend?")
    assert reply["parts"][0]["ok"] is False and "can't give you that figure" in reply["parts"][0]["error"] and "Still" not in reply["parts"][0]["error"]


def test_a_delete_tool_is_offered_only_when_the_person_used_a_delete_word(running):
    money, photos = running.apps["money"], running.apps["photos"]
    money.tools = [tool("spending_between"), tool("delete_person", id=1)]
    photos.script = [text("ok")]
    chat(running, "who is Amma?")
    assert "money__delete_person" not in offered(loop_calls(photos)[0]) and "money__spending_between" in offered(loop_calls(photos)[0])
    running.atlas.assistant._tools = None
    photos.script = [text("ok")]
    chat(running, "please delete Amma")
    assert "money__delete_person" in offered(loop_calls(photos)[-1])


def test_a_tool_the_model_invents_is_refused(running):
    photos = running.apps["photos"]
    photos.script = [call("money__format_disk"), text("Sorry, I cannot do that.")]
    chat(running, "do something")
    assert any(m["role"] == "tool" and "not available" in m["content"] for m in loop_calls(photos)[1]["messages"]) and running.apps["money"].asked == []


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


def test_notes_a_part_attaches_to_its_figures_are_shown_with_the_answer(running):
    money, photos = running.apps["money"], running.apps["photos"]
    money.tools = [tool("spending_summary")]
    money.tool_results["spending_summary"] = {"ok": True, "data": {"spent": 850.0}, "notes": ["October 2026 is NOT PROVEN: a file is missing."]}
    photos.script = [call("money__spending_summary"), text("You spent 850.00.")]
    _, reply = chat(running, "how much did I spend in October?")
    assert reply["parts"][0]["notes"] == ["October 2026 is NOT PROVEN: a file is missing."]


def test_only_the_tools_the_model_chose_are_described_to_it_and_the_index_lists_every_tool(running):
    money, photos = running.apps["money"], running.apps["photos"]
    money.tools = [tool("spending_between"), tool("net_worth")]
    photos.tools = [tool("find_photos")]
    photos.pick = ["money__net_worth"]
    photos.script = [text("ok")]
    chat(running, "what is my net worth?")
    choosing = next(c for c in photos.model_calls if isinstance(c.get("format"), dict))
    index = choosing["messages"][0]["content"]
    assert all(name in index for name in ("money__spending_between", "money__net_worth", "photos__find_photos"))  # the index shows every tool, in one line each
    assert offered(loop_calls(photos)[0]) == {"money__net_worth"}  # but only the chosen one is carried into the answer


def test_a_tool_name_the_model_makes_up_when_choosing_is_ignored(running):
    money, photos = running.apps["money"], running.apps["photos"]
    money.tools = [tool("net_worth")]
    photos.pick = ["money__net_worth", "money__format_disk"]
    photos.script = [text("ok")]
    chat(running, "hello")
    assert offered(loop_calls(photos)[0]) == {"money__net_worth"}


def test_a_change_waiting_for_the_person_is_always_shown_as_a_card_from_the_part_that_prepared_it(running):
    money, photos = running.apps["money"], running.apps["photos"]
    money.tools = [tool("preview_move_pictures", folder=1)]
    money.tool_results["preview_move_pictures"] = {
        "ok": True,
        "data": {"change_id": "abc", "status": "NOT DONE"},
        "items": [{"kind": "confirm", "title": "Confirm: move 3 pictures", "subtitle": "Waiting for you.", "link": "#/changes?id=abc"}],
    }
    photos.script = [call("money__preview_move_pictures", folder="Goa"), text("It is ready: please review and confirm it.")]
    _, reply = chat(running, "move the Goa photos to a folder")  # no show: a card that needs the person is never hidden
    assert reply["parts"][0]["items"] == [
        {"kind": "confirm", "title": "Confirm: move 3 pictures", "subtitle": "Waiting for you.", "link": "#/changes?id=abc", "module": "money"}
    ]
    assert reply["show"] == {"photos": False, "documents": False}


def test_each_question_has_its_own_turn_id_that_reaches_the_part(running):
    money, photos = running.apps["money"], running.apps["photos"]
    money.tools = [tool("find_things")]
    for _ in range(2):
        photos.script = [call("money__find_things"), text("ok")]
        chat(running, "find things")
    first, second = money.asked[-2], money.asked[-1]
    assert first["turn"] and second["turn"] and first["turn"] != second["turn"]
