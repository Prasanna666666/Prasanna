from datetime import date

import pytest

from finance import clock, planning
from finance.modules import events
from tests.test_tally import tx


@pytest.fixture
def year(conn, monkeypatch):
    """2026, month by month: salary 3000 (3300 from July), rent 1000, shop 300, insurance 120, ETF 200, savings interest 10 from June."""
    monkeypatch.setattr(clock, "today", lambda: date(2026, 12, 15))
    for m in range(1, 13):
        tx(conn, f"2026-{m:02d}-25", 300000 if m < 7 else 330000, kind="income", cat="salary", account="NL1", note="Acme salary")
        tx(conn, f"2026-{m:02d}-01", 100000, cat="rent", account="NL1", note="Huur")
        tx(conn, f"2026-{m:02d}-10", 30000, cat="groceries", account="NL1", note="Albert Heijn")
        tx(conn, f"2026-{m:02d}-12", 12000, cat="insurance", account="NL1", note="Zilveren Kruis")
        tx(conn, f"2026-{m:02d}-15", 20000, cat="investments", account="NL1", note="Degiro")
        if m >= 6:
            tx(conn, f"2026-{m:02d}-28", 1000, kind="income", cat="interest", account="NL2", note="Interest")
    return conn


def test_a_year_adds_up_and_the_savings_rate_is_exact(year):
    y = planning.yearly_overview(year)["years"][0]
    assert y["year"] == "2026" and y["months"] == 12
    assert y["salary"] == 3000 * 6 + 3300 * 6 and y["interest"] == 70.0
    assert y["income"] == 37800.0 + 70.0 and y["spent"] == 12 * (1000 + 300 + 120)  # the ETF money is saved, not spent
    assert y["saved"] == y["income"] - y["spent"] and y["savings_rate"] == round(y["saved"] / y["income"] * 100, 1)
    assert y["invested"] == 2400.0 and y["insurance"] == 1440.0 and y["kept_in_accounts"] == y["saved"] - 2400.0


def test_interest_rate_is_an_estimate_from_balances_and_says_so(year):
    for end, closing in (("2026-06-30", 1000000), ("2026-12-31", 1200000)):
        year.execute(
            "INSERT INTO statement_files (sha256,name,found,added,status,account,period_start,period_end,closing_minor) VALUES (?,?,?,?,?,?,?,?,?)",
            (end, end, 1, 1, "verified", "NL2", end[:8] + "01", end, closing),
        )
    r = planning.interest(year)["by_year"][0]
    # the whole year's interest is 70, but only June and December are covered by statements: 10 + 10 earned in 61 days on an average 11,000
    assert r["interest"] == 70.0 and r["average_balance"] == 11000.0 and r["rate_percent"] == round(20 / 11000 * 365 / 61 * 100, 2) and "estimate" in r["note"]


def test_investments_show_contributions_and_never_invent_a_value(year):
    r = planning.investments(year)
    assert r["contributed_by_year"] == [{"year": "2026", "contributed": 2400.0, "payments": 12}]
    assert r["portfolio_value"] is None and "broker" in r["note"]


def test_insurance_paid_per_year_per_insurer(year):
    r = planning.insurances(year)
    assert r["total_per_year"] == [{"year": "2026", "paid": 1440.0}] and r["paid"][0]["paid"] == 1440.0


def test_a_goal_knows_how_far_you_are_and_whether_the_pace_gets_you_there(year):
    year.execute(
        "INSERT INTO statement_files (sha256,name,found,added,status,account,period_start,period_end,opening_minor,closing_minor) VALUES ('s','s',1,1,'verified','NL1','2026-12-01','2026-12-31',0,500000)"
    )
    year.commit()
    planning.add_goal(year, {"name": "Holiday", "target": 10000, "by": "2027-06-30"})
    g = planning.list_goals(year)["goals"][0]
    assert g["have"] == 5000.0 and g["percent"] == 50.0 and g["months_left"] == 6
    assert g["needed_per_month"] == round(5000 / 6, 2) and g["pace_per_month"] == 3300 + 10 - 1620 and g["on_track"] is True
    planning.add_goal(year, {"name": "House", "target": 500000, "by": "2027-01-31"})
    assert next(x for x in planning.list_goals(year)["goals"] if x["name"] == "House")["on_track"] is False
    with pytest.raises(ValueError):
        planning.add_goal(year, {"name": "", "target": 5})


def test_the_forecast_is_a_labelled_estimate_from_recent_months_and_needs_three(year, conn):
    f = planning.forecast(year, {"months": 3})
    assert f["estimate"] is True and [m["month"] for m in f["months"]] == ["2027-01", "2027-02", "2027-03"]
    assert f["months"][0]["income"] == 3310.0 and f["months"][0]["spent"] == 1620.0 and "estimate" in f["note"].lower()


def test_a_forecast_with_too_little_data_says_so(conn):
    tx(conn, "2026-10-01", 1000)
    assert planning.forecast(conn)["months"] == []


def test_the_timeline_shows_the_salary_rise_trips_and_regular_payments(year):
    events.assign(year, {"event": "Lisbon", "main": "trips", "sub": "flights", "transaction_ids": [tx(year, "2026-04-18", 25000, note="TAP flights")]})
    what = " | ".join(i["what"] for i in planning.timeline(year)["items"])
    assert "Lisbon" in what and "Largest payment of 2026" in what
    assert "started" not in what  # every regular payment is there from the first month of data: when it began is not known
    tx(year, "2026-03-03", 999, note="Gym membership")
    for m in (5, 6, 7):
        tx(year, f"2026-{m:02d}-03", 999, note="Gym membership")
    assert "Gym Membership started" in " | ".join(i["what"] for i in planning.timeline(year)["items"])  # this one clearly began part-way through
    year.execute("INSERT INTO payslips (sha256,name,period,gross_minor,net_minor) VALUES ('a','a','2026-06',400000,300000), ('b','b','2026-07',440000,330000)")
    assert any("Net salary rose from 3,000.00 to 3,300.00" in i["what"] for i in planning.timeline(year)["items"])


def test_suggestions_are_rules_with_the_numbers_behind_them(conn, monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: date(2026, 12, 15))
    for m in range(1, 13):
        tx(conn, f"2026-{m:02d}-25", 200000, kind="income", cat="salary", account="NL1")
        tx(conn, f"2026-{m:02d}-05", 195000, cat="rent", account="NL1", note="Everything")
    tx(conn, "2026-12-08", 40000, cat="shopping", note="Zara")
    for m in (9, 10, 11):
        tx(conn, f"2026-{m:02d}-08", 10000, cat="shopping", note="Zara")
    text = " | ".join(s["text"] for s in planning.suggestions(conn)["items"])
    assert "spent 100.00 more than came in" in text
    assert "Shopping was 400.00" in text and "300%" in text
    assert "not advice" in planning.suggestions(conn)["note"]


def test_the_detective_collects_the_odd_things(conn, monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: date(2026, 12, 15))
    tx(conn, "2026-12-03", 4999, account="A", note="Zalando")
    tx(conn, "2026-12-03", 4999, account="A", note="Zalando")
    kinds = {i["kind"] for i in planning.money_detective(conn)["items"]}
    assert "duplicate payments" in kinds and "not proven" in kinds


def test_family_money_counts_a_payment_only_when_the_name_is_printed_on_it(conn):
    from finance.modules import people

    people.add_person(conn, {"name": "Amma", "relation": "mother"})
    people.add_person(conn, {"name": "Ann", "relation": "friend"})
    tx(conn, "2026-03-01", 20000, note="Overboeking Amma maandelijks")
    tx(conn, "2026-04-01", 20000, note="Overboeking amma maandelijks")
    tx(conn, "2026-05-01", 5000, kind="income", note="Amma terug")
    tx(conn, "2026-05-02", 7000, note="Hannah birthday gift")  # 'Ann' is inside 'Hannah': not a match
    tx(conn, "2026-05-03", 3000, note="Ann lunch")
    f = {p["name"]: p for p in planning.family_money(conn)["people"]}
    assert f["Amma"]["payments"] == 3 and f["Amma"]["sent"] == 400.0 and f["Amma"]["received"] == 50.0 and f["Amma"]["last"] == "2026-05-01"
    assert f["Ann"]["payments"] == 1 and f["Ann"]["sent"] == 30.0  # a whole word only
    assert f["Amma"]["by_year"] == [{"year": "2026", "sent": 400.0, "received": 50.0}]


def test_money_put_into_investments_is_saved_and_a_reimbursed_trip_is_not_spending(conn, monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: date(2026, 3, 15))
    tx(conn, "2026-01-25", 300000, kind="income", cat="salary", account="NL1", note="Acme salary")
    tx(conn, "2026-01-02", 100000, cat="rent", account="NL1", note="Huur")
    tx(conn, "2026-01-15", 50000, cat="investments", account="NL1", note="Degiro")
    tx(conn, "2026-01-20", 80000, cat="travel", account="NL1", note="Flights")
    flights = conn.execute("SELECT id FROM transactions WHERE note='Flights'").fetchone()[0]
    refund = tx(conn, "2026-01-28", 80000, kind="income", cat="other", account="NL1", note="Employer reimbursement")
    events.assign(conn, {"event": "Work trip", "main": "trips", "sub": "flights", "transaction_ids": [flights, refund]})
    jan = planning.savings_overview(conn)["months"][0]
    assert (jan["income"], jan["spent"], jan["invested"], jan["refunded"]) == (
        3000.0,
        1000.0,
        500.0,
        800.0,
    )  # rent only: flights were reimbursed, the ETF is saved
    assert (jan["saved"], jan["rate"], jan["kept_in_accounts"]) == (2000.0, 66.7, 1500.0)


def test_the_totals_check_shows_gaps_left_out_money_and_warns_in_words(conn, monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: date(2026, 6, 15))
    tx(conn, "2026-01-25", 300000, kind="income", cat="transfers", account="NL1", note="Overschrijving")  # salary sorted as a transfer
    tx(conn, "2026-01-10", 50000, cat="groceries", account="NL1", note="Albert Heijn")
    tx(conn, "2026-02-10", 1000, cat="other", account="NL1", note="Unknown")
    for start, end in (("2026-01-01", "2026-01-31"), ("2026-04-01", "2026-04-30")):
        conn.execute(
            "INSERT INTO statement_files (sha256,name,found,added,status,account,period_start,period_end) VALUES (?,?,?,?,?,?,?,?)",
            (start, start, 1, 1, "verified", "NL01BANK0001234", start, end),
        )
    conn.commit()
    r = planning.totals_check(conn)
    assert r["accounts"][0]["account"] == "…1234" and r["accounts"][0]["months_without_a_statement"] == ["2026-02", "2026-03"]
    assert r["left_out_of_income_and_spending"]["transfers_in"] == {"payments": 1, "total": 3000.0}
    assert r["left_out_of_income_and_spending"]["uncategorised"]["payments"] == 1
    text = " ".join(r["warnings"])
    assert "no statement for 2 month" in text and "mis-sorted" in text and "no category" in text
