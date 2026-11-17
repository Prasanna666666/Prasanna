"""The dashboard says which month it compares with, hides a tile that has nothing to show, and does not let a net worth without account balances look complete (review items F1 to F3)."""

from pathlib import Path

APP = (Path(__file__).resolve().parents[1] / "src" / "finance" / "static" / "app.js").read_text(encoding="utf-8")


def test_the_comparison_names_the_month_it_compares_with():
    assert "monthly vs before" not in APP
    assert "monthly vs ${monthName(previousMonth(month))}" in APP


def test_a_due_tile_with_no_payments_is_not_drawn():
    assert "dueSoon.items.length === 0" in APP
    assert "'grid g3'" in APP


def test_net_worth_without_account_balances_says_so():
    assert "without account balances: no statements read yet" in APP


def test_the_dashboard_says_whether_the_month_is_proven_and_how_fresh_it_is():
    assert "tool('month_proof', { month })" in APP
    assert "coverage(month, proof, txs)," in APP
    assert "is not proven:" in APP and "These figures may be incomplete." in APP
    assert "Newest payment:" in APP


def test_net_worth_says_how_many_holdings_were_left_out_and_savings_say_through_when():
    assert "not counted (no exchange rate)" in APP
    assert "saved, through ${through}" in APP
