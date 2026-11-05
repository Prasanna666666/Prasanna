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
    assert store.ingest_dir(conn, tmp_path) == {"new": 1, "known": 0, "rejected": 5}
    assert store.ingest_dir(conn, tmp_path) == {"new": 0, "known": 0, "rejected": 5}  # the stored one was deleted; nothing is stored twice


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
