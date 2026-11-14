import json

from kit import extract

from library import casebook


def _doc(conn, name, text, facts=None):
    cur = conn.execute("INSERT INTO documents (name, sha256, kind, text, facts, judged) VALUES (?,?,?,?,?,1)", (name, name, "x", text, json.dumps(facts or {})))
    return cur.lastrowid


def test_pieces_sharing_a_distinctive_number_are_one_matter_and_others_stand_alone():
    pieces = [
        {"id": 1, "name": "mail/a", "text": "Invoice INV-20931 due 5 June 120.50"},
        {"id": 2, "name": "scan.pdf", "text": "Reminder for INV-20931 overdue 120.50"},
        {"id": 3, "name": "other.pdf", "text": "A recipe for soup"},
    ]
    groups, undecided = casebook.link(pieces, lambda a, b: True)
    assert sorted(groups) == [[1, 2], [3]] and not undecided


def test_a_common_value_does_not_glue_unrelated_pieces():
    pieces = [{"id": i, "name": f"f{i}", "text": "REF-77777 hello"} for i in range(1, 8)]
    assert casebook.candidates(pieces) == []


def test_claims_without_a_real_quote_are_dropped(monkeypatch):
    answer = {
        "title": "Rent",
        "what": "Rent for May",
        "open": True,
        "status": "unpaid",
        "status_piece": 1,
        "status_quote": "not paid yet",
        "amounts": [
            {"label": "rent", "value": "900.00", "piece": 1, "quote": "900.00 due"},
            {"label": "fake", "value": "5.00", "piece": 1, "quote": "never said"},
        ],
        "dates": [],
    }
    monkeypatch.setattr(extract, "_ask", lambda *a, **k: answer)
    out = casebook.synthesize(None, "m", [{"id": 1, "name": "a", "text": "Rent 900.00 due, not paid yet"}])
    assert [a["value"] for a in out["amounts"]] == ["900.00"]
    assert out["status"] == "unpaid"


def test_a_matter_is_understood_once_and_read_again_only_when_it_changes(conn, monkeypatch):
    _doc(conn, "a", "Invoice INV-20931 for 120.50")
    _doc(conn, "b", "Reminder INV-20931 amount 120.50")
    calls = []

    def ask(client, model, system, body, schema):
        if "same" in schema["properties"]:
            return {"same": True, "quote_a": "INV-20931", "quote_b": "INV-20931"}
        calls.append(1)
        return {"title": "Invoice", "what": "An invoice"}

    monkeypatch.setattr(extract, "_ask", ask)
    assert casebook.rebuild(conn, object(), "m") == 2  # one new matter and one answer about which pieces belong together
    assert casebook.understand_pending(conn, None, "m") == 1
    assert casebook.rebuild(conn, object(), "m") == 0
    assert casebook.understand_pending(conn, None, "m") == 0
    assert len(calls) == 1
    assert conn.execute("SELECT COUNT(*) FROM documents WHERE case_id IS NOT NULL").fetchone()[0] == 2


def test_a_long_matter_is_read_completely_in_several_calls_and_conflicting_statuses_are_kept(monkeypatch):
    seen = []

    def ask(client, model, system, body, schema):
        seen.append(body)
        return {"title": "Big", "what": "Big matter", "status": f"s{len(seen)}", "status_piece": 1, "status_quote": "word", "open": True}

    monkeypatch.setattr(extract, "_ask", ask)
    text = "x " + "word " * 5000
    out = casebook.synthesize(None, "m", [{"id": 1, "name": "a", "text": text}, {"id": 2, "name": "b", "text": "tiny x"}])
    assert len(seen) > 1
    assert all(w in ("word", "x", "tiny") or not w for b in seen for w in b.replace("[P1] a", "").replace("[P2] b", "").split())  # no word was cut in half
    assert text[-40:].strip() in " ".join(seen)  # the very end was read too
    assert out["coverage"] == 1.0 and out["conflict"] is True and "s1" in out["status"] and "s2" in out["status"]


def test_a_link_needs_confirmation_from_the_texts_and_an_undecided_one_holds_the_pieces_back():
    pieces = [
        {"id": 1, "name": "a", "text": "Invoice INV-20931 120.50"},
        {"id": 2, "name": "b", "text": "Reminder INV-20931 120.50"},
        {"id": 3, "name": "c", "text": "soup"},
    ]
    assert casebook.link(pieces, lambda a, b: False) == ([[1], [2], [3]], set())  # the texts say they are not one matter
    groups, undecided = casebook.link(pieces, lambda a, b: None)  # not yet decided: never shown on a guess
    assert groups == [[3]] and undecided == {1, 2}


def test_the_model_must_quote_both_pieces_to_confirm(monkeypatch):
    a, b = {"name": "a", "text": "Invoice INV-20931"}, {"name": "b", "text": "Reminder INV-20931"}
    monkeypatch.setattr(extract, "_ask", lambda *x, **k: {"same": True, "quote_a": "INV-20931", "quote_b": "INV-20931"})
    assert casebook.confirm(None, "m", a, b) is True
    monkeypatch.setattr(extract, "_ask", lambda *x, **k: {"same": True, "quote_a": "INV-20931", "quote_b": "made up"})
    assert casebook.confirm(None, "m", a, b) is False


def test_the_read_button_finishes_every_matter_in_rounds_and_stops_when_nothing_more_changes(conn, monkeypatch):
    from library import store

    for i in range(8):  # more matters than one round handles
        _doc(conn, f"f{i}", f"Letter about subject{i} reference REF-{i}0000")
    monkeypatch.setattr(extract, "_ask", lambda *a, **k: {"title": "Letter", "what": "A letter"})
    assert store.finish_matters(conn, object(), "m") == 8
    assert conn.execute("SELECT COUNT(*) FROM cases WHERE summary=''").fetchone()[0] == 0
    stop = store.finish_matters(conn, object(), "m", lambda: "stop")
    assert stop == 0
