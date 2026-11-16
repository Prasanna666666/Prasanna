"""Amounts are read as the decimal they were written as and rounded once, half away from zero; no cent is lost or invented."""

import pytest
from kit import money

from finance import wealth
from finance.modules import money as finance_money
from finance.modules import statement_import
from finance.payslips import from_model


@pytest.mark.parametrize(
    ("written", "minor"),
    [
        (1.005, 101),
        ("1.005", 101),
        (12.345, 1235),
        (0.01, 1),
        (0.1 + 0.2, 30),
        (-1.005, -101),
        (-12.345, -1235),
        (0, 0),
        (19.99, 1999),
        (4.35, 435),
        (1234567890123.45, 123456789012345),
        ("99999999999.995", 10000000000000),
    ],
)
def test_to_minor_is_exact(written, minor):
    assert money.to_minor(written) == minor


@pytest.mark.parametrize(("digits", "expected"), [(0, 1), (2, 101), (3, 1005)])
def test_other_minor_unit_conventions(digits, expected):
    assert money.to_minor("1.005", digits) == expected


@pytest.mark.parametrize("bad", [True, None, "", "abc", float("nan"), float("inf"), [1]])
def test_not_an_amount(bad):
    with pytest.raises(ValueError):
        money.to_minor(bad)


def test_total_rounds_once_at_the_end():
    assert money.total_to_minor("3", "0.335") == 101  # 1.005 -> 101, not 3 * round(0.335)
    assert money.total_to_minor(0.1, 3) == 30
    assert money.scale_minor("2.5", 1001) == 2503


def test_manual_transaction_uses_the_decimal_amount(tmp_path):
    assert finance_money.to_minor(1.005) == 101
    assert finance_money.to_minor(12.345) == 1235


def test_statement_amounts_and_payslips_use_the_decimal(tmp_path):
    assert statement_import._money(-1.005) == 101
    assert statement_import._money(True) is None
    slip = from_model({"gross": 2000.005, "net": 1500.125, "period": "2025-01"})
    assert slip is not None
    assert (slip.gross_minor, slip.net_minor) == (200001, 150013)


def test_holdings_value_is_units_times_price_rounded_once():
    assert wealth.kit_money.total_to_minor("3", "0.335") == 101
