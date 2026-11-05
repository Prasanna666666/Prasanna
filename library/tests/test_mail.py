"""Mail, read offline: single messages (.eml), Apple Mail's own files (.emlx) and whole mailbox exports (.mbox), each message and each attachment becoming a document."""

import json
import mailbox
from email.message import EmailMessage

import pytest

from library import ask, parser, readers, store


def message(subject, body, attach=None, to="me@example.com"):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"], m["Date"], m["Message-ID"] = (
        "shop@example.com",
        to,
        subject,
        "Mon, 05 Oct 2026 10:00:00 +0000",
        f"<{subject.replace(' ', '-')}@example.com>",
    )
    m.set_content(body)
    for name, data in (attach or {}).items():
        kind = ("image", "png") if name.endswith(".png") else ("text", "plain")
        m.add_attachment(data, maintype=kind[0], subtype=kind[1], filename=name)
    return m


def write_mbox(path, messages):
    box = mailbox.mbox(str(path))
    for m in messages:
        box.add(m)
    box.flush()
    box.close()


def documents(out):
    return {d["name"]: d for d in (json.loads(p.read_text()) for p in out.glob("*.json"))}


def test_a_mailbox_export_becomes_one_document_per_message_and_per_attachment(tmp_path):
    (tmp_path / "in").mkdir()
    write_mbox(
        tmp_path / "in" / "gmail.mbox",
        [
            message("Uw factuur", "Zie bijlage.", {"factuur.txt": b"Factuur Ziggo totaal 60,50"}),
            message("Vliegtickets", "Uw tickets naar Bengaluru.", {"ticket.txt": b"Flight KL 879 AMS-BLR 12 Jan 2026"}),
        ],
    )
    counts = parser.process_inbox(tmp_path / "in", tmp_path / "out", isolated=False)
    docs = documents(tmp_path / "out")
    assert counts["failed"] == 0 and len(docs) == 4
    names = sorted(docs)
    assert names == [
        "gmail.mbox/00001 Uw factuur.eml",
        "gmail.mbox/00001 Uw factuur.eml/factuur.txt",
        "gmail.mbox/00002 Vliegtickets.eml",
        "gmail.mbox/00002 Vliegtickets.eml/ticket.txt",
    ]
    assert "totaal 60,50" in docs[names[1]]["text"] and "Bengaluru" in docs[names[2]]["text"] and docs[names[0]]["kind"] == "email"
    assert docs[names[0]]["meta"]["message_id"] == "<Uw-factuur@example.com>"


def test_a_mailbox_already_read_is_not_read_again_but_new_mail_in_a_new_export_is(tmp_path):
    (tmp_path / "in").mkdir()
    write_mbox(tmp_path / "in" / "a.mbox", [message("One", "first")])
    assert parser.process_inbox(tmp_path / "in", tmp_path / "out", isolated=False)["parsed"] == 1
    assert parser.process_inbox(tmp_path / "in", tmp_path / "out", isolated=False)["parsed"] == 0  # same file: nothing to do
    write_mbox(tmp_path / "in" / "b.mbox", [message("One", "first"), message("Two", "second")])
    assert parser.process_inbox(tmp_path / "in", tmp_path / "out", isolated=False)["parsed"] == 1  # the message already seen is skipped, the new one read
    assert len(documents(tmp_path / "out")) == 2


def test_apple_mails_own_files_are_read(tmp_path):
    raw = bytes(message("Polis", "Uw autoverzekering, eigen risico 250 euro."))
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "1234.emlx").write_bytes(str(len(raw)).encode() + b"\n" + raw + b'\n<?xml version="1.0"?><plist version="1.0"><dict/></plist>\n')
    parser.process_inbox(tmp_path / "in", tmp_path / "out", isolated=False)
    docs = documents(tmp_path / "out")
    assert list(docs) == ["1234.emlx"] and "eigen risico 250 euro" in docs["1234.emlx"]["text"] and docs["1234.emlx"]["kind"] == "email"


def test_a_broken_mail_file_fails_only_itself(tmp_path):
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "bad.emlx").write_bytes(b"not a length\nrubbish")
    (tmp_path / "in" / "good.eml").write_bytes(bytes(message("Fine", "all good")))
    counts = parser.process_inbox(tmp_path / "in", tmp_path / "out", isolated=False)
    assert counts["failed"] == 1 and counts["parsed"] == 1
    with pytest.raises(ValueError, match="Apple Mail"):
        readers.read_emlx(tmp_path / "in" / "bad.emlx")


def test_logos_and_tracking_pixels_are_not_documents_but_a_real_scan_is(tmp_path):
    (tmp_path / "in").mkdir()
    m = message("Receipt", "see attached", {"logo.png": b"\x89PNG" + b"0" * 100, "scan.png": b"\x89PNG" + b"0" * 20000})
    (tmp_path / "in" / "r.eml").write_bytes(bytes(m))
    _, attachments = readers.read_eml(tmp_path / "in" / "r.eml")
    assert [name for name, _ in attachments] == ["scan.png"]


def test_the_message_cap_bounds_a_huge_mailbox(tmp_path):
    write_mbox(tmp_path / "big.mbox", [message(f"m{i}", "x") for i in range(7)])
    assert len(list(readers.mbox_messages(tmp_path / "big.mbox", limit=3))) == 3


def test_subject_labels_are_one_safe_line():
    raw = b"From: a@example.com\r\nSubject: Re: ../../etc/passwd\r\n evil\tsecond line\r\n\r\nbody\r\n"  # a folded header, as real mail has
    label = readers.mail_subject(raw)
    assert "/" not in label and "\n" not in label and "\t" not in label and len(label) <= 50 and "passwd" in label
    assert readers.mail_subject(b"From: a@example.com\r\n\r\nbody") == "no subject"


def test_a_ticket_that_arrived_by_email_can_be_found_and_shown_when_asked_for(tmp_path, conn):
    (tmp_path / "in").mkdir()
    write_mbox(
        tmp_path / "in" / "gmail.mbox",
        [
            message("Vliegtickets", "Uw tickets naar Bengaluru.", {"ticket.txt": b"Flight KL 879 AMS-BLR 12 Jan 2026 passenger Prasanna"}),
            message("Nieuwsbrief", "Aanbiedingen deze week."),
        ],
    )
    parser.process_inbox(tmp_path / "in", tmp_path / "out", isolated=False)
    store.ingest_dir(conn, tmp_path / "out")
    items = ask.find_items(conn, ["show me the flight tickets"], None)
    titles = [i["title"] for i in items]
    assert any(t.endswith("ticket.txt") for t in titles) and not any("Nieuwsbrief" in t for t in titles)  # the ticket is found, the newsletter is not
    assert all(i["kind"] == "document" and i["link"].startswith("#/doc/") for i in items)


def test_information_that_is_only_in_the_text_of_an_email_is_found_too(tmp_path, conn):
    (tmp_path / "in").mkdir()
    write_mbox(
        tmp_path / "in" / "all.mbox",
        [
            message("Uw reservering", "Uw vlucht KL879 vertrekt op 12 januari om 10:45 vanaf Schiphol, gate D7."),
            message("Betaling", "Wij hebben uw betaling van 62,50 ontvangen."),
        ],
    )
    parser.process_inbox(tmp_path / "in", tmp_path / "out", isolated=False)
    store.ingest_dir(conn, tmp_path / "out")
    assert ask.find_items(conn, ["show me the email about my flight"], None) == []  # an English question, a Dutch email: the words alone do not meet
    flight = ask.find_items(conn, ["show me the email about my flight"], ["vlucht", "reservering"])  # the model supplies the Dutch phrasings
    assert [i["title"] for i in flight] == ["all.mbox/00001 Uw reservering.eml"]
    assert "gate D7" in flight[0]["text"]  # no attachment at all: the text itself is the document
