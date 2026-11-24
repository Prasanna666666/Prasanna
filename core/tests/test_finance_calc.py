"""Stage 5, Finance: exact arithmetic by code. Every figure is computed by two independent routes, a summary names its inputs and can be re-verified, and a tampered figure is refused."""

from __future__ import annotations

from decimal import Decimal

import pytest

from atlas_core.finance_calc import (
    CalcError,
    budget_variance,
    by_category,
    by_month,
    cash_flow,
    month_over_month,
    previous_month,
    recurring,
    summary_records,
    total,
    transactions,
    verify_summary,
)
from atlas_core.records import Record, RecordError

pytestmark = pytest.mark.criterion(15)


def tx(rid, day, amount, kind="expense", category="groceries", merchant=""):
    fields = {"amount": amount, "currency": "EUR", "kind": kind, "category": category}
    if merchant:
        fields["merchant"] = merchant
    return Record(rid, "finance", day, f"{category} {rid}", fields)


DATA = [
    tx("t1", "2026-09-03", "100.10", merchant="Shop"),
    tx("t2", "2026-09-20", "50.20", category="fuel"),
    tx("t3", "2026-10-02", "0.10", merchant="Shop"),
    tx("t4", "2026-10-02", "0.20", merchant="Shop"),
    tx("t5", "2026-10-15", "412.30", category="rent"),
    tx("s1", "2026-10-01", "3000.00", kind="income", category="salary"),
    tx("n1", "2026-08-05", "9.99", category="media", merchant="Stream"),
    tx("n2", "2026-09-05", "9.99", category="media", merchant="Stream"),
    tx("n3", "2026-10-05", "9.99", category="media", merchant="Stream"),
]


def test_sums_are_exact_where_floats_are_not():
    assert 0.1 + 0.2 != 0.3  # the reason money is never a float
    assert total(t for t in transactions(DATA) if t.record_id in ("t3", "t4")) == Decimal("0.30")
    month = by_month(transactions(DATA))
    assert month == {"2026-08": Decimal("9.99"), "2026-09": Decimal("160.29"), "2026-10": Decimal("422.59")}
    assert sum(by_category(transactions(DATA), "2026-10").values()) == month["2026-10"]  # categories add up to the month, exactly


def test_month_over_month_is_exact_and_the_percentage_is_labelled_rounded_and_absent_without_a_base():
    change = month_over_month(transactions(DATA), "2026-10")
    assert (change.previous, change.current, change.delta) == (Decimal("160.29"), Decimal("422.59"), Decimal("262.30")) and change.percent == Decimal("163.6")
    assert month_over_month(transactions(DATA), "2026-08").percent is None  # no earlier month: no percentage exists
    assert previous_month("2026-01") == "2025-12" and previous_month("2026-03") == "2026-02"


def test_recurring_charges_need_the_same_merchant_the_same_amount_and_consecutive_months():
    found = recurring(transactions(DATA))
    assert found == [("Stream", Decimal("9.99"), ["2026-08", "2026-09", "2026-10"])]
    gap = [tx("a", "2026-01-05", "5.00", merchant="M"), tx("b", "2026-02-05", "5.00", merchant="M"), tx("c", "2026-04-05", "5.00", merchant="M")]
    assert recurring(transactions(gap)) == []  # a missing month breaks the run


def test_budget_variance_and_cash_flow():
    v = budget_variance(transactions(DATA), "2026-10", {"groceries": Decimal("0.50"), "rent": Decimal("400.00"), "fuel": Decimal("60.00")})
    assert (
        v["groceries"] == (Decimal("0.30"), Decimal("0.50"), Decimal("0.20"))
        and v["rent"][2] == Decimal("-12.30")
        and v["fuel"] == (Decimal("0.00"), Decimal("60.00"), Decimal("60.00"))
    )
    assert cash_flow(transactions(DATA), "2026-10") == (Decimal("3000.00"), Decimal("422.59"), Decimal("2577.41"))


def test_a_summary_names_its_inputs_is_a_finance_record_and_can_be_recomputed():
    summaries = summary_records(DATA)
    oct_rent = next(s for s in summaries if s.record_id == "sum-2026-10-rent")
    assert (
        oct_rent.domain == "finance"
        and oct_rent.fields["amount"] == "412.30"
        and "t5" in oct_rent.fields["note"]
        and "computed by code" in oct_rent.fields["note"]
    )
    assert all(verify_summary(s, DATA) for s in summaries)
    assert summary_records(summaries + DATA) == summaries  # a summary never feeds another summary


def test_a_tampered_or_stale_summary_is_refused():
    good = next(s for s in summary_records(DATA) if s.record_id == "sum-2026-10-rent")
    forged = Record(good.record_id, "finance", good.date, good.title, {**good.fields, "amount": "412.31"})
    assert verify_summary(forged, DATA) is False
    missing = [r for r in DATA if r.record_id != "t5"]
    assert verify_summary(good, missing) is False  # an input is gone
    changed = [r if r.record_id != "t5" else tx("t5", "2026-10-15", "500.00", category="rent") for r in DATA]
    assert verify_summary(good, changed) is False  # an input changed
    assert verify_summary(tx("x", "2026-10-01", "1.00"), DATA) is False  # not a summary at all


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        ({"amount": "12.5", "currency": "EUR", "kind": "expense"}, "bad_amount"),
        ({"amount": "1e3", "currency": "EUR", "kind": "expense"}, "bad_amount"),
        ({"amount": "12.50", "currency": "EUR", "kind": "refund"}, "bad_kind"),
        ({"amount": "12.50", "kind": "expense"}, "missing_field"),
        ({"amount": "12.50", "currency": "EUR", "kind": "expense", "colour": "red"}, "unknown_field"),
    ],
)
def test_an_amount_is_two_exact_decimals_and_a_record_that_does_not_fit_is_refused_with_a_code(fields, code):
    with pytest.raises(RecordError) as e:
        Record("bad", "finance", "2026-10-01", "x", fields)
    assert e.value.code == code


def test_a_date_that_is_not_a_calendar_date_is_refused():
    with pytest.raises(CalcError) as e:
        transactions([Record("d", "finance", "not-a-date", "x", {"amount": "1.00", "currency": "EUR", "kind": "expense"})])
    assert e.value.code == "bad_date"


def usd(rid, day, amount, category="groceries"):
    return Record(rid, "finance", day, f"{category} {rid}", {"amount": amount, "currency": "USD", "kind": "expense", "category": category})


def test_amounts_in_different_currencies_are_never_added_or_relabelled():
    """ATLAS-FIN-029: 100.00 EUR plus 100.00 USD is not 200.00 of anything."""
    from atlas_core.finance_calc import CalcError, currencies, only

    mixed = [tx("e1", "2026-10-02", "100.00"), usd("u1", "2026-10-03", "100.00"), Record("i1", "finance", "2026-10-04", "inr", {"amount": "8300.00", "currency": "INR", "kind": "expense", "category": "groceries"})]
    txs = transactions(mixed)
    assert currencies(txs) == ["EUR", "INR", "USD"]
    for aggregate in (total, by_month, lambda t: by_category(t, "2026-10"), lambda t: cash_flow(t, "2026-10")):
        with pytest.raises(CalcError) as refused:
            aggregate(txs)
        assert refused.value.code == "mixed_currency"
    assert total(only(txs, "USD")) == Decimal("100.00") and total(only(txs, "EUR")) == Decimal("100.00")
    summaries = {s.record_id: s for s in summary_records(mixed)}
    assert set(summaries) == {"sum-2026-10-groceries", "sum-2026-10-groceries-USD", "sum-2026-10-groceries-INR"}
    assert {k: (s.fields["amount"], s.fields["currency"]) for k, s in summaries.items()} == {
        "sum-2026-10-groceries": ("100.00", "EUR"),
        "sum-2026-10-groceries-USD": ("100.00", "USD"),
        "sum-2026-10-groceries-INR": ("8300.00", "INR"),
    }
    assert all(verify_summary(s, mixed) for s in summaries.values())
    forged = Record(summaries["sum-2026-10-groceries-USD"].record_id, "finance", "2026-10-28", "x", {**summaries["sum-2026-10-groceries-USD"].fields, "currency": "EUR"})
    assert verify_summary(forged, mixed) is False  # a summary relabelled with another currency does not verify


@pytest.mark.parametrize("bad", ["eur", "EURO", "€", "", "E1R"])
def test_a_currency_that_is_not_an_iso_code_is_refused_at_the_record_boundary(bad):
    with pytest.raises(RecordError):
        Record("x", "finance", "2026-10-02", "t", {"amount": "1.00", "currency": bad, "kind": "expense"})
