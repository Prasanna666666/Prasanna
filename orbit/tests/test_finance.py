"""Finance import. The (fake) local model says what a file is and what its COLUMNS are; code reads every figure and proves the result.
All data here is invented."""

import json

import pytest

from orbit import categorize, extract, parser, tables
from orbit.modules import documents, money

COLS = [(0, 60), (70, 200), (210, 260), (270, 320), (330, 400)]
HEAD = ["Datum", "Omschrijving", "Af", "Bij", "Saldo"]
LAYOUT = {"header_line": 0, "roles": ["date", "description", "debit", "credit", "balance"], "date_format": "%d-%m-%Y", "month_names": [],
          "decimal": ",", "thousands": ".", "debit_words": ["af"], "credit_words": ["bij"], "date_on_every_row": True}
GOOD = [HEAD, ["01-10-2026", "Opening", "", "", "2.000,00"], ["01-10-2026", "Albert Heijn Utrecht", "23,45", "", "1.976,55"],
        ["25-10-2026", "Acme BV Salaris oktober", "", "2.850,00", "4.826,55"], ["26-10-2026", "Huur oktober", "1.100,00", "", "3.726,55"]]


def table_of(rows, cols=COLS):
    return [[[cols[i][0], cols[i][1], c] for i, c in enumerate(r) if c != ""] for r in rows]


class FakeModel:
    """Stands in for the local model. It answers the two questions the app asks: what is this file, and what are its columns?"""

    def __init__(self, layout=None, fail_after=None, kind=None):
        self.layout, self.calls, self.fail_after, self.kind = layout or LAYOUT, 0, fail_after, kind

    def chat(self, model, messages, tools=None, schema=None, num_ctx=4096):
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise RuntimeError("Cannot reach the local model server")
        system, text = messages[0]["content"], messages[1]["content"]
        if system == extract.KIND_PROMPT:
            if self.kind:
                return {"content": json.dumps(self.kind(text))}
            if "LOONSTROOK" in text:
                return {"content": json.dumps({"kind": "payslip", "period": "2026-10", "gross": "3.500,00", "net": "2.512,60", "tax": "812,40", "pension": "175,00", "holiday_pay": "280,00"})}
            if "FACTUUR" in text:
                return {"content": json.dumps({"kind": "invoice", "title": "Internet", "party": "Ziggo", "date": "2026-10-03", "reference": "F-1001", "total": "60,50", "vat": "10,50", "currency": "EUR"})}
            return {"content": json.dumps({"kind": "bank_statement" if "Datum" in text else "other", "title": "x"})}
        if system == tables.LAYOUT_PROMPT:
            return {"content": json.dumps(self.layout)}
        return {"content": "{}"}


def _load(conn, tmp_path, name, rows=None, text=None, area="finance", cols=COLS):
    sha = (name.encode().hex() * 8)[:64]
    shown = text if text is not None else "\n".join(" ".join(r) for r in (rows or []))
    d = {"schema": 1, "sha256": sha, "name": name, "kind": "pdf", "text": shown, "meta": {}, "area": area, "data": {"table": table_of(rows, cols)} if rows else {"lines": [shown]}}
    out = tmp_path / "parsed"
    out.mkdir(exist_ok=True)
    (out / f"{sha}.json").write_text(json.dumps(d))
    return documents.ingest_dir(conn, out)


def run(conn, model=None, **kw):
    return money.import_statements(conn, client=model or FakeModel(), model="fake", **kw)


def read(rows, layout=None):
    table = [[tables.Cell(*c) for c in line] for line in table_of(rows)]
    return tables.parse_table(table, tables.Layout(**(layout or LAYOUT)))


# ---- the proofs -------------------------------------------------------------------------------------------------------------
def test_a_statement_is_read_by_code_and_proved_by_its_balances():
    p = read(GOOD)
    assert p.status == "verified" and p.issues == [] and p.checked == 3
    assert [(t.day, t.amount_minor, t.kind, t.balance_minor) for t in p.txns] == [
        ("2026-10-01", 2345, "expense", 197655), ("2026-10-25", 285000, "income", 482655), ("2026-10-26", 110000, "expense", 372655)]


def test_a_statement_printed_newest_first_is_still_proved():
    p = read([HEAD, *GOOD[1:][::-1]])
    assert p.status == "verified" and len(p.txns) == 3


def test_one_wrong_cent_anywhere_and_nothing_is_trusted():
    bad = [list(r) for r in GOOD]
    bad[3][4] = "4.826,56"
    p = read(bad)
    assert p.status == "needs_check" and "balances do not add up" in p.issues[0]


def test_a_missing_line_breaks_the_balances_and_is_caught():
    p = read([r for i, r in enumerate(GOOD) if i != 3])  # the salary line was lost
    assert p.status == "needs_check"


def test_a_line_with_an_amount_but_no_date_is_reported_never_dropped_quietly():
    p = read([*GOOD, ["", "Totaal", "1.123,45", "2.850,00", ""]])
    assert p.status == "needs_check" and any("has an amount but no date" in i for i in p.issues)


def test_a_statement_that_prints_the_date_once_per_group_carries_it_forward():
    layout = {**LAYOUT, "date_on_every_row": False}
    rows = [HEAD, ["01-10-2026", "Opening", "", "", "100,00"], ["02-10-2026", "Shop A", "10,00", "", "90,00"], ["", "Shop B", "5,00", "", "85,00"]]
    p = read(rows, layout)
    assert p.status == "verified" and [(t.day, t.amount_minor) for t in p.txns] == [("2026-10-02", 1000), ("2026-10-02", 500)]


def test_an_unsigned_amount_with_a_direction_word_is_settled_by_the_words_and_the_balances():
    layout = {**LAYOUT, "roles": ["date", "description", "amount", "direction", "balance"]}
    rows = [HEAD, ["01-10-2026", "Opening", "", "", "100,00"], ["02-10-2026", "Shop", "10,00", "Af", "90,00"], ["03-10-2026", "Salary", "50,00", "Bij", "140,00"]]
    p = read(rows, layout)
    assert p.status == "verified" and [t.kind for t in p.txns] == ["expense", "income"]
    layout["debit_words"] = layout["credit_words"] = []  # no words at all: the balances alone decide
    assert [t.kind for t in read(rows, layout).txns] == ["expense", "income"]


def test_dutch_month_names_and_wrapped_descriptions():
    layout = {**LAYOUT, "date_format": "%d %b %Y", "month_names": ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]}
    rows = [HEAD, ["1 okt 2026", "Opening", "", "", "100,00"], ["3 mrt. 2026", "Shop", "10,00", "", "90,00"], ["", "Utrecht Centrum pas 12", "", "", ""]]
    rows[1][0] = "1 okt 2026"
    p = read(rows, layout)
    assert p.txns[0].day == "2026-03-03" and p.txns[0].desc == "Shop Utrecht Centrum pas 12"


def test_without_balances_the_file_is_imported_but_marked_unverified():
    p = read([HEAD, ["01-10-2026", "Shop", "10,00", "", ""], ["02-10-2026", "Salaris", "", "50,00", ""]])
    assert p.status == "unverified" and len(p.txns) == 2


def test_an_amount_whose_direction_cannot_be_known_is_never_guessed():
    layout = {**LAYOUT, "roles": ["date", "description", "amount", "ignore", "ignore"]}
    p = read([HEAD, ["01-10-2026", "Mystery", "10,00", "", ""]], layout)
    assert p.status == "needs_check" and "cannot tell whether" in p.issues[0]


def test_the_layout_the_model_describes_is_checked_before_it_is_used():
    class Silly:
        def chat(self, *a, **k):
            return {"content": json.dumps({"header_line": 99, "roles": ["date"], "date_format": "x", "decimal": "."})}

    cells = [[tables.Cell(0, 50, "a")]]
    assert tables.infer_layout(Silly(), "m", cells) is None  # a header that is not in the file
    assert tables.infer_layout(Silly(), "m", []) is None


def test_printed_amounts_are_read_from_the_figure_itself():
    assert tables.money_from_printed("3.500,00") == 350000 and tables.money_from_printed("1,234.56") == 123456
    assert tables.money_from_printed("€ 61") == 6100 and tables.money_from_printed("60,5") == 6050 and tables.money_from_printed("abc") is None


def test_an_amount_the_model_made_up_is_dropped_because_it_is_not_in_the_document():
    text = "Factuur Ziggo totaal 60,50 btw 10,50"
    checked = extract.verify_amounts({"kind": "invoice", "total": "60,50", "vat": "99,99"}, text)
    assert checked["total"] == 60.5 and checked["vat"] is None and checked["unverified_fields"] == ["vat"]


# ---- the whole import --------------------------------------------------------------------------------------------------------
def test_a_good_statement_is_imported_once_and_marked_verified(conn, tmp_path):
    _load(conn, tmp_path, "ing-2026-10.pdf", GOOD)
    r = run(conn)
    assert r["new_transactions"] == 3 and r["needs_check"] == [] and r["problems"] == []
    assert conn.execute("SELECT status FROM statement_files").fetchone()["status"] == "verified"
    assert run(conn)["files"] == 0  # nothing new the second time
    _load(conn, tmp_path, "ing-2026-10-again.pdf", GOOD[:4])  # an overlapping download of the same period
    r2 = run(conn)
    assert r2["new_transactions"] == 0 and r2["already_had"] == 2 and conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 3


def test_a_file_that_fails_its_proof_adds_nothing_to_your_totals_and_says_why(conn, tmp_path):
    bad = [list(r) for r in GOOD]
    bad[3][4] = "4.826,56"
    _load(conn, tmp_path, "broken.pdf", bad)
    r = run(conn)
    assert r["new_transactions"] == 0 and r["needs_check"][0]["file"] == "broken.pdf"
    assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0
    assert money.files_to_check(conn)[0]["status"] == "needs_check" and "do not add up" in money.files_to_check(conn)[0]["issues"]


def test_a_layout_nobody_can_understand_is_refused_not_guessed(conn, tmp_path):
    _load(conn, tmp_path, "odd.pdf", GOOD)
    r = run(conn, FakeModel(layout={"header_line": 50, "roles": [], "date_format": "", "decimal": "."}))
    assert r["new_transactions"] == 0 and "could not be understood" in r["needs_check"][0]["issues"][0]


def test_a_payslip_is_read_from_its_printed_figures_and_not_a_bank_transaction(conn, tmp_path):
    _load(conn, tmp_path, "loonstrook-2026-10.pdf", None, text="LOONSTROOK oktober 2026 Bruto loon 3.500,00 Pensioen 175,00 Loonheffing 812,40 Vakantiegeld 280,00 Netto loon 2.512,60")
    r = run(conn)
    assert r["payslips"] == 1 and r["new_transactions"] == 0
    slip = money.list_payslips(conn)[0]
    assert (slip["period"], slip["gross"], slip["tax"], slip["pension"], slip["holiday"], slip["net"]) == ("2026-10", 3500.0, 812.4, 175.0, 280.0, 2512.6)


def test_a_payslip_with_an_amount_not_in_the_document_is_rejected(conn, tmp_path):
    _load(conn, tmp_path, "loonstrook.pdf", None, text="LOONSTROOK oktober 2026 Bruto loon 3.500,00 Loonheffing 812,40")  # no net amount printed: the model's net is invented
    assert run(conn)["payslips"] == 0


def test_invoices_are_filed_with_verified_totals(conn, tmp_path):
    _load(conn, tmp_path, "factuur.pdf", None, text="FACTUUR Ziggo oktober totaal 60,50 waarvan btw 10,50")
    r = run(conn)
    assert r["files"] == 1 and r["new_transactions"] == 0 and r["needs_check"] == []
    inv = money.finance_documents(conn, {"kind": "invoice"})[0]
    assert (inv["party"], inv["total"], inv["vat"]) == ("Ziggo", 60.5, 10.5)


def test_without_the_model_nothing_is_imported_and_you_are_told(conn, tmp_path):
    _load(conn, tmp_path, "a.pdf", GOOD)
    r = money.import_statements(conn)
    assert r["new_transactions"] == 0 and "Ollama" in r["problems"][0]
    assert conn.execute("SELECT COUNT(*) FROM statement_files").fetchone()[0] == 0


def test_files_outside_the_finance_folder_are_never_imported(conn, tmp_path):
    _load(conn, tmp_path, "notes.pdf", GOOD, area="")
    assert run(conn)["files"] == 0


def test_categories_rules_then_your_corrections(conn, tmp_path):
    assert categorize.categorise("UPI-SWIGGY-swiggy@icici-4567", "expense") == "food"
    assert categorize.categorise("SELF TRANSFER TO SAVINGS", "expense") == "transfers"
    assert categorize.categorise("RANDOM SHOP 1234", "expense") == "other"
    assert categorize.merchant("UPI-SWIGGY-swiggy@icici-4567-Order") == "swiggy"
    _load(conn, tmp_path, "oct.pdf", [HEAD, ["01-10-2026", "Kiran Stores Utrecht", "3,00", "", ""]])
    run(conn)
    assert conn.execute("SELECT category FROM transactions").fetchone()["category"] == "other" and money.uncategorised(conn)[0]["merchant"] == "kiran stores utrecht"
    money.set_category(conn, {"merchant": "Kiran Stores Utrecht", "category": "groceries"})
    assert conn.execute("SELECT category FROM transactions").fetchone()["category"] == "groceries" and categorize.learned_rules(conn)


def test_the_model_can_place_the_merchants_the_rules_miss(conn, tmp_path):
    _load(conn, tmp_path, "oct.pdf", [HEAD, ["01-10-2026", "Kiran Stores Utrecht", "3,00", "", ""]])
    run(conn)

    class Categoriser:
        def chat(self, model, messages, **kw):
            return {"content": '{"kiran stores utrecht": "groceries", "invented": "food"}'}

    assert categorize.recategorise_with_model(conn, Categoriser(), "fake") == 1


def test_views_top_merchants_trend_and_recurring(conn, tmp_path):
    rows = [HEAD]
    for m in (7, 8, 9, 10):
        rows += [[f"05-{m:02d}-2026", "NETFLIX.COM MUMBAI", "649,00", "", ""], [f"15-{m:02d}-2026", "Swiggy order", "400,00", "", ""]]
    rows.append(["20-10-2026", "SELF TRANSFER TO SAVINGS", "10.000,00", "", ""])
    _load(conn, tmp_path, "q.pdf", rows)
    run(conn)
    assert money.top_merchants(conn, {"month": "2026-10"})[0]["spent"] == 649.0
    assert [r["month"] for r in money.monthly_trend(conn, {"months": 12})] == ["2026-07", "2026-08", "2026-09", "2026-10"]
    names = [r["merchant"] for r in money.recurring_payments(conn)]
    assert any("netflix" in n for n in names) and any("swiggy" in n for n in names)
    assert money.summary(conn, {"month": "2026-10"})["spent"] == 1049.0


# ---- the parser keeps positions so columns can be recovered ---------------------------------------------------------------
def test_the_parser_keeps_exact_csv_rows_with_any_delimiter_and_marks_the_finance_area(tmp_path):
    fin, out = tmp_path / "fin", tmp_path / "out"
    fin.mkdir()
    (fin / "ing.csv").write_text('"Datum";"Naam / Omschrijving";"Af Bij";"Bedrag (EUR)"\n"01-10-2026";"Jumbo; Utrecht";"Af";"12,34"\n', encoding="utf-8-sig")
    parser.process_inbox(fin, out, area="finance")
    doc = json.loads(next(out.glob("*.json")).read_text())
    assert doc["area"] == "finance" and doc["data"]["rows"][1] == ["01-10-2026", "Jumbo; Utrecht", "Af", "12,34"]
    assert [[c.text for c in line] for line in tables.table_from_data(doc["data"])][1] == ["01-10-2026", "Jumbo; Utrecht", "Af", "12,34"]


def test_pdf_words_become_cells_with_positions():
    words = [(50, 100, 80, 110, "01/10/2026"), (120, 101, 160, 111, "SWIGGY"), (164, 101, 190, 111, "Utrecht"), (300, 99, 340, 109, "450.00"), (50, 130, 80, 140, "Page")]
    cells = parser._table_lines(words)
    assert [[c[2] for c in line] for line in cells] == [["01/10/2026", "SWIGGY Utrecht", "450.00"], ["Page"]]  # close words share a cell, a wide gap starts another
    assert cells[0][2][0] == 300


@pytest.mark.parametrize("bad", ["", "not json", "[1,2]"])
def test_nonsense_from_the_model_never_crashes_the_import(bad):
    class Odd:
        def chat(self, *a, **k):
            return {"content": bad}

    assert extract.classify(Odd(), "m", "x.pdf", "text")["kind"] == "other"
    assert tables.infer_layout(Odd(), "m", [[tables.Cell(0, 1, "a")]]) is None
