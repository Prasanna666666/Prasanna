"""Everything must tally: currencies apart, transfers matched, statements vs stored payments, reports vs the raw ledger."""

import json

from orbit import currency, db, verify
from orbit.modules import documents, events, money
from tests.test_standards import MT940


def tx(conn, day, amount, kind="expense", account="", cur="", cat="other", note="x", event=None):
    return conn.execute("INSERT INTO transactions (day, amount_minor, kind, category, note, source, account, currency, event_id) VALUES (?,?,?,?,?,?,?,?,?)",
                        (day, amount, kind, cat, note, "s.pdf", account, cur, event)).lastrowid


# ---- currencies ------------------------------------------------------------------------------------------------------------
def test_currency_is_read_from_what_the_statement_prints_and_never_guessed():
    assert currency.detect("Saldo EUR 1.234,56  Af EUR 12,00") == "EUR" and currency.detect("Balance ₹ 1,200.00 Rs. 300") == "INR"
    assert currency.detect("Account statement, no money words here") == ""
    assert currency.detect("EUR 10 EUR 20 EUR 30 INR 5 INR 6 INR 7") == ""  # two currencies clearly present: do not guess


def test_reports_show_one_currency_at_a_time_and_never_add_euros_to_rupees(conn):
    tx(conn, "2026-10-02", 5000, cur="EUR", cat="groceries")
    tx(conn, "2026-10-03", 700000, cur="INR", cat="groceries")
    assert money.summary(conn, {"month": "2026-10"})["spent"] == 50.0  # the main currency
    db.set_setting(conn, "view_currency", "INR")
    db.ledger_view(conn)
    assert money.summary(conn, {"month": "2026-10"})["spent"] == 7000.0
    assert [r["category"] for r in events.daily_by_category(conn, {"month": "2026-10"})] == ["groceries"]
    assert db.view_currency(conn) == "INR"


def test_a_payment_with_no_recorded_currency_counts_as_the_main_currency(conn):
    tx(conn, "2026-10-02", 5000)
    assert money.summary(conn, {"month": "2026-10"})["spent"] == 50.0


def test_an_mt940_statement_stores_its_currency_and_account(conn, tmp_path):
    sha = "ab" * 32
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / f"{sha}.json").write_text(json.dumps({"schema": 1, "sha256": sha, "name": "abn.sta", "kind": "text", "text": MT940, "meta": {}, "area": "finance", "data": {}}))
    documents.ingest_dir(conn, tmp_path / "p")
    money.import_statements(conn)
    assert {r[0] for r in conn.execute("SELECT currency FROM transactions")} == {"EUR"}
    assert {r[0] for r in conn.execute("SELECT account FROM transactions")} == {"NL00ABNA0123456789"}


# ---- transfers between your own accounts -------------------------------------------------------------------------------------
def test_a_transfer_between_two_of_your_accounts_is_matched_and_leaves_spending_and_income(conn):
    tx(conn, "2026-10-05", 50000, "expense", account="NLABN")
    tx(conn, "2026-10-06", 50000, "income", account="NLWISE")
    tx(conn, "2026-10-07", 1234, "expense", account="NLABN", cat="groceries")
    found = verify.link_transfers(conn)
    assert any(f.level == "ok" and "1 transfer" in f.message for f in found)
    assert money.summary(conn, {"month": "2026-10"})["spent"] == 12.34 and money.summary(conn, {"month": "2026-10"})["income"] == 0


def test_an_ambiguous_or_lonely_transfer_is_never_guessed(conn):
    tx(conn, "2026-10-05", 20000, "expense", account="NLABN")
    tx(conn, "2026-10-05", 20000, "income", account="NLWISE")
    tx(conn, "2026-10-06", 20000, "income", account="NLSAVE")  # two possible partners
    found = verify.link_transfers(conn)
    assert any(f.level == "warn" and "more than one candidate" in f.message for f in found)
    assert conn.execute("SELECT COUNT(*) FROM transactions WHERE transfer_id IS NOT NULL").fetchone()[0] == 0
    tx(conn, "2026-10-09", 999, "expense", account="NLABN", cat="transfers")  # looks like a transfer, nothing arrives anywhere
    assert any("no matching payment" in f.message for f in verify.link_transfers(conn))


# ---- statements vs the payments stored for them ---------------------------------------------------------------------------
def _statement(conn, name, start, end, opening, closing, account="NLABN"):
    conn.execute("INSERT INTO statement_files (sha256,name,found,added,status,account,period_start,period_end,opening_minor,closing_minor) VALUES (?,?,0,0,'verified',?,?,?,?,?)",
                 (name, name, account, start, end, opening, closing))


def test_the_stored_payments_must_add_up_to_what_the_statements_say_and_a_lost_payment_is_caught(conn):
    _statement(conn, "oct", "2026-10-01", "2026-10-31", 100000, 130000)
    tx(conn, "2026-10-05", 20000, "expense", account="NLABN")
    tx(conn, "2026-10-25", 50000, "income", account="NLABN")
    assert verify.account_ledger(conn)[0].level == "ok"
    conn.execute("DELETE FROM transactions WHERE amount_minor=20000")  # a payment is lost somewhere between the statement and the ledger
    bad = verify.account_ledger(conn)[0]
    assert bad.level == "fail" and "difference" in bad.message


def test_two_overlapping_statements_do_not_count_a_payment_twice(conn):
    _statement(conn, "a", "2026-10-01", "2026-10-20", 100000, 120000)
    _statement(conn, "b", "2026-10-15", "2026-10-31", 110000, 130000)  # overlaps; its own opening differs, so they are separate runs
    tx(conn, "2026-10-17", 20000, "income", account="NLABN")  # stored once, as dedupe guarantees
    tx(conn, "2026-10-28", 20000, "income", account="NLABN")
    levels = {f.subject: f.level for f in verify.account_ledger(conn)}
    assert levels["NLABN 2026-10-01 to 2026-10-20"] == "ok" and levels["NLABN 2026-10-15 to 2026-10-31"] == "fail"  # b should see 40000 more but only sees 40000 - 10000


# ---- the reports against the raw ledger -----------------------------------------------------------------------------------
def test_the_reports_tally_with_the_raw_ledger_every_month(conn):
    tx(conn, "2026-10-02", 5000, cat="groceries")
    tx(conn, "2026-10-03", 300000, "income", cat="salary")
    ev = events.assign(conn, {"event": "Max Amini", "main": "events", "sub": "tickets", "transaction_ids": [tx(conn, "2026-10-04", 6348)]})
    events.assign(conn, {"event": ev["id"], "transaction_ids": [tx(conn, "2026-10-20", 1000, "income")]})
    tx(conn, "2026-11-01", 7000, cat="transfers", account="NLABN")
    found = verify.tally(conn)
    assert [f.level for f in found] == ["ok"] and "2 month(s)" in found[0].message


def test_a_report_that_drops_a_payment_makes_the_tally_fail(conn):
    tx(conn, "2026-10-02", 5000, cat="groceries")
    conn.commit()
    conn.execute("PRAGMA foreign_keys=OFF")  # only effective outside a transaction
    tx(conn, "2026-10-03", 7777, event=424242)  # a payment pointing at an event that does not exist: the reports would silently lose it
    found = verify.tally(conn)
    assert found and found[0].level == "fail" and "2026-10" in found[0].subject


def test_tally_checks_each_currency_on_its_own_and_restores_the_view(conn):
    tx(conn, "2026-10-02", 5000, cur="EUR")
    tx(conn, "2026-10-02", 900000, cur="INR")
    found = verify.tally(conn)
    assert {f.subject for f in found} == {"EUR", "INR"} and all(f.level == "ok" for f in found)
    assert db.view_currency(conn) == "EUR"  # the setting is back where it was
    assert any("EUR, INR" in f.message for f in verify.currency_mix(conn))
