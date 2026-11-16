"""The whole read, from files on disk to grouped documents, against what the person asked for: nothing is read twice, nothing is lost without being said, sorting never starts while the
reader is busy, every counted file is accounted for, the same documents have the same number in every step, a model that fails sometimes still sorts every file, and a second read
does nothing new."""

import http.client
import json
import threading
import time
from http.server import ThreadingHTTPServer

import pytest
from kit import db

from library import parser, store, web


def _emlx(path, headers, body="Please find the document attached."):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = f"{headers}\nSubject: s\n\n{body}".encode()
    path.write_bytes(str(len(raw)).encode() + b"\n" + raw)


@pytest.fixture
def library(tmp_path, monkeypatch):
    inbox, parsed, mail, home = tmp_path / "in", tmp_path / "parsed", tmp_path / "mail", tmp_path / "home"
    for d in (inbox, parsed, home):
        d.mkdir()
    # documents: an invoice, a ticket, a copy of the invoice, three circuit files, an empty file (not a document), a file nothing can read
    invoice = "FACTUUR Hotel Delhi 12-01-2026 totaal 480,00 EUR betaling ontvangen " * 3
    (inbox / "hotel.txt").write_text(invoice)
    (inbox / "hotel copy.txt").write_text(invoice)
    (inbox / "ticket.txt").write_text("BOARDING PASS flight Amsterdam to Delhi 2026-03-01 seat 12A " * 3)
    for i in range(3):
        (inbox / f"adder{i}.vhd").write_text(f"entity adder{i} is port ( a : in bit; b : in bit ); end entity; architecture rtl of adder{i} is begin end; " * 2)
    (inbox / "empty.txt").write_text("")
    (inbox / "broken.pdf").write_bytes(b"%PDF-1.4 this is not a real pdf at all " * 5)
    # mail: Gmail keeps everything in All Mail; spam is a mailbox of its own; a newsletter carries an unsubscribe header
    base = mail / "V10/ACC/[Gmail].mbox/All Mail.mbox/U/Data/1"
    _emlx(base / "Messages/1.emlx", "From: a@example.org", "Your electricity invoice is attached. Total 60,50 EUR.")
    _emlx(base / "Messages/2.partial.emlx", "From: b@example.org", "Second message with a stored attachment.")
    _emlx(base / "Messages/3.emlx", "From: news@example.org\nList-Unsubscribe: <mailto:u@example.org>", "Big sale!")
    _emlx(mail / "V10/ACC/[Gmail].mbox/Spam.mbox/U/Data/1/Messages/4.emlx", "From: s@example.org", "You won")
    for message in ("2", "5"):  # the same attachment (a logo) in two messages
        folder = base / "Attachments" / message / "1"
        folder.mkdir(parents=True)
        (folder / "report.txt").write_text("Quarterly report with figures and words in it. " * 6)
    (base / "Attachments/2/2").mkdir()
    (base / "Attachments/2/2/invoice.txt").write_text("FACTUUR Electricity Co 2026-02-01 totaal 60,50 EUR " * 4)
    monkeypatch.setenv("ATLAS_ALLOW_PLAIN", "1")
    monkeypatch.setenv("ATLAS_HOME", str(home))
    monkeypatch.setenv("ATLAS_PARSED", str(parsed))
    monkeypatch.setenv("LIBRARY_GENTLE_SECONDS", "0")
    monkeypatch.setattr(web, "SETTLE_SECONDS", 0.05)
    monkeypatch.setattr(parser, "GENTLE_SECONDS", 0)
    monkeypatch.setattr(parser, "ROUND_SECONDS", 0)
    monkeypatch.setattr(store, "GENTLE_SECONDS", 0)
    return tmp_path, inbox, parsed, mail


class FakeModel:
    """Sorts by what the text says. It fails once on the first circuit file (cut off), and records whether the reader was busy whenever it was asked."""

    def __init__(self, parsed):
        self.parsed, self.calls, self.busy_calls, self.failed_once = parsed, 0, 0, False

    def chat(self, model, messages, schema=None, **kw):
        self.calls += 1
        self.busy_calls += (self.parsed / ".busy").exists()
        text = messages[-1]["content"]
        if "adder0" in text and not self.failed_once:
            self.failed_once = True
            return {"content": "{cut off"}
        if not schema:
            return {"content": "ok"}
        low = text.lower()
        if "factuur" in low or "invoice" in low:
            answer = {"kind": "invoice", "apps": ["finance"], "title": "Invoice", "total": "480,00" if "480,00" in text else None, "currency": "EUR"}
        elif "boarding" in low:
            answer = {"kind": "ticket", "apps": ["travel"], "title": "Flight", "place": "Delhi"}
        else:
            answer = {"kind": "circuit design" if "entity" in low else "report", "apps": [], "title": "t"}
        return {"content": json.dumps({k: v for k, v in answer.items() if v is not None})}


def _run_read(tmp_path, inbox, parsed, mail, monkeypatch):
    model = FakeModel(parsed)
    monkeypatch.setattr(web, "model_client", lambda: (model, "fake"))
    reader = threading.Thread(
        target=parser.main, args=(["--inbox", str(inbox), "--out", str(parsed), "--mail", str(mail), "--watch"],), daemon=True
    )  # the reader waits for the request, as in the real setup
    reader.start()
    state = web.State()
    conn = state.connect()
    db.migrate(conn, [store.MODULE])
    conn.close()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(state))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return state, httpd, model


def _scan(httpd):
    c = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=20)
    c.request("GET", "/api/scan", headers={"Host": f"127.0.0.1:{httpd.server_address[1]}"})
    return json.loads(c.getresponse().read())


def _press(state, httpd):
    """Press Read; returns the last status of the read itself (with its steps) and what the card says once it has finished (the unread files)."""
    assert web.start_scan(state)
    last = {}
    for _ in range(600):
        time.sleep(0.05)
        status = _scan(httpd)
        if status["steps"]:
            last = status
        if not status["running"]:
            return {**last, "unread_files": status["unread_files"], "problems": status["problems"]}
    raise AssertionError("the read did not finish")


def test_the_whole_read_keeps_every_promise(library, monkeypatch):
    tmp_path, inbox, parsed, mail = library
    state, httpd, model = _run_read(tmp_path, inbox, parsed, mail, monkeypatch)
    status = _press(state, httpd)
    conn = state.connect()
    names = {r["name"]: r for r in conn.execute("SELECT name, judged, case_id, area, kind FROM documents")}
    docs = [n for n in names if not n.startswith("V10") or "/" in n]

    # Read: newsletters and spam are not read, copies are one document, an empty file is no document, what cannot be read is said by name
    assert not any("List-Unsubscribe" in (r[0] or "") for r in conn.execute("SELECT text FROM documents"))
    assert not any("You won" in (r[0] or "") for r in conn.execute("SELECT text FROM documents"))
    assert sum(1 for n in names if n in ("hotel.txt", "hotel copy.txt")) == 1  # identical content is held once
    assert "empty.txt" not in names
    assert any(line.startswith("broken.pdf") for line in status["unread_files"])  # said, with the reason

    # Sort: every file the model is asked about ends sorted, even the one whose first answer was cut off
    assert not conn.execute("SELECT 1 FROM documents WHERE judged IN (0, 3)").fetchall()
    assert names["adder0.vhd"]["judged"] == 1
    assert model.busy_calls == 0  # sorting never started while the reader was busy

    # Group: everything sorted as about something is grouped
    assert not conn.execute("SELECT name FROM documents WHERE judged=1 AND case_id IS NULL AND kind<>'email'").fetchall()

    # The card: the documents have one number in every step, and each line accounts for every counted file
    steps = web._steps(conn, {"phase": 4})  # the numbers as the card works them out at the end (the status itself reuses them for a few seconds)
    totals = {s["n"]: next(c for c in s["counts"] if c["key"] == "documents")["total"] for s in steps}
    assert len(set(totals.values())) == 1, totals
    for line in steps[0]["counts"]:
        assert line["done"] + line["copies"] + line["unread"] >= line["total"] or line["total"] == 0, line
    assert [s["state"] for s in steps][:2] == ["done", "done"]

    # A second read changes nothing and asks the model nothing new
    calls, held = model.calls, conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    conn.close()
    _press(state, httpd)
    conn = state.connect()
    assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == held and model.calls - calls <= 1
    conn.close()
    httpd.shutdown()
    assert docs
