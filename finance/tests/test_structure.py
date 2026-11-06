"""The five sections of the finance structure: income (salary, bonus, other), savings, investments (paid in, value, gain or loss) and net worth."""

from datetime import date

import pytest

from finance import categorize, clock, planning, wealth
from tests.test_tally import tx


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: date(2026, 12, 15))


def test_a_bonus_is_recognised_as_its_own_kind_of_income():
    for note in ("Acme BV Bonus 2026", "Gratificatie december", "13e maand uitbetaling", "Winstdeling Acme"):
        assert categorize.by_rules(note, "income") == "bonus", note
    assert categorize.by_rules("Acme BV Salaris", "income") != "bonus"


def test_income_is_split_into_salary_bonus_and_other_by_month_and_year(conn):
    for m in (1, 2, 3):
        tx(conn, f"2026-{m:02d}-25", 300000, kind="income", cat="salary", note="Salary")
    tx(conn, "2026-03-28", 100000, kind="income", cat="bonus", note="Bonus")
    tx(conn, "2026-02-14", 2500, kind="income", cat="interest", note="Interest")
    tx(conn, "2026-03-02", 4000, kind="income", cat="refund", note="Refund")
    tx(conn, "2025-12-25", 280000, kind="income", cat="salary", note="Salary")
    r = planning.income_breakdown(conn)
    march = next(m for m in r["months"] if m["month"] == "2026-03")
    assert march == {"month": "2026-03", "salary": 3000.0, "bonus": 1000.0, "other": 40.0, "total": 4040.0}
    y26 = next(y for y in r["years"] if y["year"] == "2026")
    assert y26 == {"year": "2026", "salary": 9000.0, "bonus": 1000.0, "other": 65.0, "total": 10065.0}
    assert r["latest_year"]["year"] == "2026" and next(y for y in r["years"] if y["year"] == "2025")["total"] == 2800.0


def test_money_that_belongs_to_a_trip_is_not_income(conn):
    from finance.modules import events

    tx(conn, "2026-03-25", 300000, kind="income", cat="salary", note="Salary")
    refund = tx(conn, "2026-03-20", 5000, kind="income", cat="refund", note="Refund flights")
    events.assign(conn, {"event": "Lisbon", "main": "trips", "sub": "flights", "transaction_ids": [refund]})
    assert planning.income_breakdown(conn)["months"][-1]["total"] == 3000.0


def test_savings_are_income_minus_spending_with_the_exact_rate(conn):
    tx(conn, "2026-01-25", 300000, kind="income", cat="salary")
    tx(conn, "2026-01-10", 240000, cat="rent")
    tx(conn, "2026-02-25", 300000, kind="income", cat="salary")
    tx(conn, "2026-02-10", 330000, cat="other")  # a month that spent more than came in
    r = planning.savings_overview(conn)
    jan, feb = r["months"]
    assert (jan["saved"], jan["rate"]) == (600.0, 20.0) and (feb["saved"], feb["rate"]) == (-300.0, -10.0)
    assert r["years"] == [{"year": "2026", "income": 6000.0, "spent": 5700.0, "saved": 300.0, "savings_rate": 5.0, "months": 2}]
    assert r["last12"] == {"months": 2, "income": 6000.0, "spent": 5700.0, "saved": 300.0, "rate": 5.0}
    assert r["best"]["month"] == "2026-01" and r["worst"]["month"] == "2026-02"


def test_a_month_with_no_income_has_no_rate_rather_than_a_made_up_one(conn):
    tx(conn, "2026-01-10", 5000, cat="other")
    assert planning.savings_overview(conn)["months"][0]["rate"] is None


def test_investments_show_what_was_paid_in_the_value_you_entered_and_the_gain_or_loss(conn):
    for m in (1, 2, 3):
        tx(conn, f"2026-{m:02d}-03", 20000, cat="investments", note="Degiro")
    wealth.add_holding(conn, {"name": "World ETF", "kind": "investment", "units": 10, "price": 120, "cost": 1000})
    wealth.add_holding(conn, {"name": "Bitcoin", "kind": "investment", "value": 500, "cost": 800})
    wealth.add_holding(conn, {"name": "Fund X", "kind": "investment", "value": 300})  # cost not typed: no gain or loss claimed for it
    r = wealth.investments_overview(conn)
    assert r["contributed_total"] == 600.0 and r["contributed_by_year"] == [{"year": "2026", "contributed": 600.0, "payments": 3}]
    assert r["value"] == 2000.0 and r["cost"] == 1800.0 and r["gain"] == -100.0 and r["gain_percent"] == -5.6  # +200 on the ETF, -300 on the Bitcoin
    assert r["complete"] is False
    etf = next(h for h in r["holdings"] if h["name"] == "World ETF")
    assert etf["gain"] == 200.0 and next(h for h in r["holdings"] if h["name"] == "Fund X")["gain"] is None


def test_cost_can_be_updated_and_a_negative_cost_is_refused(conn):
    h = wealth.add_holding(conn, {"name": "ETF", "kind": "investment", "value": 100})
    wealth.update_holding(conn, {"id": h["id"], "value": 150, "cost": 120})
    assert wealth.investments_overview(conn)["gain"] == 30.0
    with pytest.raises(ValueError):
        wealth.add_holding(conn, {"name": "x", "kind": "investment", "value": 1, "cost": -5})


def test_an_empty_database_gives_empty_but_valid_overviews(conn):
    assert planning.income_breakdown(conn)["months"] == [] and planning.savings_overview(conn)["last12"]["rate"] is None
    r = wealth.investments_overview(conn)
    assert r["value"] == 0 and r["gain"] is None and r["complete"] is True


def test_only_the_amount_paid_in_can_be_edited(conn):
    h = wealth.add_holding(conn, {"name": "ETF", "kind": "investment", "value": 100})
    wealth.update_holding(conn, {"id": h["id"], "cost": 80})
    r = wealth.investments_overview(conn)
    assert r["value"] == 100.0 and r["gain"] == 20.0
    with pytest.raises(ValueError):
        wealth.update_holding(conn, {"id": h["id"]})
