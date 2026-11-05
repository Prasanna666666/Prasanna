"""Everything in euros at the rate of its own day. The rates here are INVENTED, in the layout of the ECB's eurofxref CSV."""

from decimal import Decimal

from orbit import db, parser, rates, verify
from orbit.modules import documents, money

ECB = [["Date", "USD", "JPY", "INR", ""],
       ["2026-10-09", "1.0900", "160.00", "90.0000", ""],   # a Friday
       ["2026-10-08", "1.0800", "N/A", "89.5000", ""],
       ["2026-10-02", "1.0700", "159.00", "89.0000", ""]]


def tx(conn, day, amount, kind="expense", cur="", account="", cat="other", note="x"):
    return conn.execute("INSERT INTO transactions (day, amount_minor, kind, category, note, source, currency, account) VALUES (?,?,?,?,?,?,?,?)",
                        (day, amount, kind, cat, note, "s.pdf", cur, account)).lastrowid


def test_the_ecb_file_is_recognised_and_its_rates_stored_exactly(conn):
    assert rates.looks_like_ecb(ECB) and not rates.looks_like_ecb([["Datum", "Bedrag"]])
    found = rates.parse_ecb(ECB)
    assert ("2026-10-09", "INR", "90.0000") in found and not any(c == "JPY" and d == "2026-10-08" for d, c, _ in found)  # N/A is skipped
    assert rates.store(conn, found) == len(found)


def test_a_weekend_uses_the_last_published_rate_and_a_stale_one_is_refused(conn):
    rates.store(conn, rates.parse_ecb(ECB))
    assert rates.rate_on(conn, "INR", "2026-10-10") == (Decimal("90.0000"), "2026-10-09")  # Saturday: Friday's rate
    assert rates.rate_on(conn, "INR", "2026-10-09")[1] == "2026-10-09"
    assert rates.rate_on(conn, "INR", "2026-10-30") is None  # more than a week after the last rate: never guessed
    assert rates.rate_on(conn, "SEK", "2026-10-09") is None


def test_conversion_is_exact_decimal_arithmetic_rounded_half_even():
    assert rates.to_eur(900000, Decimal("90.5")) == 9945   # 9000.00 / 90.5 = 99.4475...
    assert rates.to_eur(100, Decimal(2)) == 50 and rates.to_eur(1, Decimal(2)) == 0 and rates.to_eur(3, Decimal(2)) == 2  # half-even on .5


def test_every_payment_is_converted_at_its_own_days_rate_and_a_missing_rate_is_left_out_and_reported(conn):
    tx(conn, "2026-10-09", 4500)                                   # a euro payment
    tx(conn, "2026-10-09", 900000, cur="INR", cat="groceries")   # 9000.00 INR at 90.0000
    tx(conn, "2026-10-02", 890000, cur="INR", cat="groceries")   # 8900.00 INR at 89.0000
    tx(conn, "2026-10-20", 500000, cur="INR", cat="groceries")   # no rate that week
    rates.store(conn, rates.parse_ecb(ECB))
    assert rates.convert_all(conn) == {"euro": 1, "converted": 2, "missing": 1}
    got = {r["day"]: (r["eur_minor"], r["rate"], r["rate_source"]) for r in conn.execute("SELECT day, eur_minor, rate, rate_source FROM transactions WHERE currency='INR'")}
    assert got["2026-10-09"] == (10000, "90.0000", "ecb 2026-10-09") and got["2026-10-02"] == (10000, "89.0000", "ecb 2026-10-02") and got["2026-10-20"][0] is None
    assert money.summary(conn, {"month": "2026-10"})["spent"] == 45  # the default shows each currency as it is: the euro payments only
    db.set_setting(conn, "view_currency", "ALL")  # the option: everything converted to euros. The unconverted payment is not in it, the converted ones are
    db.ledger_view(conn)
    assert money.summary(conn, {"month": "2026-10"})["spent"] == 45 + 100 + 100
    msgs = {f.level: f.message for f in verify.conversion(conn)}
    assert "2 payment(s) in INR converted" in msgs["ok"] and "1 payment(s) in INR have no exchange rate" in msgs["warn"]


def test_an_ecb_file_in_the_finance_folder_is_loaded_through_the_parser_and_the_import(conn, tmp_path):
    fin, out = tmp_path / "fin", tmp_path / "out"
    fin.mkdir()
    (fin / "ecb-eurofxref-hist.csv").write_text("\n".join(",".join(r) for r in ECB) + "\n")
    tx(conn, "2026-10-09", 900000, cur="INR")
    parser.process_inbox(fin, out, isolated=False, area="finance")
    documents.ingest_dir(conn, out)
    r = money.import_statements(conn)
    assert r["problems"] == [] and r["needs_check"] == [] and r["new_transactions"] == 0
    assert conn.execute("SELECT eur_minor FROM transactions WHERE currency='INR'").fetchone()[0] == 10000  # converted by the import itself
    assert any(f["message"].endswith("exchange rates loaded") for f in conn.execute("SELECT message FROM findings"))


def test_a_transfer_from_a_rupee_account_to_a_euro_account_is_matched_and_its_cost_becomes_an_expense(conn):
    rates.store(conn, rates.parse_ecb(ECB))
    tx(conn, "2026-10-09", 900000, cur="INR", account="ICICI1", note="NEFT to own account")   # 9000.00 INR = 100.00 EUR at 90.0000
    tx(conn, "2026-10-10", 9780, "income", cur="EUR", account="NLWISE", note="Wise")           # 97.80 EUR arrived: a fee and spread of 2.20
    rates.convert_all(conn)
    found = verify.link_transfers(conn)
    assert any(f.level == "ok" and "1 transfer(s) between currencies matched" in f.message and "2.20 EUR" in f.message for f in found)
    db.set_setting(conn, "view_currency", "ALL")
    db.ledger_view(conn)
    assert money.summary(conn, {"month": "2026-10"})["spent"] == 2.20 and money.summary(conn, {"month": "2026-10"})["income"] == 0  # the two halves cancel; the cost is the only spending
    cost = conn.execute("SELECT category, eur_minor, rate_source FROM transactions WHERE source='derived'").fetchone()
    assert tuple(cost) == ("fees", 220, "transfer")
    realized = conn.execute("SELECT rate FROM transactions WHERE currency='INR'").fetchone()[0]
    assert realized == f"{900000 / 9780:.4f}"  # the rate the money really moved at
    verify.link_transfers(conn)  # running again changes nothing
    assert conn.execute("SELECT COUNT(*) FROM transactions WHERE source='derived'").fetchone()[0] == 1


def test_currencies_too_far_apart_are_not_a_transfer(conn):
    rates.store(conn, rates.parse_ecb(ECB))
    tx(conn, "2026-10-09", 900000, cur="INR", account="ICICI1")     # worth 100.00 EUR
    tx(conn, "2026-10-09", 5000, "income", cur="EUR", account="NLWISE")  # 50.00 EUR: not the same money
    rates.convert_all(conn)
    verify.link_transfers(conn)
    assert conn.execute("SELECT COUNT(*) FROM transactions WHERE transfer_id IS NOT NULL").fetchone()[0] == 0


def test_the_tally_still_holds_in_euros_with_conversions_and_a_derived_cost(conn):
    rates.store(conn, rates.parse_ecb(ECB))
    tx(conn, "2026-10-09", 900000, cur="INR", account="ICICI1")
    tx(conn, "2026-10-10", 9780, "income", cur="EUR", account="NLWISE")
    tx(conn, "2026-10-09", 1000, cur="EUR", cat="groceries")
    tx(conn, "2026-10-09", 180000, cur="INR", cat="groceries")
    rates.convert_all(conn)
    verify.link_transfers(conn)
    assert all(f.level == "ok" for f in verify.tally(conn)) and db.view_currency(conn) == "EUR"  # the default view is the main currency, as it is


def test_viewing_one_currency_shows_its_own_amounts_not_euros(conn):
    rates.store(conn, rates.parse_ecb(ECB))
    tx(conn, "2026-10-09", 900000, cur="INR", cat="groceries")
    rates.convert_all(conn)
    db.set_setting(conn, "view_currency", "INR")
    db.ledger_view(conn)
    assert money.summary(conn, {"month": "2026-10"})["spent"] == 9000.0 and db.display_currency(conn) == "INR"


def test_the_agent_register_is_consistent():
    names = [a["name"] for a in verify.AGENTS]
    assert len(names) == len(set(names)) and {a["status"] for a in verify.AGENTS} == {"built", "planned"}
    assert all(a["group"] and a["does"] for a in verify.AGENTS)


def test_a_converted_payment_still_shows_its_original_amount_and_currency(conn):
    rates.store(conn, rates.parse_ecb(ECB))
    tx(conn, "2026-10-09", 900000, cur="INR", cat="groceries", note="Big Bazaar")
    rates.convert_all(conn)
    db.set_setting(conn, "view_currency", "ALL")
    db.ledger_view(conn)
    row = money.list_transactions(conn, {"since": "2026-10-01", "until": "2026-10-31"})[0]
    assert (row["amount"], row["original"], row["currency"]) == (100.0, 9000.0, "INR")  # euros for the totals, the original beside it
    db.set_setting(conn, "view_currency", "INR")
    db.ledger_view(conn)
    row = money.list_transactions(conn, {"since": "2026-10-01", "until": "2026-10-31"})[0]
    assert (row["amount"], row["original"]) == (9000.0, 9000.0)
