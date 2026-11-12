import json

import pytest

from library import parser, store


def test_extract_text_csv_and_control_chars(tmp_path):
    (tmp_path / "a.txt").write_text("hello\x00 \x1bworld\nline2")
    (tmp_path / "s.csv").write_text("date,desc,amount\n2026-01-01,Rent,1000\n")
    assert parser.extract(tmp_path / "a.txt")["text"] == "hello world\nline2"
    c = parser.extract(tmp_path / "s.csv")
    assert c["meta"]["columns"] == ["date", "desc", "amount"] and "Rent | 1000" in c["text"]
    with pytest.raises(ValueError):
        parser.extract(tmp_path / "x.exe")


def test_process_inbox_isolated_dedupes_skips_and_survives_bad_files(tmp_path):
    inbox, out = tmp_path / "in", tmp_path / "out"
    inbox.mkdir()
    (inbox / "note.md").write_text("Dad BP tablet after breakfast")
    (inbox / "copy.md").write_text("Dad BP tablet after breakfast")  # same content -> parsed once
    (inbox / "broken.pdf").write_bytes(b"%PDF-1.4 this is not a real pdf \x00\xff" * 50)
    (inbox / "malware.exe").write_bytes(b"MZ")
    (tmp_path / "secret.txt").write_text("outside the inbox")
    (inbox / "link.txt").symlink_to(tmp_path / "secret.txt")
    r = parser.process_inbox(inbox, out)  # real subprocess isolation
    assert r["parsed"] == 1 and r["failed"] == 1 and r["skipped"] == 1
    files = list(out.glob("*.json"))
    assert len(files) == 1 and not list(out.glob(".*.tmp"))
    d = json.loads(files[0].read_text())
    assert d["kind"] == "text" and d["name"] in ("note.md", "copy.md") and d["sha256"] == files[0].stem
    assert parser.process_inbox(inbox, out) == {"parsed": 0, "skipped": 1, "failed": 1}  # nothing re-parsed


def _doc(**kw):
    d = {
        "schema": 1,
        "sha256": "a" * 64,
        "name": "bp.txt",
        "kind": "text",
        "text": "Dad BP 150/90 doctor said reduce salt",
        "parsed_at": "2026-11-03T10:00:00+00:00",
    }
    return {**d, **kw}


def _put(dirpath, d, stem=None):
    (dirpath / f"{stem or d['sha256']}.json").write_text(json.dumps(d))


def test_ingest_validates_strictly(conn, tmp_path):
    _put(tmp_path, _doc())
    _put(tmp_path, _doc(sha256="b" * 64, schema=2))  # wrong schema
    _put(tmp_path, _doc(sha256="c" * 64, kind="exe"))  # unknown kind
    _put(tmp_path, _doc(sha256="d" * 64, text=["not", "a", "string"]))  # wrong type
    _put(tmp_path, _doc(sha256="e" * 64), stem="f" * 64)  # name/hash mismatch
    (tmp_path / "junk.json").write_text("{not json")
    assert store.ingest_dir(conn, tmp_path) == {"new": 1, "known": 0, "rejected": 5, "replaced": 0}
    assert store.ingest_dir(conn, tmp_path) == {"new": 0, "known": 0, "rejected": 5, "replaced": 0}  # the stored one was deleted; nothing is stored twice


def test_search_and_read_documents(conn, tmp_path):
    _put(tmp_path, _doc())
    store.ingest_dir(conn, tmp_path)
    hit = store.passages(conn, "salt doctor")[0]
    assert hit["title"] == "bp.txt" and "salt" in hit["text"]
    got = store.get_document(conn, "a" * 64)
    assert got is not None and got["name"] == "bp.txt" and "salt" in got["text"]


def test_a_document_becomes_ready_once_judged_and_an_app_asks_by_kind(conn, tmp_path):
    _put(tmp_path, _doc(name="invoice.txt", text="FACTUUR Ziggo totaal 60,50 EUR betaling", sha256="b" * 64))
    store.ingest_dir(conn, tmp_path)
    assert store.list_documents(conn, ["invoice"]) == []  # not judged yet: not ready

    class Model:
        def chat(self, model, messages, **kw):
            return {"content": json.dumps({"kind": "invoice", "title": "Internet", "party": "Ziggo", "total": "60,50", "currency": "EUR"})}

    done = store.judge_pending(conn, Model(), "fake")
    assert done["read"] == 1
    [doc] = store.list_documents(conn, ["invoice"], full=True)
    assert doc["facts"]["party"] == "Ziggo" and float(doc["facts"]["total"]) == 60.5 and "FACTUUR" in doc["text"] and doc["ready"] == 1
    assert store.list_documents(conn, ["ticket"]) == [] and store.list_documents(conn, ["invoice"], since=1) == []  # nothing new since number 1


def test_a_newsletter_is_judged_once_without_the_model_and_a_waiting_document_stays_pending(conn, tmp_path):
    _put(tmp_path, _doc(name="promo.eml", kind="email", text="Big sale this week only, enjoy our newsletter with many friendly words.", sha256="c" * 64))
    _put(tmp_path, _doc(name="hotel.eml", kind="email", text="Booking confirmed. Total paid EUR 480,00 for the hotel.", sha256="d" * 64))
    store.ingest_dir(conn, tmp_path)
    done = store.judge_pending(conn, None, None)  # the model is not running
    assert done["skipped"] == 1 and done["waiting"] == 1 and "Ollama" in done["problem"]
    assert store.counts(conn)["waiting"] == 1


def test_a_picture_with_no_text_is_a_photo_and_one_with_text_is_a_document(conn, tmp_path):
    _put(tmp_path, _doc(name="holiday.jpg", kind="image", text="", sha256="e" * 64))
    _put(
        tmp_path,
        _doc(name="receipt.jpg", kind="image", text="Albert Heijn kassabon totaal 23,45 EUR betaald met pinpas, bedankt voor uw bezoek", sha256="f" * 64),
    )
    store.ingest_dir(conn, tmp_path)

    class Model:
        def chat(self, model, messages, **kw):
            return {"content": json.dumps({"kind": "receipt", "title": "Albert Heijn", "total": "23,45", "currency": "EUR"})}

    store.judge_pending(conn, Model(), "fake")
    assert [d["name"] for d in store.list_documents(conn, ["photo"])] == ["holiday.jpg"]  # for the Photos app to take; no model was asked
    assert [d["name"] for d in store.list_documents(conn, ["receipt"])] == ["receipt.jpg"]


def test_every_kind_of_file_has_one_reader_in_the_registry():
    assert set(parser.PARSERS) == set(parser.KINDS.values()) - {
        "mbox",
        "zip",
    }  # archives and mailboxes are opened first, then each file inside is read by its own reader


def test_a_trip_is_found_from_the_tickets_and_bookings_and_everything_in_its_window_belongs_to_it(conn, tmp_path):
    texts = {
        "flight-out.eml": (
            "c" * 64,
            "ticket",
            {"kind": "ticket", "title": "Flight out", "place": "India", "start_date": "2026-01-12", "end_date": "2026-01-12"},
        ),
        "hotel.eml": ("d" * 64, "booking", {"kind": "booking", "title": "Hotel Delhi", "place": "India", "start_date": "2026-01-12", "end_date": "2026-01-28"}),
        "flight-back.eml": (
            "e" * 64,
            "ticket",
            {"kind": "ticket", "title": "Flight back", "place": "India", "start_date": "2026-01-30", "end_date": "2026-01-30"},
        ),
        "paris.eml": ("f" * 64, "booking", {"kind": "booking", "title": "Paris", "place": "France", "start_date": "2025-06-01", "end_date": "2025-06-03"}),
        "taxi.eml": ("1" * 64, "receipt", {"kind": "receipt", "title": "Taxi Delhi", "date": "2026-01-14"}),
    }
    for name, (sha, kind, _facts) in texts.items():
        _put(tmp_path, _doc(name=name, kind="email", text=f"{kind} {name}", sha256=sha))
    store.ingest_dir(conn, tmp_path)
    for sha, _kind, facts in texts.values():
        store._mark_ready(conn, sha, 1, facts)
    [india] = store.trips(conn, "india", "2026")
    assert india == {"place": "India", "start": "2026-01-12", "end": "2026-01-30", "documents": 3}
    assert [t["place"] for t in store.trips(conn)] == ["India", "France"]  # most documents first
    titles = [d["facts"]["title"] for d in store.documents_between(conn, india["start"], india["end"])]
    assert titles == ["Flight out", "Hotel Delhi", "Taxi Delhi", "Flight back"]  # the taxi has no trip tag, but its date is inside the window


def test_the_reader_counts_every_file_and_mail_it_will_take_before_reading(tmp_path):
    import argparse
    import json

    from library import parser

    inbox = tmp_path / "inbox"
    (inbox / "mail").mkdir(parents=True)
    (inbox / "a.txt").write_text("x")
    (inbox / "b.pdf").write_bytes(b"%PDF")
    (inbox / "skip.xyz").write_text("x")
    (inbox / "mail" / "m.eml").write_text("Subject: hi\n\nbody")
    ns = argparse.Namespace(inbox=str(inbox), out=str(tmp_path / "out"), collection=[], mail="")
    parser.write_found(ns)
    assert json.loads((tmp_path / "out" / ".found").read_text()) == {"documents": 2, "mails": 1, "mail_connected": False, "by_folder": {"inbox": 2}}


def test_reading_several_files_at_once_gives_the_same_result_as_one_at_a_time(tmp_path, monkeypatch):
    inbox = tmp_path / "in"
    inbox.mkdir()
    for i in range(12):
        (inbox / f"m{i}.eml").write_text(f"Subject: hello {i}\nFrom: a@b.c\n\nBody of mail {i} about invoice number {i}\n")
    (inbox / "twin1.txt").write_text("same words")
    (inbox / "twin2.txt").write_text("same words")  # the same content twice: read once, even when read at the same moment
    results = {}
    for workers in (1, 4):
        monkeypatch.setattr(parser, "WORKERS", workers)
        out = tmp_path / f"out{workers}"
        counts = parser.process_inbox(inbox, out, isolated=False)
        results[workers] = (counts, sorted(p.stem for p in out.glob("*.json")))
    assert results[1] == results[4] and results[4][0]["parsed"] == 13


def test_stop_and_pause_are_heard_while_the_reader_is_still_looking_through_the_folders(tmp_path, monkeypatch):
    import argparse

    from library import parser

    monkeypatch.setattr(parser, "CHECK_EVERY", 5)
    monkeypatch.setattr(parser, "GENTLE_SECONDS", 0)
    inbox, mail, out = tmp_path / "in", tmp_path / "mail", tmp_path / "out"
    for folder in (inbox, mail / "box"):
        folder.mkdir(parents=True)
    for i in range(40):
        (inbox / f"f{i}.txt").write_text(f"note {i}")
        (mail / "box" / f"{i}.emlx").write_text(f"Subject: {i}\n\nbody {i}")
    ns = argparse.Namespace(inbox=str(inbox), out=str(out), collection=[], mail=str(mail))
    out.mkdir()
    (out / parser.STOP).touch()  # the person pressed Stop
    parser.write_found(ns)
    assert not (out / parser.FOUND_FILE).exists()  # it stopped counting instead of walking everything
    assert parser.process_mail_store(mail, out, isolated=False) == {"parsed": 0, "skipped": 0, "failed": 0}  # and did not read the mail
    assert parser.read_everything(ns) == {"parsed": 0, "skipped": 0, "failed": 0} and not list(out.glob("*.json"))
    (out / parser.STOP).unlink()
    parser.write_found(ns)
    assert json.loads((out / parser.FOUND_FILE).read_text())["documents"] == 40  # without Stop it counts as before


def test_a_changed_file_replaces_its_older_version_and_going_back_reads_it_again(tmp_path):
    from kit import db

    from library import store

    folder, out = tmp_path / "icloud", tmp_path / "parsed"
    folder.mkdir()
    conn = db.connect(tmp_path / "library.db")
    db.migrate(conn, [store.MODULE])
    note = folder / "plan.txt"

    def read(text):
        note.write_text(text)
        parser.process_inbox(folder, out, isolated=False, area="health")
        return store.ingest_dir(conn, out)

    def texts():
        return [r[0] for r in conn.execute("SELECT text FROM documents ORDER BY id")]

    assert read("version one")["new"] == 1 and texts() == ["version one"]
    assert read("version two")["replaced"] == 1 and texts() == ["version two"]  # one file, one document: the latest
    other = folder / "other.txt"
    other.write_text("a different file")
    parser.process_inbox(folder, out, isolated=False, area="health")
    store.ingest_dir(conn, out)
    assert sorted(texts()) == ["a different file", "version two"]  # a different file is not a version of this one
    assert (
        read("version one")["replaced"] == 1 and "version one" in texts() and "version two" not in texts()
    )  # back to the earlier content: read again, not skipped as known
    assert read("version one")["new"] == 0  # unchanged: nothing happens
