import json
from types import SimpleNamespace

import pytest
from kit import db

from library import store


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "library.db")
    db.migrate(c, [store.MODULE])
    n = [0]

    def add(name, kind, **facts):
        n[0] += 1
        c.execute(
            "INSERT INTO documents (sha256, name, kind, text, area, facts, judged, ready) VALUES (?,?,?,?,?,?,1,?)",
            (f"{n[0]:064x}", name, "pdf", "t", "", json.dumps({"kind": kind, **facts}), n[0]),
        )
        c.commit()

    return SimpleNamespace(conn=c, add=add)


def test_the_home_cards_are_short_facts_from_the_same_data(conn):
    from types import SimpleNamespace

    from library import highlights

    conn.add(
        "b.pdf",
        "medical",
        title="Blood test",
        date="2026-03-01",
        health={"values": [{"test": "Glucose", "value": "6,4", "number": 6.4, "unit": "mmol/L", "range": "4,0 - 6,0"}], "medicines": [], "follow_up": None},
    )
    state = SimpleNamespace(engine=lambda: None)
    card = highlights.card("health", conn.conn, state)
    assert card["headline"] == "1 to look at" and card["tone"] == "warn" and card["items"][0] == {"label": "Glucose", "value": "6,4 mmol/L"}
    assert highlights.card("photos", conn.conn, state)["headline"] == "Not connected"
    assert highlights.card("nonsense", conn.conn, state) is None


def test_forgetting_a_document_removes_what_was_read_and_nothing_else(conn):
    conn.add("a.pdf", "invoice", title="Keep")
    conn.add("b.pdf", "invoice", title="Forget")
    gone = conn.conn.execute("SELECT id FROM documents WHERE name='b.pdf'").fetchone()["id"]
    assert store.forget(conn.conn, gone) == "b.pdf" and store.forget(conn.conn, gone) is None
    assert [r["name"] for r in conn.conn.execute("SELECT name FROM documents")] == ["a.pdf"]


def test_an_empty_health_page_says_where_the_documents_are_stuck(conn):
    conn.add(
        "v.pdf",
        "medical",
        title="Blood test",
        date="2026-03-01",
        health={"values": [{"test": "Glucose", "value": "6,4", "number": 6.4, "unit": "", "range": ""}]},
    )
    conn.conn.execute("INSERT INTO documents (sha256, name, kind, text, area, facts, judged) VALUES ('w','scan.pdf','pdf','','health','',0)")
    conn.conn.commit()
    f = store.health_funnel(conn.conn)
    assert f["found"] == 2 and f["understood"] == 1 and f["with_values"] == 1 and f["waiting_for_the_model"] == 1 and f["no_readable_text"] == 1
