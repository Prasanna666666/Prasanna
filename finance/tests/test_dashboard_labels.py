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
