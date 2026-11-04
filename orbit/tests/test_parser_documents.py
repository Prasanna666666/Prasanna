import json

import pytest

from orbit import agents, parser
from orbit.modules import ALL, documents, tools


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
    d = {"schema": 1, "sha256": "a" * 64, "name": "bp.txt", "kind": "text", "text": "Dad BP 150/90 doctor said reduce salt",
         "parsed_at": "2026-11-03T10:00:00+00:00"}
    return {**d, **kw}


def _put(dirpath, d, stem=None):
    (dirpath / f"{stem or d['sha256']}.json").write_text(json.dumps(d))


def test_ingest_validates_strictly(conn, tmp_path):
    _put(tmp_path, _doc())
    _put(tmp_path, _doc(sha256="b" * 64, schema=2))                       # wrong schema
    _put(tmp_path, _doc(sha256="c" * 64, kind="exe"))                     # unknown kind
    _put(tmp_path, _doc(sha256="d" * 64, text=["not", "a", "string"]))    # wrong type
    _put(tmp_path, _doc(sha256="e" * 64), stem="f" * 64)                  # name/hash mismatch
    (tmp_path / "junk.json").write_text("{not json")
    assert documents.ingest_dir(conn, tmp_path) == {"new": 1, "known": 0, "rejected": 5}
    assert documents.ingest_dir(conn, tmp_path)["known"] == 1             # idempotent


def test_search_and_read_documents(conn, tmp_path):
    _put(tmp_path, _doc())
    documents.ingest_dir(conn, tmp_path)
    hit = documents.search_documents(conn, {"query": "salt doctor"})[0]
    assert hit["name"] == "bp.txt" and "salt" in hit["snippet"]
    got = documents.get_document(conn, {"id": hit["id"], "max_chars": 10})
    assert got["truncated"] and "untrusted" in got["note"]


def test_documents_agent_is_read_only_and_routed():
    spec = agents.BY_NAME["documents"]
    assert spec.tools == {"search_documents", "get_document", "search_files"}  # every one of them only reads
    assert agents.route("find the pdf statement from the hospital") == "documents"
    # no tool anywhere can create/modify/delete documents
    assert not [t for t in tools(ALL) if "document" in t and t.split("_")[0] in ("add", "delete", "update", "edit")]
