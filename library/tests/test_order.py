import json
import threading

from library import casebook, priority, store


def test_the_apps_are_served_in_their_order_with_loose_files_and_mail_last(monkeypatch):
    monkeypatch.delenv("LIBRARY_PRIORITY", raising=False)
    assert priority.order() == ["finance", "health", "travel", "personal"]
    ranks = [priority.rank(a) for a in ("finance", "health", "travel", "personal", "others", "", "mail", "pictures")]
    assert ranks == sorted(ranks) and len(set(ranks[:5])) == 5 and ranks[-1] == ranks[-2]  # mail and pictures come together, last
    monkeypatch.setenv("LIBRARY_PRIORITY", "health, FINANCE, x'; drop table")
    assert priority.order() == ["health", "finance", "xdroptable"]  # the names go into queries: only letters, digits, - and _ survive
    assert priority.tiers()[0] == "area='health'" and priority.tiers()[-1] == "area IN ('mail', 'pictures')"


def _add(conn, name, area, judged=0):
    conn.execute(
        "INSERT INTO documents (sha256, name, kind, text, area, judged) VALUES (?,?,?,?,?,?)", (name, name, "pdf", "Invoice text " + name, area, judged)
    )


def test_finance_files_are_taken_before_health_files_and_before_loose_files_and_mail(conn):
    for name, area in (("mail.eml", "mail"), ("loose.pdf", ""), ("health.pdf", "health"), ("finance.pdf", "finance"), ("other.pdf", "others")):
        _add(conn, name, area)
    conn.commit()
    assert store.waiting_files(conn, limit=5) == ["finance.pdf", "health.pdf", "other.pdf", "loose.pdf", "mail.eml"]


def test_an_app_is_grouped_only_when_every_one_of_its_files_is_read_and_identified(conn):
    _add(conn, "a.pdf", "finance", judged=1)
    _add(conn, "b.pdf", "finance", judged=0)
    conn.commit()
    assert store.app_ready(conn, "finance", found=2) is False  # one file still waits for the model
    conn.execute("UPDATE documents SET judged=1 WHERE name='b.pdf'")
    conn.commit()
    assert store.app_ready(conn, "finance", found=3) is False  # the reader has not yet read all three files it found
    assert store.app_ready(conn, "finance", found=2) is True and store.app_ready(conn, "health", found=0) is False


def test_the_groups_of_the_app_served_first_are_read_first(conn, monkeypatch):
    from kit import extract

    for name, area in (("h.pdf", "health"), ("f.pdf", "finance")):
        _add(conn, name, area, judged=1)
        conn.execute("UPDATE documents SET facts=? WHERE name=?", (json.dumps({"due_date": "2026-12-01"}), name))
    conn.commit()
    asked = []
    monkeypatch.setattr(extract, "_ask", lambda *a, **k: asked.append(a[3]) or {"title": "t", "what": "w"})
    store.finish_matters(conn, object(), "m", up_to_rank=priority.rank("finance"))
    assert len(asked) == 1 and "f.pdf" in asked[0]  # Health waits for its turn
    store.finish_matters(conn, object(), "m")
    assert len(asked) == 2 and "h.pdf" in asked[1]
    assert [r["rank"] for r in conn.execute("SELECT rank FROM cases ORDER BY id")] == [priority.rank("health"), priority.rank("finance")]


def test_the_model_is_asked_about_the_next_file_while_the_current_one_is_still_being_waited_for(conn, monkeypatch):
    for i in range(2):
        _add(conn, f"f{i}.pdf", "finance")
    conn.commit()
    both_asked = threading.Barrier(2, timeout=5)  # the first answer is held back until the second question has arrived

    class Model:
        def chat(self, model, messages, **kw):
            both_asked.wait()
            return {"content": json.dumps({"kind": "invoice", "title": "t", "what": "w"})}

    monkeypatch.setattr(store, "GENTLE_SECONDS", 0)
    monkeypatch.setattr(store, "PARALLEL", 2)
    out = store.judge_pending(conn, Model(), "fake")
    assert out["read"] == 2 and conn.execute("SELECT COUNT(*) FROM documents WHERE judged=1").fetchone()[0] == 2


def test_a_cases_rank_follows_the_app_served_first_among_its_files(conn):
    _add(conn, "a.pdf", "finance", judged=1)
    _add(conn, "b.pdf", "mail", judged=1)
    conn.execute("UPDATE documents SET facts=? , text=?", (json.dumps({}), "Invoice INV-20931 for 120.50"))
    conn.commit()
    pieces = casebook.pieces_of(conn)
    assert {p["area"] for p in pieces} == {"finance", "mail"}
