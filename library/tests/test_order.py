import json
import threading

from library import apps, casebook, priority, store


def test_the_apps_are_served_in_their_order_with_loose_files_and_mail_last(monkeypatch):
    monkeypatch.delenv("LIBRARY_PRIORITY", raising=False)
    assert priority.order() == apps.names() == ["finance", "health", "travel"]  # the order the apps are declared in apps.json
    ranks = [priority.rank(a) for a in ("finance", "health", "travel", "personal", "others", "", "mail", "pictures")]
    assert (
        ranks == sorted(ranks) and len(set(ranks[:4])) == 4 and ranks[3] == ranks[4] and ranks[-1] == ranks[-2]
    )  # other folders after the apps; mail and pictures together, last
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


def test_each_step_counts_documents_mails_and_documents_in_mails_apart(conn, monkeypatch):
    from library import web

    monkeypatch.setattr(web, "_found", lambda: {"documents": 2, "mails": 1})
    monkeypatch.setattr(web, "_gone_through", lambda: {"mails": 1})

    _add(conn, "a.pdf", "finance", judged=1)
    _add(conn, "b.pdf", "finance", judged=0)
    _add(conn, "m1.eml", "mail", judged=1)
    conn.execute("UPDATE documents SET kind='email' WHERE name='m1.eml'")
    _add(conn, "m1.eml/bill.pdf", "mail", judged=0)
    conn.commit()
    sort = web._steps(conn, {"phase": 2})[1]
    assert {c["key"]: (c["done"], c["total"]) for c in sort["counts"]} == {"documents": (1, 2), "mails": (1, 1), "attachments": (0, 1)}
    conn.execute("UPDATE documents SET promised=7 WHERE name='m1.eml'")
    conn.commit()
    read = web._steps(conn, {"phase": 1})[0]
    assert {c["key"]: c["total"] for c in read["counts"] if c["known"]} == {
        "documents": 2,
        "mails": 1,
        "attachments": 7,
    }  # each gives its number as soon as its total is known
    assert [c["key"] for c in read["counts"]] == ["mails", "attachments", "documents"]  # all three are always listed alike, in the order they are read
    assert web._steps(conn, {"phase": 1})[0]["state"] != "done"  # the mail says how many it carried, even before they are all taken out
    assert [c["label"] for c in sort["counts"]] == ["mails", "documents in mails", "documents"]


def test_the_groups_of_the_app_served_first_are_read_first(conn, monkeypatch):
    from kit import extract

    for name, area in (("h.pdf", "health"), ("f.pdf", "finance")):
        _add(conn, name, area, judged=1)
        conn.execute("UPDATE documents SET facts=? WHERE name=?", (json.dumps({"due_date": "2026-12-01"}), name))
    conn.commit()
    asked = []
    monkeypatch.setattr(extract, "_ask", lambda *a, **k: asked.append(a[3]) or {"title": "t", "what": "w"})
    store.finish_matters(conn, object(), "m")
    assert len(asked) == 2 and "f.pdf" in asked[0] and "h.pdf" in asked[1]  # the app served first is read first
    assert [r["rank"] for r in conn.execute("SELECT rank FROM cases ORDER BY id")] == [priority.rank("health"), priority.rank("finance")]


def test_the_model_is_asked_about_the_next_file_while_the_current_one_is_still_being_waited_for(conn, monkeypatch):
    for i in range(2):
        _add(conn, f"f{i}.pdf", "finance")
    conn.commit()
    both_asked = threading.Barrier(2, timeout=5)  # the first answer is held back until the second question has arrived

    class Model:
        def chat(self, model, messages, **kw):
            both_asked.wait()
            return {"content": json.dumps({"kind": "invoice", "apps": ["finance"], "title": "t", "what": "w"})}

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


def test_a_mail_with_attachments_is_not_skipped_by_the_keyword_rule_but_one_without_still_can_be():
    base = {"kind": "email", "area": "mail", "name": "00001 Hello.eml", "text": "Hi, see you soon, thanks for the lovely evening"}
    assert store._skippable({**base, "data": json.dumps({"meta": {"attachments": 0}})}) is True  # no amount, no invoice-like word, nothing attached
    assert (
        store._skippable({**base, "data": json.dumps({"meta": {"attachments": 2}})}) is False
    )  # its attachments are read: what the mail says about them matters
    assert store._skippable({**base, "text": "  ", "data": json.dumps({"meta": {"attachments": 2}})}) is True  # no text at all is still nothing to read


def test_the_apps_and_their_words_come_from_the_file_not_from_the_code(tmp_path, monkeypatch):
    from library import relevance

    declared = tmp_path / "apps.json"
    declared.write_text(
        json.dumps({"apps": [{"name": "Garden", "about": "the garden", "terms": "tulips"}, {"name": "pets", "about": "the pets", "terms": "kibble"}]})
    )
    monkeypatch.setenv("LIBRARY_APPS", str(declared))
    monkeypatch.delenv("LIBRARY_PRIORITY", raising=False)
    assert priority.order() == ["garden", "pets"] and apps.describe() == {"garden": "the garden", "pets": "the pets"}
    assert relevance.worth_reading("m.eml", "email", "Your tulips order: 12,50 euro")  # a word an app declares
    assert not relevance.worth_reading("m.eml", "email", "Your invoice: 12,50 euro")  # "invoice" is in no declared app here: no word is in the code


def test_once_step_one_is_over_it_is_done_and_the_totals_are_what_is_held(conn, monkeypatch):
    from library import web

    monkeypatch.setattr(web, "_found", lambda: {"documents": 5, "mails": 3})  # more counted than there are: some are copies of each other, some cannot be read
    _add(conn, "a.pdf", "finance", judged=1)
    conn.commit()
    steps = web._steps(conn, {"phase": 2})
    assert steps[0]["state"] == "done" and all(c["known"] for c in steps[0]["counts"])
    assert {c["key"]: c["total"] for c in steps[1]["counts"]}["documents"] == 1


def test_a_step_that_has_not_begun_shows_nothing_done(conn, monkeypatch):
    from library import web

    monkeypatch.setattr(web, "_found", lambda: {"documents": 2, "mails": 0})
    _add(conn, "a.pdf", "finance", judged=2)  # skipped: it counts as sorted and as grouped the moment sorting begins, not before
    conn.commit()
    steps = web._steps(conn, {"phase": 1})
    assert [c["done"] for c in steps[1]["counts"]] == [0, 0, 0] and [c["done"] for c in steps[2]["counts"]] == [0, 0, 0]
    assert {c["key"]: c["done"] for c in web._steps(conn, {"phase": 2})[1]["counts"]}["documents"] == 1


def test_step_one_counts_every_file_the_reader_has_gone_through_and_ends_on_the_exact_count(conn, monkeypatch):
    from library import web

    monkeypatch.setattr(web, "_found", lambda: {"documents": 10, "mails": 0})
    monkeypatch.setattr(web, "_gone_through", lambda: {"documents": 7})
    for i in range(4):
        _add(conn, f"f{i}.pdf", "finance", judged=1)
    conn.commit()
    line = lambda phase: next(c for c in web._steps(conn, {"phase": phase})[0]["counts"] if c["key"] == "documents")  # noqa: E731
    assert (line(1)["done"], line(1)["total"]) == (7, 10)  # copies and left-out files are gone through too
    assert (line(2)["done"], line(2)["total"]) == (10, 10)  # and when the step is over it is exactly the count


def test_all_three_counts_are_known_as_soon_as_the_reader_has_counted(conn, monkeypatch):
    from library import web

    monkeypatch.setattr(web, "_found", lambda: {"documents": 3, "mails": 5, "attachments": 2})
    monkeypatch.setattr(web, "_gone_through", dict)
    counts = {c["key"]: (c["known"], c["total"]) for c in web._steps(conn, {"phase": 1})[0]["counts"]}
    assert counts == {"documents": (True, 3), "mails": (True, 5), "attachments": (True, 2)}


def test_many_files_of_a_kind_about_no_app_are_suggested_as_a_new_app_and_can_become_one(conn, tmp_path, monkeypatch):
    import json

    from library import apps

    monkeypatch.setenv("ATLAS_HOME", str(tmp_path))
    for i in range(25):
        conn.execute(
            "INSERT INTO documents (sha256, name, kind, text, area, judged, facts, ready) VALUES (?,?,?,?,?,1,?,?)",
            (f"{i:064x}", f"c{i}.vhd", "text", "t", "", json.dumps({"kind": "Circuit design", "apps": []}), i + 1),
        )
    for i in range(5):  # too few to suggest
        conn.execute(
            "INSERT INTO documents (sha256, name, kind, text, area, judged, facts) VALUES (?,?,?,?,?,1,?)",
            (f"f{i:063x}", f"n{i}.txt", "text", "t", "", json.dumps({"kind": "Course notes", "apps": []})),
        )
    conn.commit()
    suggested = store.category_suggestions(conn)
    assert [(s["kind"], s["count"]) for s in suggested] == [("circuit design", 25)] and len(suggested[0]["examples"]) == 3
    made = store.create_app_for_kind(conn, "Circuit design")
    assert made == {"ok": True, "app": "circuit-design", "files": 25}
    assert "circuit-design" in apps.names() and store.category_suggestions(conn) == []  # the files belong to the app now
    assert len(store.list_documents(conn, app="circuit-design", limit=100)) == 25
    assert store.create_app_for_kind(conn, "circuit design")["ok"] is False  # not twice


def test_a_round_is_complete_only_when_the_reader_has_gone_through_everything_it_counted(monkeypatch):
    from library import web

    monkeypatch.setattr(web, "_found", lambda: {"documents": 10, "mails": 4, "attachments": 2})
    monkeypatch.setattr(web, "_gone_through", lambda: {"documents": 7, "mails": 4, "attachments": 2})
    assert not web._round_complete()  # three documents never came: the reader stopped short, so sorting must not start yet
    monkeypatch.setattr(web, "_gone_through", lambda: {"documents": 10, "mails": 4, "attachments": 2})
    assert web._round_complete()
    monkeypatch.setattr(web, "_gone_through", dict)
    assert web._round_complete()  # nothing to compare with: the read is not held
