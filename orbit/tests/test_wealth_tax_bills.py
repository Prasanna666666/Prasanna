from datetime import date

import pytest

from orbit import clock, planning, wealth
from orbit.modules import money
from tests.test_tally import tx


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: date(2026, 11, 20))


def statement(conn, account, end, closing, opening=0, status="verified"):
    conn.execute(
        "INSERT INTO statement_files (sha256,name,found,added,status,account,period_start,period_end,opening_minor,closing_minor) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (account + end, account + end, 1, 1, status, account, end[:8] + "01", end, opening, closing),
    )


def test_net_worth_adds_proven_accounts_and_typed_items_and_keeps_them_apart(conn):
    statement(conn, "NL00TEST0001", "2026-10-31", 1000000)  # 10,000 on the account
    wealth.add_holding(conn, {"name": "ETF", "kind": "investment", "units": 50, "price": 80.5})  # 4,025
    wealth.add_holding(conn, {"name": "Car", "kind": "asset", "value": 8000})
    wealth.add_holding(conn, {"name": "Car loan", "kind": "debt", "value": 3000})
    s = wealth.wealth_summary(conn)
    assert s["accounts"] == 10000.0 and s["investments"] == 4025.0 and s["assets"] == 8000.0 and s["debts"] == 3000.0
    assert s["net_worth"] == 10000 + 4025 + 8000 - 3000 and "typed in" in s["note"]
    assert all(h["entered_by_you"] for h in wealth.list_holdings(conn))


def test_a_holding_can_be_repriced_and_removed_and_bad_input_is_refused(conn):
    h = wealth.add_holding(conn, {"name": "ETF", "kind": "investment", "units": 10, "price": 100})
    assert wealth.update_holding(conn, {"id": h["id"], "price": 110})["value"] == 1100.0  # units stay, the price moved
    assert wealth.update_holding(conn, {"id": h["id"], "value": 900})["value"] == 900.0
    wealth.delete_holding(conn, {"id": h["id"]})
    assert wealth.list_holdings(conn) == []
    for bad in (
        {"name": "x", "kind": "pet", "value": 1},
        {"name": "", "kind": "asset", "value": 1},
        {"name": "x", "kind": "asset"},
        {"name": "x", "kind": "debt", "value": -5},
    ):
        with pytest.raises(ValueError):
            wealth.add_holding(conn, bad)


def test_a_holding_in_another_currency_needs_a_rate_and_is_never_guessed(conn):
    wealth.add_holding(conn, {"name": "US shares", "kind": "investment", "value": 1000, "currency": "USD", "as_of": "2026-11-01"})
    s = wealth.wealth_summary(conn)
    assert s["investments"] == 0 and s["not_converted"] == 1  # no rate loaded: left out and said so


def test_accounts_overview_says_whether_every_statement_of_an_account_is_proven(conn):
    statement(conn, "NL00TEST0001", "2026-09-30", 900000)
    statement(conn, "NL00TEST0001", "2026-10-31", 1000000, status="needs_check")
    a = wealth.accounts_overview(conn)
    assert a[0]["label"] == "…0001" and a[0]["statements"] == 2 and a[0]["proven"] is False


def test_budgets_show_what_is_left_and_what_is_over(conn):
    tx(conn, "2026-10-04", 30000, cat="groceries", note="AH")
    tx(conn, "2026-10-18", 25000, cat="groceries", note="AH")
    tx(conn, "2026-10-20", 5000, cat="fun", note="Cinema")
    money.set_budget(conn, {"category": "groceries", "monthly_amount": 500})
    money.set_budget(conn, {"category": "fun", "monthly_amount": 100})
    b = {x["category"]: x for x in planning.budget_progress(conn, {"month": "2026-10"})["budgets"]}
    assert b["groceries"]["spent"] == 550.0 and b["groceries"]["left"] == -50.0 and b["groceries"]["over"] is True and b["groceries"]["percent"] == 110
    assert b["fun"]["left"] == 50.0 and b["fun"]["over"] is False


def test_an_unpaid_invoice_is_a_bill_and_a_paid_one_is_not(conn):
    conn.execute(
        "INSERT INTO finance_docs (sha256,name,kind,party,doc_date,due_date,total_minor) VALUES ('a','a.pdf','invoice','Ziggo','2026-11-05','2026-11-25',6250)"
    )
    conn.execute(
        "INSERT INTO finance_docs (sha256,name,kind,party,doc_date,due_date,total_minor) VALUES ('b','b.pdf','invoice','Vattenfall','2026-11-01','2026-11-22',11840)"
    )
    tx(conn, "2026-11-10", 11840, note="Vattenfall")  # this one is paid
    items = planning.bills_due(conn)["items"]
    assert [(i["what"], i["amount"], i["in_days"]) for i in items if i["kind"] == "invoice"] == [("Ziggo", 62.5, 5)]


def test_the_tax_summary_collects_the_facts_for_one_year(conn):
    conn.execute(
        "INSERT INTO finance_docs (sha256,name,kind,gross_minor,tax_minor,net_minor,period,doc_date) VALUES ('j','jaar','annual_statement',5000000,1200000,3800000,'2026','2027-01-20')"
    )
    for m in (1, 2):
        conn.execute(
            "INSERT INTO payslips (sha256,name,period,gross_minor,net_minor,tax_minor,pension_minor) VALUES (?,?,?,?,?,?,?)",
            (f"p{m}", "p", f"2026-0{m}", 400000, 300000, 90000, 20000),
        )
    conn.execute("INSERT INTO finance_docs (sha256,name,kind,party,doc_date,total_minor) VALUES ('t','aanslag','tax','Belastingdienst','2026-07-01',41200)")
    tx(conn, "2026-03-31", 1500, kind="income", cat="interest", account="NL1", note="Interest")
    tx(conn, "2026-03-02", 20000, cat="investments", account="NL1", note="Degiro")
    tx(conn, "2026-03-12", 12000, cat="insurance", account="NL1", note="Zilveren Kruis")
    statement(conn, "NL00TEST0001", "2025-12-31", 777700)
    t = planning.tax_summary(conn, {"year": "2026"})
    assert t["annual_statement"] == {"gross": 50000.0, "tax_withheld": 12000.0, "net": 38000.0}
    assert t["payslips"] == {"count": 2, "gross": 8000.0, "tax_withheld": 1800.0, "net": 6000.0, "pension": 400.0}
    assert t["interest_received"] == 15.0 and t["paid_into_investments"] == 200.0 and t["insurance_paid"] == 120.0
    assert t["balances_on_1_january"] == [{"account": "0001", "balance": 7777.0, "as_of": "2025-12-31"}] and t["tax_letters"][0]["amount"] == 412.0
    assert "Not tax advice" in t["note"]


def test_a_merchant_over_time_and_payment_search(conn):
    for m, amt in ((8, 4000), (9, 5000), (10, 6000)):
        tx(conn, f"2026-{m:02d}-05", amt, note="Albert Heijn Utrecht", cat="groceries")
    tx(conn, "2026-10-06", 99900, note="Bol.com laptop", cat="shopping")
    h = planning.merchant_history(conn, {"merchant": "albert heijn"})
    assert h["payments"] == 3 and h["total"] == 150.0 and [m["spent"] for m in h["per_month"]] == [40.0, 50.0, 60.0]
    found = money.list_transactions(conn, {"query": "laptop"})
    assert [r["note"] for r in found] == ["Bol.com laptop"]
    big = money.list_transactions(conn, {"min_amount": 500})
    assert len(big) == 1 and big[0]["amount"] == 999.0
    assert money.list_transactions(conn, {"query": "100%"}) == []  # a % in the words is just text, not a wildcard
    with pytest.raises(ValueError):
        planning.merchant_history(conn, {"merchant": " "})


def test_the_year_report_is_one_printable_page_with_the_year_and_a_warning_for_unproven_months(conn):
    from orbit import report

    tx(conn, "2026-03-25", 300000, kind="income", cat="salary", account="NL1", note="Acme <b>salary</b>")
    tx(conn, "2026-03-01", 100000, cat="rent", account="NL1", note="Huur")
    html = report.year_report(conn, "2026")
    assert "<h1>Finance · 2026</h1>" in html and "Tax checklist" in html and "Month by month" in html and "not tax or financial advice" in html
    assert "not fully proven" in html and "2026-03" in html  # no statement backs this invented data
    assert "<script" not in html and "http" not in html.replace("https://", "")  # nothing is loaded from anywhere


def test_the_report_page_is_served_only_to_the_logged_in_and_only_for_a_year(tmp_path, monkeypatch):
    import http.client
    import threading
    from http.server import ThreadingHTTPServer

    from orbit import db, web
    from orbit.modules import ALL

    monkeypatch.setenv("ORBIT_HOME", str(tmp_path))
    monkeypatch.delenv("ORBIT_DB_KEY", raising=False)
    c = db.connect()
    db.migrate(c, ALL)
    c.close()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(web.State(token="pw-123456")))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]

    def get(path, cookie=None):
        conn = http.client.HTTPConnection("127.0.0.1", port)
        conn.request("GET", path, headers={"Host": f"127.0.0.1:{port}", **({"Cookie": cookie} if cookie else {})})
        r = conn.getresponse()
        return r.status, r.read()

    try:
        assert get("/report/2026")[0] == 401  # not without the password
        session = web.State(token="pw-123456").session
        assert get("/report/2026", f"orbit_k={session}")[0] == 200
        assert get("/report/abc", f"orbit_k={session}")[0] == 404 and get("/report/20266", f"orbit_k={session}")[0] == 404
    finally:
        srv.shutdown()
