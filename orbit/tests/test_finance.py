"""Statement import, categorising and the money views. All data here is invented."""

import json

from orbit import categorize, parser, statements
from orbit.modules import documents, money

HDFC_STYLE = [
    ["Account Statement", "", "", "", "", "", ""],
    ["Date", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"],
    ["01/10/26", "UPI-SWIGGY-swiggy@icici-4567-Order", "0000123", "01/10/26", "450.00", "", "49,550.00"],
    ["02/10/26", "NEFT CR-ACME TECH PVT LTD-SALARY", "N123", "02/10/26", "", "85,000.00", "1,34,550.00"],
    ["03/10/26", "UPI-AMAZON PAY-amazon@apl-9988", "0000124", "03/10/26", "1,299.00", "", "1,33,251.00"],
    ["", "Opening Balance", "", "", "", "", ""],
    ["Total", "", "", "", "1,749.00", "85,000.00", ""],
]
SIGNED_AMOUNT = [["Transaction Date", "Description", "Amount (INR)"], ["2026-10-05", "Netflix.com", "-649.00"], ["2026-10-06", "Refund AMAZON", "200.00"]]
DR_CR = [["Txn Date", "Particulars", "Amount", "Dr/Cr"], ["05-Oct-2026", "ATM CASH WDL", "5,000.00", "Dr"], ["06-Oct-2026", "Interest credited", "12.50", "Cr"]]


def test_columns_are_recognised_by_their_words_in_three_different_bank_layouts():
    a = statements.from_rows(HDFC_STYLE)
    assert [(t.day, t.amount_minor, t.kind) for t in a] == [("2026-10-01", 45000, "expense"), ("2026-10-02", 8500000, "income"), ("2026-10-03", 129900, "expense")]
    assert a[0].balance_minor == 4955000 and "SWIGGY" in a[0].desc  # opening balance and totals rows were skipped
    b = statements.from_rows(SIGNED_AMOUNT)
    assert [(t.amount_minor, t.kind) for t in b] == [(64900, "expense"), (20000, "income")]
    c = statements.from_rows(DR_CR)
    assert [(t.day, t.amount_minor, t.kind) for t in c] == [("2026-10-05", 500000, "expense"), ("2026-10-06", 1250, "income")]


def test_amounts_and_dates_in_the_usual_formats():
    assert statements.parse_amount("Rs. 1,000.50 Cr") == (100050, "cr") and statements.parse_amount("(500.00)") == (-50000, None)
    assert statements.parse_amount("₹250 Dr") == (25000, "dr") and statements.parse_amount("abc") is None and statements.parse_amount("") is None
    assert statements.parse_date("05/10/2026") == "2026-10-05" and statements.parse_date("5 Oct 2026") == "2026-10-05"
    assert statements.parse_date("2026-10-05") == "2026-10-05" and statements.parse_date("Balance") is None


def test_pdf_style_lines_use_dr_cr_or_the_running_balance_to_find_the_direction():
    lines = ["Statement of account", "01/10/2026 UPI-ZOMATO-zomato@hdfc 380.00 49,620.00", "02/10/2026 SALARY ACME 85,000.00 1,34,620.00",
             "03/10/2026 POS CROMA 2,000.00 Dr", "Page 1 of 2"]
    got = statements.from_lines(lines)
    assert [(t.day, t.amount_minor, t.kind) for t in got] == [("2026-10-01", 38000, "expense"), ("2026-10-02", 8500000, "income"), ("2026-10-03", 200000, "expense")]


def test_the_same_line_twice_in_a_day_is_kept_but_a_repeated_import_adds_nothing():
    t = statements.Txn("2026-10-01", 15000, "expense", "Coffee", None)
    refs = [r for r, _ in statements.with_references([t, t])]
    assert len(set(refs)) == 2 and refs == [r for r, _ in statements.with_references([t, t])]


def _load(conn, tmp_path, name, rows=None, lines=None, area="finance"):
    sha = (name.encode().hex() * 8)[:64]
    d = {"schema": 1, "sha256": sha, "name": name, "kind": "csv", "text": "x", "meta": {}, "area": area, "data": {"rows": rows} if rows else {"lines": lines}}
    out = tmp_path / "parsed"
    out.mkdir(exist_ok=True)
    (out / f"{sha}.json").write_text(json.dumps(d))
    return documents.ingest_dir(conn, out)


def test_import_is_idempotent_across_runs_and_overlapping_statements(conn, tmp_path):
    _load(conn, tmp_path, "oct.csv", rows=HDFC_STYLE)
    r1 = money.import_statements(conn)
    assert r1["new_transactions"] == 3 and r1["files"] == 1
    assert money.import_statements(conn)["files"] == 0  # nothing new
    _load(conn, tmp_path, "oct-again.csv", rows=HDFC_STYLE[:4])  # an overlapping download of the same period
    r2 = money.import_statements(conn)
    assert r2["new_transactions"] == 0 and r2["already_had"] == 2
    assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 3


def test_files_outside_the_finance_folder_are_never_imported(conn, tmp_path):
    _load(conn, tmp_path, "notes.csv", rows=HDFC_STYLE, area="")
    assert money.import_statements(conn)["files"] == 0


def test_categories_rules_then_your_corrections(conn, tmp_path):
    assert categorize.categorise("UPI-SWIGGY-swiggy@icici-4567", "expense") == "food"
    assert categorize.categorise("NEFT CR-ACME TECH-SALARY", "income") == "salary"
    assert categorize.categorise("UPI-RANDOM SHOP-1234", "expense") == "other"  # a payment to a shop is spending, never hidden as a transfer
    assert categorize.categorise("SELF TRANSFER TO SAVINGS", "expense") == "transfers"
    assert categorize.merchant("UPI-SWIGGY-swiggy@icici-4567-Order") == "swiggy"
    _load(conn, tmp_path, "oct.csv", rows=[["Date", "Narration", "Withdrawal Amt.", "Deposit Amt."], ["01/10/26", "UPI-KIRAN STORES-kiran@ybl-11", "300.00", ""]])
    money.import_statements(conn)
    row = conn.execute("SELECT category FROM transactions").fetchone()
    assert row["category"] == "other" and money.uncategorised(conn)[0]["merchant"] == "kiran stores"
    money.set_category(conn, {"merchant": "UPI-KIRAN STORES-kiran@ybl-11", "category": "groceries"})
    assert conn.execute("SELECT category FROM transactions").fetchone()["category"] == "groceries"
    assert categorize.learned_rules(conn)  # remembered for future imports


def test_views_top_merchants_trend_and_recurring(conn, tmp_path):
    rows = [["Date", "Narration", "Withdrawal Amt.", "Deposit Amt."]]
    for m in (7, 8, 9, 10):
        rows.append([f"05/{m:02d}/26", "NETFLIX.COM MUMBAI", "649.00", ""])
        rows.append([f"15/{m:02d}/26", "UPI-SWIGGY-swiggy@icici-77", "400.00", ""])
    rows.append(["20/10/26", "SELF TRANSFER TO SAVINGS", "10,000.00", ""])
    _load(conn, tmp_path, "q.csv", rows=rows)
    money.import_statements(conn)
    assert money.top_merchants(conn, {"month": "2026-10"})[0]["spent"] == 649.0  # the self-transfer is not spending
    assert [r["month"] for r in money.monthly_trend(conn, {"months": 12})] == ["2026-07", "2026-08", "2026-09", "2026-10"]
    names = [r["merchant"] for r in money.recurring_payments(conn)]
    assert any("netflix" in n for n in names) and any("swiggy" in n for n in names)
    assert money.summary(conn, {"month": "2026-10"})["spent"] == 1049.0


def test_the_parser_keeps_exact_csv_rows_and_marks_the_finance_area(tmp_path):
    fin, out = tmp_path / "fin", tmp_path / "out"
    fin.mkdir()
    (fin / "oct.csv").write_text("Date,Narration,Withdrawal Amt.\n01/10/26,\"Shop, Main Road\",100.00\n")
    parser.process_inbox(fin, out, area="finance")
    doc = json.loads(next(out.glob("*.json")).read_text())
    assert doc["area"] == "finance" and doc["data"]["rows"][1] == ["01/10/26", "Shop, Main Road", "100.00"]
    assert statements.from_document(doc["data"])[0].desc == "Shop, Main Road"


def test_visual_lines_join_the_cells_of_a_table_row():
    words = [(50, 100, 80, 110, "01/10/2026"), (120, 101, 160, 111, "SWIGGY"), (300, 99, 340, 109, "450.00"), (50, 130, 80, 140, "Page")]
    assert parser._visual_lines(words) == ["01/10/2026 SWIGGY 450.00", "Page"]
