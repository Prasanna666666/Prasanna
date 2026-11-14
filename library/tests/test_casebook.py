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
    groups = sorted(casebook.link(pieces))
    assert groups == [[1, 2], [3]]


def test_a_common_value_does_not_glue_unrelated_pieces():
    pieces = [{"id": i, "name": f"f{i}", "text": "REF-77777 hello"} for i in range(1, 8)]
    assert len(casebook.link(pieces)) == 7


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
    monkeypatch.setattr(extract, "_ask", lambda *a, **k: calls.append(1) or {"title": "Invoice", "what": "An invoice"})
    assert casebook.rebuild(conn) == 1
    assert casebook.understand_pending(conn, None, "m") == 1
    assert casebook.rebuild(conn) == 0
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
