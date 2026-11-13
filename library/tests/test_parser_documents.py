import json

from library import parser, store


def test_extract_text_csv_and_control_chars(tmp_path):
    (tmp_path / "a.txt").write_text("hello\x00 \x1bworld\nline2")
    (tmp_path / "s.csv").write_text("date,desc,amount\n2026-01-01,Rent,1000\n")
    assert parser.extract(tmp_path / "a.txt")["text"] == "hello world\nline2"
    c = parser.extract(tmp_path / "s.csv")
    assert c["meta"]["columns"] == ["date", "desc", "amount"] and "Rent | 1000" in c["text"]
    (tmp_path / "x.exe").write_bytes(b"MZ\x90\x00" + bytes(range(256)) * 4)
    assert parser.extract(tmp_path / "x.exe")["kind"] == "binary"  # no list of allowed types: a file no reader fits is still taken, by the words it holds


def test_process_inbox_isolated_dedupes_skips_and_survives_bad_files(tmp_path):
    inbox, out = tmp_path / "in", tmp_path / "out"
    inbox.mkdir()
    (inbox / "note.md").write_text("Dad BP tablet after breakfast")
    (inbox / "copy.md").write_text("Dad BP tablet after breakfast")  # same content -> parsed once
    (inbox / "broken.pdf").write_bytes(b"%PDF-1.4 this is not a real pdf \x00\xff" * 50)
    (inbox / "malware.exe").write_bytes(b"MZ\x90\x00" + bytes(range(256)) * 2)
    (tmp_path / "secret.txt").write_text("outside the inbox")
    (inbox / "link.txt").symlink_to(tmp_path / "secret.txt")
    r = parser.process_inbox(inbox, out)  # real subprocess isolation
    assert (
        r["parsed"] == 2 and r["failed"] == 1 and r["skipped"] == 0
    )  # the notes once, the program as a file with no readable text; only the damaged PDF fails
    files = list(out.glob("*.json"))
    assert len(files) == 2 and not list(out.glob(".*.tmp"))
    kinds = {json.loads(f.read_text())["name"]: json.loads(f.read_text())["kind"] for f in files}
    assert kinds.get("malware.exe") == "binary" and "text" in (kinds.get("note.md"), kinds.get("copy.md"))
    assert all(json.loads(f.read_text())["sha256"] == f.stem for f in files)
    assert parser.process_inbox(inbox, out) == {"parsed": 0, "skipped": 0, "failed": 1}  # nothing re-parsed


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
    from library import sniff

    # every kind of content the sniffer can name has a reader, except mailboxes, which are opened first so that each message is read by the email reader
    named = {"pdf", "image", "sheet", "doc", "html", "email", "json", "csv", "text", "zip", "binary"}
    assert set(parser.PARSERS) == named and sniff.kind_of.__doc__ and all(k in sniff.kind_of.__doc__ for k in named | {"mbox"})


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
    assert json.loads((tmp_path / "out" / ".found").read_text()) == {
        "documents": 3,  # skip.xyz is counted too: no file is turned away for its ending
        "mails": 1,
        "mail_connected": False,
        "by_folder": {"inbox": 3},
        "unread": {"counts": {}, "examples": {}},
    }


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


def test_the_report_says_which_files_are_not_read_and_why(tmp_path, monkeypatch):
    import argparse

    from kit import db

    from library import parser, readreport, store, tools

    inbox, out = tmp_path / "in", tmp_path / "out"
    cat = tmp_path / "personal"
    for folder in (inbox, cat / "sub"):
        folder.mkdir(parents=True)
    (inbox / "ok.txt").write_text("fine")
    (cat / "sub" / "deck.key").write_bytes(b"x")  # any ending is read: nothing is turned away for it
    (cat / ".contract.pdf.icloud").write_bytes(b"")  # a file that is only in iCloud
    (cat / "alias.pdf").symlink_to(inbox / "ok.txt")
    (cat / ".hidden").write_text("x")  # hidden system files are not mentioned
    (cat / ".DS_Store").write_text("x")
    ns = argparse.Namespace(inbox=str(inbox), out=str(out), collection=[f"personal={cat}"], mail="")
    monkeypatch.setenv("ATLAS_PARSED", str(out))
    parser.write_found(ns)
    conn = db.connect(tmp_path / "library.db")
    db.migrate(conn, [store.MODULE])
    report = readreport.summary(conn)
    assert {r["reason"]: r["count"] for r in report["reasons"]} == {"only_in_icloud": 1, "alias_or_link": 1} and report["not_read"] == 2
    assert json.loads((out / ".found").read_text())["documents"] == 2  # ok.txt and deck.key: both will be read
    examples = {r["reason"]: r["examples"] for r in report["reasons"]}
    assert examples["only_in_icloud"] == ["personal: contract.pdf"] and "Download Now" in next(
        r["each_file"] for r in report["reasons"] if r["reason"] == "only_in_icloud"
    )
    (out / ".failed.json").write_text(json.dumps(["personal/bad.pdf: password protected"]))
    assert readreport.summary(conn)["not_read"] == 3 and readreport.unread_counts()["unreadable"] == 1
    conn.execute("INSERT INTO documents (sha256, name, kind, text, area, judged) VALUES (?,?,?,?,?,2)", ("a" * 64, "news.eml", "email", "t", "mail"))
    conn.execute("INSERT INTO documents (sha256, name, kind, text, area, judged) VALUES (?,?,?,?,?,2)", ("b" * 64, "holiday.mov", "binary", "", "personal"))
    conn.commit()
    again = readreport.summary(conn)
    assert (
        again["set_aside_as_not_relevant"] == {"mail": 1, "personal": 1}
        and again["kept_by_name_only"]["count"] == 1
        and again["kept_by_name_only"]["examples"] == ["holiday.mov"]
    )
    assert tools.run(type("S", (), {"engine": lambda s: None, "picture_text": lambda s: None})(), conn, "unread_files", {})["data"]["not_read"] == 3


def test_rtf_odt_and_pptx_files_are_read_and_heic_is_a_supported_picture_type(tmp_path):
    import zipfile

    from library import parser

    rtf = tmp_path / "letter.rtf"
    rtf.write_bytes(
        rb"{\rtf1\ansi{\fonttbl\f0 Arial;}{\*\generator Word;}\f0\fs24 Dear Mr. Jansen,\par Your policy number is 12345.\par Caf\'e9 invoice: total 480,00 euro.\par}"
    )
    text = parser.extract(rtf)["text"]
    assert (
        "Dear Mr. Jansen," in text
        and "policy number is 12345." in text
        and "Café invoice: total 480,00 euro." in text
        and "fonttbl" not in text
        and "generator" not in text
    )
    odt = tmp_path / "plan.odt"
    with zipfile.ZipFile(odt, "w") as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        z.writestr(
            "content.xml",
            '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><text:h>Tenancy</text:h><text:p>Rent is <text:span>950</text:span> euro.</text:p></office:body></office:document-content>',
        )
    assert parser.extract(odt)["text"] == "Tenancy\nRent is 950 euro."
    pptx = tmp_path / "talk.pptx"
    slide = '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>{}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>'
    with zipfile.ZipFile(pptx, "w") as z:
        z.writestr("ppt/slides/slide10.xml", slide.format("Tenth"))
        z.writestr("ppt/slides/slide2.xml", slide.format("Second"))
        z.writestr("ppt/slides/slide1.xml", slide.format("First"))
    assert parser.extract(pptx)["text"] == "First\n\nSecond\n\nTenth"  # in slide order, not name order
    from library import sniff

    heic = tmp_path / "scan.heic"
    heic.write_bytes(b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heicmif1")
    assert (
        sniff.kind_of(heic) == "image" and sniff.kind_of(rtf) == "doc" and sniff.kind_of(odt) == "doc" and sniff.kind_of(pptx) == "doc"
    )  # found out by what is inside, not by the ending


def test_judging_in_small_rounds_leaves_the_rest_for_the_next_round(conn, tmp_path):
    for i in range(5):
        _put(tmp_path, _doc(name=f"i{i}.txt", text=f"FACTUUR Ziggo totaal {i}0,50 EUR betaling", sha256=str(i) * 64))
    store.ingest_dir(conn, tmp_path)

    class Model:
        def chat(self, model, messages, **kw):
            return {"content": json.dumps({"kind": "invoice", "title": "x", "party": "Ziggo", "total": "1,00", "currency": "EUR"})}

    assert store.judge_pending(conn, Model(), "fake", limit=2)["read"] == 2
    assert store.counts(conn)["waiting"] == 3  # the other three wait; new files can be taken in meanwhile
    assert store.judge_pending(conn, Model(), "fake", limit=2)["read"] == 2
