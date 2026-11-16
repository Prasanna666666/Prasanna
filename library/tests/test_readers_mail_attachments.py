"""Every document a mail carries is found, wherever it sits in the message."""

import email.message
import email.policy

from library import judging, readers


def test_every_attachment_of_a_mail_is_found_nested_unnamed_repeated_and_forwarded():
    m = email.message.EmailMessage()
    m["Subject"] = "x"
    m.set_content("hello")
    m.add_alternative("<p>hello</p>", subtype="html")
    m.add_attachment(b"%PDF-1 a" * 10, maintype="application", subtype="pdf", filename="a.pdf")
    m.add_attachment(b"%PDF-1 b" * 10, maintype="application", subtype="pdf")
    m.add_attachment(b"%PDF-1 c" * 10, maintype="application", subtype="pdf", filename="a.pdf")
    forwarded = email.message.EmailMessage()
    forwarded["Subject"] = "fw"
    forwarded.set_content("inner")
    forwarded.add_attachment(b"zz" * 20, maintype="application", subtype="pdf", filename="in.pdf")
    m.add_attachment(forwarded)
    doc, found = readers.read_message(email.message_from_bytes(m.as_bytes(), policy=email.policy.default))
    assert [n for n, _ in found] == ["a.pdf", "attachment.pdf", "2 a.pdf", "in.pdf"]
    assert doc["meta"]["attachments"] == 4


def test_only_the_declared_mailboxes_are_read_and_the_rest_are_skipped(monkeypatch):
    from pathlib import Path

    from library import parser

    monkeypatch.delenv("LIBRARY_MAILBOXES", raising=False)
    read = lambda p: not parser._in_skipped_mailbox(Path(p))  # noqa: E731
    assert (
        read("acc/INBOX.mbox/Data/Messages/1.emlx")
        and read("acc/Sent Messages.mbox/Data/Messages/2.emlx")
        and read("acc/[Gmail].mbox/Sent Mail.mbox/Messages/3.emlx")
        and read("acc/[Gmail].mbox/All Mail.mbox/Messages/4.emlx")
    )
    for skipped in (
        "acc/Promotions.mbox/Messages/1.emlx",
        "acc/Junk.mbox/Messages/1.emlx",
        "acc/INBOX.mbox/Newsletters.mbox/Messages/1.emlx",
        "acc/Archive.mbox/Messages/1.emlx",
        "acc/Bin.mbox/Messages/1.emlx",
        "acc/Outbox.mbox/Messages/1.emlx",
        "acc/[Gmail].mbox/Spam.mbox/Messages/1.emlx",
    ):
        assert not read(skipped)
    monkeypatch.setenv("LIBRARY_MAILBOXES", "archive")
    assert read("acc/Archive.mbox/Messages/1.emlx") and not read("acc/INBOX.mbox/Messages/1.emlx")


def test_mail_read_before_the_mailboxes_were_chosen_is_forgotten_and_nothing_else(conn, tmp_path):
    import json

    from library import store

    for i, (name, area) in enumerate((("m.eml", "mail"), ("m.eml/a.pdf", "mail"), ("keep.pdf", "finance"))):
        conn.execute("INSERT INTO documents (sha256, name, kind, text, area) VALUES (?,?,?,?,?)", (f"{i:064x}", name, "pdf", "t", area))
    conn.execute("INSERT INTO cases (input_hash, members, summary) VALUES ('h1', ?, ''), ('h2', ?, '')", (json.dumps([1, 3]), json.dumps([3])))
    conn.commit()
    (tmp_path / ".done").mkdir()
    (tmp_path / ".done" / f"{0:064x}").touch()
    assert store.forget_mail(conn, tmp_path) == 2
    assert [r["name"] for r in conn.execute("SELECT name FROM documents")] == ["keep.pdf"]
    assert [r["input_hash"] for r in conn.execute("SELECT input_hash FROM cases")] == ["h2"] and not (tmp_path / ".done" / f"{0:064x}").exists()


def test_stop_ends_a_wait_for_the_model_at_once_and_an_answer_that_comes_is_passed_on_otherwise():
    import threading
    import time

    gate = threading.Event()

    class Slow:
        def chat(self, *a, **k):
            gate.wait(30)
            return {"content": "late"}

        other = "kept"

    stop = threading.Event()
    model = judging.StoppableModel(Slow(), stop.is_set)
    assert model.other == "kept"  # everything but chat is passed on
    threading.Timer(0.5, stop.set).start()
    began = time.monotonic()
    try:
        model.chat("m", [])
        raise AssertionError("it should have stopped")
    except judging.Stopped:
        pass
    gate.set()
    assert time.monotonic() - began < 5  # not the 30 s the model would have taken
    assert judging.StoppableModel(Slow(), lambda: False).chat("m", []) == {"content": "late"}


def test_gmail_all_mail_is_read_but_bulk_mail_and_spam_are_not(tmp_path):
    from library import parser

    def put(path, headers):
        f = tmp_path / path
        f.parent.mkdir(parents=True, exist_ok=True)
        body = (headers + "\nSubject: x\n\nhello").encode()
        f.write_bytes(str(len(body)).encode() + b"\n" + body)

    put("V10/A/[Gmail].mbox/All Mail.mbox/U/Data/Messages/1.emlx", "From: a@example.org")
    put("V10/A/[Gmail].mbox/All Mail.mbox/U/Data/Messages/2.emlx", "From: n@example.org\nList-Unsubscribe: <mailto:x@example.org>")
    put("V10/A/[Gmail].mbox/All Mail.mbox/U/Data/Messages/3.emlx", "From: n@example.org\nPrecedence: bulk")
    put("V10/A/[Gmail].mbox/Spam.mbox/U/Data/Messages/4.emlx", "From: a@example.org")
    assert parser.mail_index(tmp_path, tmp_path / "out").mails == 1


def test_the_rules_for_which_mail_is_read_have_a_fingerprint_that_changes_with_them(monkeypatch):
    from library import web

    monkeypatch.delenv("LIBRARY_MAILBOXES", raising=False)
    first = web._mail_scope()
    assert first == web._mail_scope()
    monkeypatch.setenv("LIBRARY_MAILBOXES", "archive")
    assert web._mail_scope() != first


def test_attachments_apple_mail_keeps_beside_its_messages_are_found_and_read(tmp_path):
    import json

    from library import parser

    box = tmp_path / "V10/A/[Gmail].mbox/All Mail.mbox/U/Data/1/Messages"
    att = tmp_path / "V10/A/[Gmail].mbox/All Mail.mbox/U/Data/1/Attachments"
    spam = tmp_path / "V10/A/[Gmail].mbox/Spam.mbox/U/Data/1/Attachments/9/1"
    for folder in (box, att / "5/1", att / "6/1", spam):
        folder.mkdir(parents=True)
    for number, headers in (("5", "From: a@example.org"), ("6", "From: n@example.org\nList-Unsubscribe: <x>")):
        body = (headers + "\nSubject: x\n\nhello").encode()
        (box / f"{number}.partial.emlx").write_bytes(str(len(body)).encode() + b"\n" + body)
    (att / "5/1/report.txt").write_text("Quarterly report with some words in it. " * 5)
    (att / "6/1/offer.txt").write_text("Special offer. " * 10)  # belongs to a newsletter
    (spam / "x.txt").write_text("spam " * 20)  # a mailbox that is not read
    assert [relative.rsplit("/", 1)[-1] for _, relative in parser.mail_index(tmp_path, tmp_path / "idx").attachments] == ["report.txt"]
    parser._MAIL_INDEX.clear()
    out = tmp_path / "out"
    assert parser.process_mail_attachments(tmp_path, out, isolated=False)["parsed"] == 1
    assert [json.loads(p.read_text())["name"] for p in out.glob("*.json")] == ["5/1/report.txt"]


def test_a_google_export_marks_spam_promotions_and_trash_by_the_labels_it_carries(tmp_path):
    from library import parser

    def put(name, labels):
        f = tmp_path / name
        f.write_bytes(f"From: a@example.org\nX-Gmail-Labels: {labels}\nSubject: x\n\nhello".encode())
        return f

    assert not parser.is_bulk_mail(put("a.eml", "Inbox,Important,Category Updates"))
    assert not parser.is_bulk_mail(put("b.eml", "Sent"))
    for labels in ("Spam", "Inbox,Category Promotions", "Trash", "Category Social,Unread"):
        assert parser.is_bulk_mail(put("c.eml", labels))
