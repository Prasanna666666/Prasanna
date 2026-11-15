"""Every document a mail carries is found, wherever it sits in the message."""

import email.message
import email.policy

from library import readers


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
    )
    for skipped in (
        "acc/Promotions.mbox/Messages/1.emlx",
        "acc/Junk.mbox/Messages/1.emlx",
        "acc/INBOX.mbox/Newsletters.mbox/Messages/1.emlx",
        "acc/Archive.mbox/Messages/1.emlx",
        "acc/[Gmail].mbox/All Mail.mbox/Messages/1.emlx",
    ):
        assert not read(skipped)
    monkeypatch.setenv("LIBRARY_MAILBOXES", "archive")
    assert read("acc/Archive.mbox/Messages/1.emlx") and not read("acc/INBOX.mbox/Messages/1.emlx")
