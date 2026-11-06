"""The verifier agents: each one must pass good data and FAIL bad data. All data is invented."""

import json
from datetime import date, timedelta

from finance import tables, verify
from finance.modules import documents, money
from tests.test_standards import CAMT, MT940

LAYOUT = {
    "header_line": 0,
    "roles": ["date", "description", "debit", "credit", "balance"],
    "date_format": "%d-%m-%Y",
    "month_names": [],
    "decimal": ",",
    "thousands": ".",
    "debit_words": [],
    "credit_words": [],
    "date_on_every_row": True,
}
COLS = [(0, 60), (70, 200), (210, 260), (270, 320), (330, 400)]


def table(rows, cols=COLS):
    return [[tables.Cell(cols[i][0], cols[i][1], c) for i, c in enumerate(r) if c != ""] for r in rows]


class Model:
    """Answers the layout question from a list, one answer per call."""

    def __init__(self, *layouts):
        self.layouts, self.calls = list(layouts), 0

    def chat(self, model, messages, tools=None, schema=None, num_ctx=4096):
        layout = self.layouts[min(self.calls, len(self.layouts) - 1)]
        self.calls += 1
        return {"content": json.dumps(layout)}


def data_of(rows, cols=COLS):
    return {"table": [[[cols[i][0], cols[i][1], c] for i, c in enumerate(r) if c != ""] for r in rows]}


def long_statement(n=14):
    rows, bal = [["Datum", "Omschrijving", "Af", "Bij", "Saldo"], ["01-10-2026", "Opening", "", "", "1.000,00"]], 100000
    for i in range(n):
        amt = 1000 + i * 111
        bal -= amt
        rows.append([f"{2 + i:02d}-10-2026", f"Shop {i}", f"{amt // 100},{amt % 100:02d}", "", f"{bal // 100:,}".replace(",", ".") + f",{bal % 100:02d}"])
    return rows


# ---- file-level agents --------------------------------------------------------------------------------------------------------
def test_a_statement_read_the_same_way_twice_passes_the_second_reader():
    r = verify.read_table_statement(Model(LAYOUT), "m", "ing.pdf", data_of(long_statement()), "")
    agents = {f.agent: f.level for f in r.findings}
    assert r.status == "verified" and agents == {
        "layout reader": "ok",
        "currency": "warn",
        "balance prover": "ok",
        "engine agreement": "warn",
        "second reader": "ok",
    }  # no currency is printed in this sample


def test_two_independent_readings_that_disagree_fail_the_file():
    wrong = {**LAYOUT, "decimal": ".", "thousands": ","}  # the second reading believes numbers are written 1,234.56
    r = verify.read_table_statement(Model(LAYOUT, wrong), "m", "ing.pdf", data_of(long_statement()), "")
    assert r.status == "needs_check" and any(f.agent == "second reader" and f.level == "fail" for f in r.findings)


def test_a_credit_card_statement_without_running_balances_is_proved_by_its_totals():
    rows = [["Datum", "Omschrijving", "Bedrag"], ["02-10-2026", "Albert Heijn", "40,00 Af"], ["05-10-2026", "Betaling ontvangen", "10,00 Bij"]]
    layout = {
        "header_line": 0,
        "roles": ["date", "description", "amount"],
        "date_format": "%d-%m-%Y",
        "month_names": [],
        "decimal": ",",
        "thousands": ".",
        "debit_words": ["af"],
        "credit_words": ["bij"],
        "date_on_every_row": True,
        "opening_balance": "100,00",
        "closing_balance": "130,00",
        "balance_is_amount_owed": True,
    }
    cols = [(0, 60), (70, 200), (210, 260)]
    text = "Vorig saldo 100,00 Nieuw saldo 130,00"
    good = verify.read_table_statement(Model(layout), "m", "card.pdf", data_of(rows, cols), text)
    assert good.status == "verified" and "opening + transactions = closing" in good.proofs  # 100 + 40 purchases - 10 payment = 130
    bad = verify.read_table_statement(
        Model({**layout, "closing_balance": "131,00"}), "m", "card.pdf", data_of(rows, cols), "Vorig saldo 100,00 Nieuw saldo 131,00"
    )
    assert bad.status == "needs_check" and any(f.agent == "totals prover" and f.level == "fail" for f in bad.findings)
    invented = verify.read_table_statement(
        Model(layout), "m", "card.pdf", data_of(rows, cols), "Vorig saldo 100,00"
    )  # the closing balance is not in the document
    assert invented.status == "unverified" and any(f.level == "warn" for f in invented.findings)


def test_a_file_with_no_header_row_is_read_from_the_first_line():
    rows = [["20261001", "Opening", "", "2.000,00"], ["20261002", "Shop", "-23,45", "1.976,55"], ["20261025", "Salaris", "2.850,00", "4.826,55"]]
    layout = {
        "header_line": -1,
        "roles": ["date", "description", "amount", "balance"],
        "date_format": "%Y%m%d",
        "month_names": [],
        "decimal": ",",
        "thousands": ".",
        "debit_words": [],
        "credit_words": [],
        "date_on_every_row": True,
    }
    parsed = tables.parse_table(tables.table_from_data({"rows": rows}), tables.Layout(**layout))  # loaded the way the app loads a plain file
    assert parsed.status == "verified" and [(t.day, t.amount_minor, t.kind) for t in parsed.txns] == [
        ("2026-10-02", 2345, "expense"),
        ("2026-10-25", 285000, "income"),
    ]


def test_an_amount_shifted_into_a_text_column_is_caught():
    rows = [["Datum", "Omschrijving", "Af", "Bij", "Saldo"], ["01-10-2026", "Shop", "10,00", "", "90,00"], ["02-10-2026", "Foo 1.234,56", "5,00", "", "85,00"]]
    cells = table(rows)
    cells[2][1] = tables.Cell(70, 200, "1.234,56")  # a figure that landed under the description heading
    p = tables.parse_table(cells, tables.Layout(**LAYOUT))
    assert any("sits in a column read as text" in i for i in p.issues) and p.status == "needs_check"


def test_a_balance_line_with_no_date_is_used_as_a_proof_point_not_dropped():
    rows = [
        ["Datum", "Omschrijving", "Af", "Bij", "Saldo"],
        ["", "Beginsaldo", "", "", "100,00"],
        ["02-10-2026", "Shop", "10,00", "", "90,00"],
        ["", "Eindsaldo", "", "", "91,00"],
    ]
    assert tables.parse_table(table(rows), tables.Layout(**LAYOUT)).status == "needs_check"  # the closing balance contradicts the transactions
    rows[3][4] = "90,00"
    assert tables.parse_table(table(rows), tables.Layout(**LAYOUT)).status == "verified"


# ---- the bank standards, end to end -----------------------------------------------------------------------------------------
def _ingest(conn, tmp_path, name, text, data=None):
    sha = (name.encode().hex() * 8)[:64]
    documents.store_from_library(
        conn, {"sha256": sha, "name": name, "file_kind": "text", "text": text, "area": "finance", "data": json.dumps(data or {}), "facts": {}}
    )


def test_mt940_and_camt053_are_imported_exactly_without_any_model(conn, tmp_path):
    _ingest(conn, tmp_path, "abn-2026-10.sta", MT940)
    r = money.import_statements(conn)  # no model at all
    assert r["new_transactions"] == 3 and r["needs_check"] == [] and r["problems"] == []
    f = conn.execute("SELECT * FROM statement_files").fetchone()
    assert (f["status"], f["account"], f["period_start"], f["period_end"], f["opening_minor"], f["closing_minor"]) == (
        "verified",
        "NL00ABNA0123456789",
        "2026-10-01",
        "2026-10-26",
        200000,
        372655,
    )
    _ingest(conn, tmp_path, "abn-again.xml", CAMT)  # the same period as camt.053: the same three payments, nothing added twice
    r2 = money.import_statements(conn)
    assert r2["new_transactions"] == 0 and r2["already_had"] == 3


def test_a_standard_statement_that_does_not_add_up_is_not_imported(conn, tmp_path):
    _ingest(conn, tmp_path, "abn-bad.sta", MT940.replace("D1100,00N", "D1100,01N"))
    r = money.import_statements(conn)
    assert r["new_transactions"] == 0 and r["needs_check"][0]["file"] == "abn-bad.sta"
    assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0


# ---- across documents ---------------------------------------------------------------------------------------------------------
def tx(conn, day, amount, kind="expense", note="x", source="s.pdf"):
    conn.execute("INSERT INTO transactions (day, amount_minor, kind, category, note, source) VALUES (?,?,?,?,?,?)", (day, amount, kind, "other", note, source))


def test_payslip_net_pay_must_arrive_in_the_bank_to_the_cent(conn):
    conn.execute("INSERT INTO payslips VALUES ('a','loon-09.pdf','2026-09',450000,318000,0,0,0)")
    conn.execute("INSERT INTO payslips VALUES ('b','loon-10.pdf','2026-10',450000,318000,0,0,0)")
    tx(conn, "2026-09-25", 318000, "income")
    tx(conn, "2026-10-25", 317999, "income")  # one cent off
    found = {f.subject: f.level for f in verify.payslip_vs_bank(conn)}
    assert found == {"loon-09.pdf": "ok", "loon-10.pdf": "warn"}


def test_invoice_totals_must_match_a_payment_and_unrelated_months_are_not_judged(conn):
    conn.execute("INSERT INTO finance_docs (sha256,name,kind,party,doc_date,total_minor) VALUES ('i1','f1.pdf','invoice','Ziggo','2026-10-03',6050)")
    conn.execute("INSERT INTO finance_docs (sha256,name,kind,party,doc_date,total_minor) VALUES ('i2','f2.pdf','invoice','Vattenfall','2026-10-05',11840)")
    conn.execute("INSERT INTO finance_docs (sha256,name,kind,party,doc_date,total_minor) VALUES ('i3','f3.pdf','receipt','Old shop','2024-01-05',999)")
    tx(conn, "2026-10-10", 6050)
    found = {f.subject: f.level for f in verify.documents_vs_bank(conn)}
    assert found == {"f1.pdf": "ok", "f2.pdf": "warn"}  # 2024 has no statements here, so it is not judged


def _file(conn, name, start, end, opening, closing, account="NL1"):
    conn.execute(
        "INSERT INTO statement_files (sha256,name,found,added,status,account,period_start,period_end,opening_minor,closing_minor) VALUES (?,?,0,0,'verified',?,?,?,?,?)",
        (name, name, account, start, end, opening, closing),
    )


def test_each_statement_must_start_where_the_last_one_ended_with_no_month_missing(conn):
    _file(conn, "oct", "2026-10-01", "2026-10-31", 1000, 2000)
    _file(conn, "nov", "2026-11-01", "2026-11-30", 2000, 3000)  # joins up
    _file(conn, "jan", "2027-01-01", "2027-01-31", 3000, 4000)  # December is missing
    _file(conn, "feb", "2027-02-01", "2027-02-28", 4001, 5000)  # does not join up
    levels = [(f.level, f.message) for f in verify.continuity(conn)]
    assert [lv for lv, _ in levels] == ["ok", "warn", "fail"] and "no statement between 2026-11-30 and 2027-01-01" in levels[1][1]


def test_payments_dated_in_the_future_or_outside_their_statement_fail(conn):
    _file(conn, "s.pdf", "2026-10-01", "2026-10-31", 0, 0)
    tx(conn, "2026-09-30", 100, source="s.pdf")
    tx(conn, (date.today() + timedelta(days=5)).isoformat(), 100)
    msgs = {f.subject: f.level for f in verify.plausibility(conn)}
    assert msgs["payments"] == "fail" and msgs["s.pdf"] == "fail"


def test_the_report_counts_what_every_agent_concluded(conn):
    conn.execute("INSERT INTO payslips VALUES ('a','loon.pdf','2026-10',450000,318000,0,0,0)")
    tx(conn, "2026-10-02", 100)
    verify.run_cross_checks(conn)
    report = money.verification_report(conn)
    assert report["summary"]["payslip ↔ bank"]["warn"] == 1 and any(p["level"] == "warn" for p in report["problems"]) and report["passed"] >= 1
