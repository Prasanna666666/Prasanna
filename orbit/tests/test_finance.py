"""Finance import with a fake local model. The model reads the files; the code only checks and stores. All data here is invented."""

import json

import pytest

from orbit import categorize, extract, parser
from orbit.modules import documents, money


class FakeModel:
    """Stands in for the local model. A statement line like 'DATE|desc|amount|in/out|balance' is returned as the model would; the file kind comes
    from the first words of the text. `fail_after` makes it die part-way (Ollama stopped)."""

    def __init__(self, fail_after=None):
        self.calls = 0
        self.fail_after = fail_after

    def chat(self, model, messages, tools=None, schema=None, num_ctx=4096):
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise RuntimeError("Cannot reach the local model server")
        system, text = messages[0]["content"], messages[1]["content"]
        if system == extract.KIND_PROMPT:
            if "LOONSTROOK" in text:
                return {"content": json.dumps({"kind": "payslip", "period": "2026-10", "gross": 3500.0, "net": 2512.6, "tax": 812.4, "pension": 175.0, "holiday_pay": 280.0})}
            if "FACTUUR" in text:
                return {"content": json.dumps({"kind": "invoice", "title": "Internet oktober", "party": "Ziggo", "date": "2026-10-03", "due_date": "2026-10-17",
                                               "reference": "F-1001", "total": 60.5, "vat": 10.5, "currency": "EUR", "summary": "Monthly internet bill"})}
            if "KASSABON" in text:
                return {"content": json.dumps({"kind": "receipt", "title": "Groceries", "party": "Albert Heijn", "date": "2026-10-04", "total": 23.45, "vat": 1.9, "currency": "EUR"})}
            return {"content": json.dumps({"kind": "bank_statement" if "|" in text else "other", "title": "A letter"})}
        items = []
        for line in text.splitlines():
            parts = line.split("|")
            if len(parts) == 5:
                day, desc, amount, direction, balance = parts
                items.append({"date": day, "description": desc, "amount": float(amount), "direction": direction,
                              "balance": float(balance) if balance else None})
        return {"content": json.dumps({"transactions": items})}


STATEMENT = ["2026-10-01|Albert Heijn Utrecht|23.45|out|1976.55", "2026-10-25|Acme BV Salaris oktober|2850.00|in|4826.55", "2026-10-26|Huur oktober|1100.00|out|3726.55",
             "Pagina 1 van 2"]


def _load(conn, tmp_path, name, lines, area="finance", text=None):
    sha = (name.encode().hex() * 8)[:64]
    d = {"schema": 1, "sha256": sha, "name": name, "kind": "pdf", "text": text or "\n".join(lines), "meta": {}, "area": area, "data": {"lines": lines}}
    out = tmp_path / "parsed"
    out.mkdir(exist_ok=True)
    (out / f"{sha}.json").write_text(json.dumps(d))
    return documents.ingest_dir(conn, out)


def run(conn, model=None, **kw):
    return money.import_statements(conn, client=model or FakeModel(), model="fake", **kw)


def test_the_models_answer_is_checked_bad_items_are_dropped_and_arithmetic_fixes_a_backwards_direction():
    model = FakeModel()
    lines = ["2026-10-01|Shop|10.00|out|90.00", "2026-10-02|Refund|5.00|out|95.00", "2026-13-40|Impossible date|5|in|", "2026-10-03|Zero|0|in|", "no digits here? 7"]
    res = extract.read_statement(model, "fake", lines)
    assert [(t.day, t.amount_minor, t.kind) for t in res.txns] == [("2026-10-01", 1000, "expense"), ("2026-10-02", 500, "income")]  # balance 90 -> 95 means money came IN
    assert res.flipped == 1 and res.consistent == 1


def test_a_statement_is_imported_checked_and_stored_once(conn, tmp_path):
    _load(conn, tmp_path, "ing-2026-10.pdf", STATEMENT)
    r = run(conn)
    assert r["new_transactions"] == 3 and r["files"] == 1 and r["problems"] == []
    assert run(conn)["files"] == 0  # nothing new the second time
    _load(conn, tmp_path, "ing-2026-10-again.pdf", STATEMENT[:2] + ["x|y"])  # an overlapping download of the same period
    r2 = run(conn)
    assert r2["new_transactions"] == 0 and r2["already_had"] == 2
    assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 3


def test_a_payslip_is_read_by_the_model_and_is_not_a_bank_transaction(conn, tmp_path):
    _load(conn, tmp_path, "loonstrook-2026-10.pdf", ["x"], text="LOONSTROOK oktober 2026 bruto netto")
    r = run(conn)
    assert r["payslips"] == 1 and r["new_transactions"] == 0
    slip = money.list_payslips(conn)[0]
    assert (slip["period"], slip["gross"], slip["tax"], slip["pension"], slip["holiday"], slip["net"]) == ("2026-10", 3500.0, 812.4, 175.0, 280.0, 2512.6)
    assert money.statement_report(conn)[0]["payslip"] is True


def test_an_interrupted_import_resumes_without_duplicates(conn, tmp_path):
    many = [f"2026-10-{d:02d}|Shop {d}|1.00|out|" for d in range(1, 29)]  # two chunks
    _load(conn, tmp_path, "big.pdf", many)
    r = run(conn, FakeModel(fail_after=2))  # file kind (1) + first chunk (2), then the model stops
    assert r["problems"] and r["files"] == 0
    assert 0 < conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] < 28  # what was read is kept
    r2 = run(conn)
    assert r2["files"] == 1 and conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 28


def test_without_the_model_nothing_is_imported_and_you_are_told(conn, tmp_path):
    _load(conn, tmp_path, "a.pdf", STATEMENT)
    r = money.import_statements(conn)
    assert r["new_transactions"] == 0 and "Ollama" in r["problems"][0]
    assert conn.execute("SELECT COUNT(*) FROM statement_files").fetchone()[0] == 0  # not marked as read: the next run will do it


def test_files_outside_the_finance_folder_are_never_imported(conn, tmp_path):
    _load(conn, tmp_path, "notes.pdf", STATEMENT, area="")
    assert run(conn)["files"] == 0


def test_categories_rules_then_your_corrections(conn, tmp_path):
    assert categorize.categorise("UPI-SWIGGY-swiggy@icici-4567", "expense") == "food"
    assert categorize.categorise("SELF TRANSFER TO SAVINGS", "expense") == "transfers"
    assert categorize.categorise("RANDOM SHOP 1234", "expense") == "other"  # a payment to a shop is spending, never hidden as a transfer
    assert categorize.merchant("UPI-SWIGGY-swiggy@icici-4567-Order") == "swiggy"
    _load(conn, tmp_path, "oct.pdf", ["2026-10-01|Kiran Stores Utrecht|3.00|out|"])
    run(conn)
    assert conn.execute("SELECT category FROM transactions").fetchone()["category"] == "other" and money.uncategorised(conn)[0]["merchant"] == "kiran stores utrecht"
    money.set_category(conn, {"merchant": "Kiran Stores Utrecht", "category": "groceries"})
    assert conn.execute("SELECT category FROM transactions").fetchone()["category"] == "groceries" and categorize.learned_rules(conn)


def test_the_model_can_place_the_merchants_the_rules_miss(conn, tmp_path):
    _load(conn, tmp_path, "oct.pdf", ["2026-10-01|Kiran Stores Utrecht|3.00|out|"])
    run(conn)

    class Categoriser:
        def chat(self, model, messages, **kw):
            return {"content": '{"kiran stores utrecht": "groceries", "invented": "food"}'}

    assert categorize.recategorise_with_model(conn, Categoriser(), "fake") == 1
    assert conn.execute("SELECT category FROM transactions").fetchone()["category"] == "groceries"


def test_views_top_merchants_trend_and_recurring(conn, tmp_path):
    lines = []
    for m in (7, 8, 9, 10):
        lines += [f"2026-{m:02d}-05|NETFLIX.COM MUMBAI|649.00|out|", f"2026-{m:02d}-15|Swiggy order|400.00|out|"]
    lines.append("2026-10-20|SELF TRANSFER TO SAVINGS|10000.00|out|")
    _load(conn, tmp_path, "q.pdf", lines)
    run(conn)
    assert money.top_merchants(conn, {"month": "2026-10"})[0]["spent"] == 649.0  # the self-transfer is not spending
    assert [r["month"] for r in money.monthly_trend(conn, {"months": 12})] == ["2026-07", "2026-08", "2026-09", "2026-10"]
    names = [r["merchant"] for r in money.recurring_payments(conn)]
    assert any("netflix" in n for n in names) and any("swiggy" in n for n in names)
    assert money.summary(conn, {"month": "2026-10"})["spent"] == 1049.0


def test_the_parser_keeps_exact_csv_rows_with_any_delimiter_and_marks_the_finance_area(tmp_path):
    fin, out = tmp_path / "fin", tmp_path / "out"
    fin.mkdir()
    (fin / "ing.csv").write_text('"Datum";"Naam / Omschrijving";"Af Bij";"Bedrag (EUR)"\n"01-10-2026";"Jumbo; Utrecht";"Af";"12,34"\n', encoding="utf-8-sig")
    parser.process_inbox(fin, out, area="finance")
    doc = json.loads(next(out.glob("*.json")).read_text())
    assert doc["area"] == "finance" and doc["data"]["rows"][1] == ["01-10-2026", "Jumbo; Utrecht", "Af", "12,34"]


def test_visual_lines_join_the_cells_of_a_table_row():
    words = [(50, 100, 80, 110, "01/10/2026"), (120, 101, 160, 111, "SWIGGY"), (300, 99, 340, 109, "450.00"), (50, 130, 80, 140, "Page")]
    assert parser._visual_lines(words) == ["01/10/2026 SWIGGY 450.00", "Page"]


@pytest.mark.parametrize("bad", [{}, {"transactions": "x"}, {"transactions": [1, None, {"date": "2026-01-01"}]}])
def test_nonsense_from_the_model_never_crashes_the_import(bad):
    class Odd:
        def chat(self, *a, **k):
            return {"content": json.dumps(bad)}

    assert extract.read_statement(Odd(), "fake", ["2026-01-01 x 1"]).txns == []


def test_invoices_receipts_and_other_files_are_read_filed_and_summed_without_becoming_transactions(conn, tmp_path):
    _load(conn, tmp_path, "factuur-ziggo.pdf", ["x"], text="FACTUUR Ziggo oktober")
    _load(conn, tmp_path, "bon-ah.pdf", ["x"], text="KASSABON Albert Heijn")
    _load(conn, tmp_path, "brief.pdf", ["x"], text="Dear Sir")
    r = run(conn)
    assert r["files"] == 3 and r["new_transactions"] == 0 and r["files_with_no_transactions"] == []  # none of them is a failed statement
    inv = money.finance_documents(conn, {"kind": "invoice"})[0]
    assert (inv["party"], inv["date"], inv["due_date"], inv["reference"], inv["total"], inv["vat"], inv["currency"]) == ("Ziggo", "2026-10-03", "2026-10-17", "F-1001", 60.5, 10.5, "EUR")
    assert [d["party"] for d in money.finance_documents(conn, {"party": "albert"})] == ["Albert Heijn"]
    by_kind = {r["grp"]: r["total"] for r in money.finance_document_totals(conn, {"by": "kind"})}
    assert by_kind == {"invoice": 60.5, "receipt": 23.45}
    assert money.finance_document_totals(conn, {"by": "month"})[0]["grp"] == "2026-10"
