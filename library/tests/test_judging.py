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
