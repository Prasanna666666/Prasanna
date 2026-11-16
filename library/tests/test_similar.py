"""Documents that read alike are asked about once; what the model said is the model's, the fingerprint only says "reads like"."""

import json

from library import similar, store


def _add(conn, name, text):
    conn.execute("INSERT INTO documents (sha256, name, kind, text, area, judged) VALUES (?,?,?,?,?,0)", (f"{abs(hash(name)):064x}"[:64], name, "pdf", text, ""))


def test_a_document_that_reads_like_one_found_to_be_about_no_app_gets_its_answer_without_the_model(conn, monkeypatch):
    monkeypatch.setattr(store, "PARALLEL", 1)  # one at a time, so what was learned from the first is there for the second
    base = " ".join(f"signal{i % 40} stage{i % 7} clock{i % 13}" for i in range(120))
    _add(conn, "a.vhd", base)
    _add(conn, "b.vhd", base + " one more small line")  # almost the same
    _add(conn, "c.txt", "Dear Prasanna please find the invoice for your internet subscription this month " * 3)
    conn.commit()
    asked = []

    class Model:
        def chat(self, model, messages, **kw):
            asked.append(messages[-1]["content"][:20])
            return {"content": json.dumps({"kind": "circuit design", "title": "t", "apps": []})}

    assert store.judge_pending(conn, Model(), "m")["read"] == 3
    assert len(asked) == 2  # a.vhd and c.txt were asked about; b.vhd reads like a.vhd and was not
    row = conn.execute("SELECT facts FROM documents WHERE name='b.vhd'").fetchone()
    assert json.loads(row[0])["kind"] == "circuit design" and json.loads(row[0])["inherited"] is True


def test_the_fingerprint_tells_alike_from_different():
    a = similar.signature(" ".join(f"w{i} x{i % 5} y{i % 3}" for i in range(100)))
    assert similar.similarity(a, a) == 1.0
    other = similar.signature(" ".join(f"totally{i} different{i % 9} words{i % 4}" for i in range(100)))
    assert similar.similarity(a, other) < similar.SAME
    assert similar.signature("too short") is None
