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


def test_the_audit_says_final_only_when_nothing_is_left(conn, monkeypatch):
    from library import store

    _doc(conn, "a", "Letter about subject reference REF-10000")
    assert store.audit(conn)["not_grouped"] == 1 and store.audit_line(store.audit(conn)).startswith(
        "Still left: 1 sorted files not yet placed in a group of related files"
    )
    monkeypatch.setattr(extract, "_ask", lambda *a, **k: {"title": "Letter", "what": "A letter"})
    store.finish_matters(conn, object(), "m")
    assert store.audit_line(store.audit(conn)).startswith("Nothing is left: 1 files sorted, in 1 groups of related files")


def test_a_lone_file_costs_no_model_call_and_a_file_with_a_date_to_act_on_is_read_by_the_model(conn, monkeypatch):
    from library import store

    _doc(conn, "lone", "A newsletter about gardens")
    _doc(conn, "bill", "Invoice for internet", {"due_date": "2026-12-01", "kind": "invoice"})
    calls = []
    monkeypatch.setattr(extract, "_ask", lambda *a, **k: calls.append(a[3]) or {"title": "Internet bill", "what": "A bill", "open": False})
    assert store.finish_matters(conn, object(), "m") == 2
    assert len(calls) == 1 and "Invoice for internet" in calls[0]  # only the file with a date was sent to the model


def test_a_stop_pressed_during_the_final_step_ends_it_before_the_next_model_call(conn, monkeypatch):
    from library import store

    for i in range(3):
        _doc(conn, f"b{i}", f"Invoice number {i}", {"due_date": "2026-12-01"})
    calls = []
    monkeypatch.setattr(extract, "_ask", lambda *a, **k: calls.append(1) or {"title": "t", "what": "w"})
    assert store.finish_matters(conn, object(), "m", lambda: "stop") == 0 and calls == []


def test_a_database_made_by_any_earlier_version_upgrades_without_error(tmp_path):
    """Migrations are only ever added at the end: a database that has applied the first k steps must take the rest."""
    from kit import db

    from library import store

    for k in range(1, len(store.MIGRATIONS)):
        conn = db.connect(tmp_path / f"v{k}.db")
        db.migrate(conn, [db.Module("library", store.MIGRATIONS[:k])])
        db.migrate(conn, [store.MODULE])
        assert conn.execute("SELECT COUNT(*) FROM trace").fetchone()[0] == 0


def test_interpretation_can_run_in_small_slices_while_files_are_still_being_identified(conn, monkeypatch):
    from library import store

    for i in range(6):
        _doc(conn, f"b{i}", f"Invoice number {i}", {"due_date": "2026-12-01"})
    calls = []
    monkeypatch.setattr(extract, "_ask", lambda *a, **k: calls.append(1) or {"title": "t", "what": "w"})
    assert store.finish_matters(conn, object(), "m", pairs=2, groups=2) == 2 and len(calls) == 2  # only a slice
    assert store.finish_matters(conn, object(), "m", pairs=2, groups=2) == 2  # the next slice carries on from there
    assert conn.execute("SELECT COUNT(*) FROM cases WHERE summary=''").fetchone()[0] == 2
