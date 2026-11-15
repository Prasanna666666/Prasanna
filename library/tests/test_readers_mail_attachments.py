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
