from datetime import date

from orbit import audit, insight
from orbit.modules import money
from tests.test_tally import tx


def names(found):
    return {(f.agent, f.level) for f in found}


def test_two_spellings_of_one_shop_become_one(conn):
    for i in range(3):
        tx(conn, f"2026-0{i + 1}-05", 1000, note="Albert Heijn Utrecht 1234")
    tx(conn, "2026-04-05", 1000, note="Albert Heijn")
    insight.merchant_aliases(conn)
    assert len({insight._name(insight._aliases(conn), n) for n in ("Albert Heijn Utrecht 1234", "Albert Heijn")}) == 1


def test_a_payment_taken_twice_is_flagged_but_a_transfer_is_not(conn):
    tx(conn, "2026-03-01", 4999, note="Zalando", account="A")
    tx(conn, "2026-03-02", 4999, note="Zalando", account="A")
    tx(conn, "2026-03-01", 7000, note="Zalando", account="B")
    found = insight.duplicate_payments(conn)
    assert len(found) == 1 and "zalando" in found[0].message


def test_a_changed_subscription_price_is_flagged(conn):
    for m, amt in enumerate((1299, 1299, 1299, 1599), 1):
        tx(conn, f"2026-0{m}-10", amt, note="Netflix")
    found = insight.price_changes(conn)
    assert any(f.level == "warn" and "netflix" in f.message for f in found)


def test_upcoming_payments_predict_the_next_date(conn):
    for m in (1, 2, 3):
        tx(conn, f"2026-0{m}-10", 80000, note="Rent")
    out = insight.upcoming_payments(conn, {"today": "2026-04-01"})
    assert out and out[0]["merchant"] and out[0]["amount"] == 800.0 and out[0]["due"] >= "2026-04-05"


def test_an_unusually_large_payment_is_flagged(conn):
    for i in range(8):
        tx(conn, f"2026-0{i + 1}-0{i + 1}", 2000 + i * 10, note="Jumbo")
    tx(conn, "2026-09-15", 20000, note="Jumbo")
    assert insight.unusual_payments(conn, today=date(2026, 9, 20))


def test_a_refund_is_tied_to_its_purchase(conn):
    p = tx(conn, "2026-05-01", 5000, note="Bol.com", account="A")
    r = tx(conn, "2026-05-20", 5000, kind="income", cat="refund", note="Bol.com", account="A")
    insight.refund_matcher(conn)
    assert conn.execute("SELECT refund_of FROM transactions WHERE id=?", (r,)).fetchone()[0] == p


def test_year_end_must_match_the_payslips(conn):
    conn.execute(
        "INSERT INTO finance_docs (sha256,name,kind,gross_minor,tax_minor,net_minor,period) VALUES ('a','jaar','annual_statement',200000,50000,150000,'2026')"
    )
    for m in (1, 2):
        conn.execute(
            "INSERT INTO payslips (sha256,name,period,gross_minor,net_minor,tax_minor) VALUES (?,?,?,?,?,?)", (f"s{m}", "p", f"2026-0{m}", 100000, 75000, 25000)
        )
    assert insight.year_end(conn)[0].level == "ok"
    conn.execute("UPDATE finance_docs SET net_minor=151000")
    assert insight.year_end(conn)[0].level == "fail"


def test_tax_letter_needs_a_matching_payment(conn):
    conn.execute("INSERT INTO finance_docs (sha256,name,kind,party,doc_date,total_minor) VALUES ('t','aanslag','tax','Belastingdienst','2026-03-01',123400)")
    tx(conn, "2026-03-20", 5000, note="x")
    assert insight.tax_letters(conn)[0].level == "warn"
    tx(conn, "2026-04-01", 123400, note="Belastingdienst")
    assert insight.tax_letters(conn)[0].level == "ok"


def test_vat_larger_than_total_fails(conn):
    conn.execute("INSERT INTO finance_docs (sha256,name,kind,doc_date,total_minor,vat_minor) VALUES ('i','inv','invoice','2026-01-01',1000,2000)")
    assert any(f.level == "fail" for f in insight.vat_agent(conn))


def test_missing_rates_and_a_broken_audit_chain_are_reported(conn):
    tx(conn, "2026-01-01", 1000, cur="USD")
    assert insight.rate_freshness(conn)[0].level == "warn"
    audit.record(conn, "x", "y")
    audit.record(conn, "x", "z")
    assert insight.audit_chain(conn)[0].level == "ok"
    conn.execute("UPDATE audit_log SET detail='changed' WHERE id=1")
    assert insight.audit_chain(conn)[0].level == "fail"


def test_net_worth_from_proven_closing_balances(conn):
    conn.execute(
        "INSERT INTO statement_files (sha256,name,found,added,status,account,period_end,closing_minor,currency) VALUES ('f','a',1,1,'verified','NL1','2026-02-28',150000,'EUR')"
    )
    nw = money.tools if False else insight.net_worth(conn)
    assert nw["latest"] == 1500.0


def test_every_extra_agent_runs_on_an_empty_database(conn):
    for agent in insight.EXTRA_AGENTS:
        if agent is not insight.backup_status:
            agent(conn)
