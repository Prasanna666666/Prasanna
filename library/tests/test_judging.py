"""What the Documents service does with what it reads: judging once, leaving newsletters alone, reading Apple Mail's folder once, and leaving no readable copy behind."""

import json

from library import parser, relevance, store


def test_what_is_worth_reading():
    assert not relevance.worth_reading("promo.eml", "email", "Big sale this week only, enjoy our newsletter with many words in it today")
    assert relevance.worth_reading("m.eml", "email", "Your booking is confirmed. Total paid EUR 480,00 for the hotel in Delhi")
    assert not relevance.worth_reading("scan.pdf", "pdf", "")


def test_the_mail_store_is_read_once_and_junk_is_skipped(tmp_path):
    mail, out = tmp_path / "Mail", tmp_path / "out"
    for box in ("INBOX.mbox", "Junk.mbox"):
        d = mail / "V10" / "acct" / box / "Messages"
        d.mkdir(parents=True)
        raw = f"From: a@b.c\nSubject: {box}\nMessage-ID: <{box}@x>\n\nInvoice total EUR 12,00\n".encode()
        (d / "1.emlx").write_bytes(f"{len(raw)}\n".encode() + raw)
    assert parser.process_mail_store(mail, out, isolated=False)["parsed"] == 1
    assert parser.process_mail_store(mail, out, isolated=False)["parsed"] == 0
    assert all(json.loads(p.read_text())["area"] == "mail" for p in out.glob("*.json")) and len(list(out.glob("*.json"))) == 1


def test_the_readable_copy_is_deleted_once_stored_and_the_file_is_not_read_again(tmp_path, conn):
    inbox, out = tmp_path / "in", tmp_path / "parsed"
    inbox.mkdir()
    (inbox / "letter.txt").write_text("Invoice for the hotel, total EUR 100,00. Very personal text.")
    assert parser.process_inbox(inbox, out, isolated=False)["parsed"] == 1
    assert store.ingest_dir(conn, out)["new"] == 1
    assert not list(out.glob("*.json"))  # no readable copy is left on disk
    assert not any("Very personal" in p.read_text(errors="ignore") for p in out.rglob("*") if p.is_file())
    assert parser.process_inbox(inbox, out, isolated=False)["parsed"] == 0  # remembered by a marker with no content
    assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1


def test_a_parser_round_says_when_it_is_busy_and_wakes_on_request(tmp_path):
    inbox, out = tmp_path / "in", tmp_path / "parsed"
    inbox.mkdir()
    assert parser.main(["--inbox", str(inbox), "--out", str(out), "--once"]) == 0
    assert not (out / parser.BUSY).exists()  # idle again once the round is over


def test_the_panel_says_how_long_one_file_takes_and_how_long_all_will_take():
    assert store._speed_line(1184, 0, 0) == "Identifying files: 1,184 waiting"
    assert store._speed_line(1184, 140, 10) == "Identifying files: 1,184 waiting, 14 s per file, about 4 h 36 min left"
    assert store._duration(45) == "45 s" and store._duration(600) == "10 min"


def test_each_file_the_model_finishes_is_saved_at_once_so_the_counts_move(tmp_path, monkeypatch):
    import json
    import sqlite3

    from kit import db

    path = tmp_path / "library.db"
    conn = db.connect(path)
    db.migrate(conn, [store.MODULE])
    for i in range(3):
        conn.execute(
            "INSERT INTO documents (sha256, name, kind, text, area, judged) VALUES (?,?,?,?,?,0)",
            (f"{i:064x}", f"f{i}.pdf", "pdf", "Invoice from Ziggo " * 20, "finance"),
        )
    conn.commit()
    seen = []

    class Model:
        def chat(self, model, messages, **kw):
            other = sqlite3.connect(path)  # what a status question sees while the model is working on the next file
            seen.append(other.execute("SELECT COUNT(*) FROM documents WHERE judged=1").fetchone()[0])
            other.close()
            return {"content": json.dumps({"kind": "invoice", "title": "t", "what": "w", "party": "Ziggo", "total": "1,00", "currency": "EUR"})}

    monkeypatch.setattr(store, "GENTLE_SECONDS", 0)
    store.judge_pending(conn, Model(), "fake")
    assert seen == [0, 1, 2]


def test_a_read_leaves_a_trace_of_every_step_on_every_file(conn):
    import json

    from library import trace

    conn.execute("INSERT INTO documents (sha256, name, kind, text, area, judged) VALUES ('a','bill.pdf','pdf','Invoice from Ziggo total 60,50 ' ,'finance',0)")
    conn.execute("INSERT INTO documents (sha256, name, kind, text, area, judged) VALUES ('b','empty.pdf','pdf','','finance',0)")
    conn.commit()
    now = []

    class Model:
        def chat(self, model, messages, **kw):
            return {"content": json.dumps({"kind": "invoice", "title": "t", "what": "w", "party": "Ziggo", "total": "60,50", "currency": "EUR"})}

    followed = trace.Trace(conn, lambda name, step, detail: now.append((name, step, detail)))
    store.judge_pending(conn, Model(), "fake", trace=followed)
    steps = [(s["name"], s["step"], s["detail"]) for s in reversed(trace.recent(conn))]
    assert ("bill.pdf", "identifying", "31 characters") in steps and ("bill.pdf", "identified", "invoice") in steps
    assert ("empty.pdf", "set aside", "no readable text") in steps
    assert now[0] == ("bill.pdf", "identifying", "31 characters")  # the panel is told which file is being worked on
    assert [s["step"] for s in trace.recent(conn, name="empty")] == ["set aside"]
