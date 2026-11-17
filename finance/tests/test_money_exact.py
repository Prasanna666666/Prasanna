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


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("1,250.50", "1250.50"),
        ("1.250,50", "1250.50"),
        ("12,5", "12.5"),
        ("12.5", "12.5"),
        ("1,25", "1.25"),
        ("EUR 1 250,50", "1250.50"),
        ("1,250,000", "1250000"),
        ("-5,5", "-5.5"),
        ("7", "7"),
    ],
)
def test_amounts_typed_as_text_are_read_in_either_notation(written, expected):
    from decimal import Decimal

    assert money.parse_amount(written) == Decimal(expected)


@pytest.mark.parametrize("written", ["1,250", "1.250", "1.2.3", "abc", "", "1,250,50"])
def test_an_amount_that_could_mean_two_things_is_refused_not_guessed(written):
    with pytest.raises(ValueError):
        money.parse_amount(written)


def test_a_european_amount_from_the_model_is_not_silently_read_as_1_25(conn):
    from finance import toolrun

    tool = toolrun.registry(toolrun.ALL)["add_transaction"]
    assert toolrun._coerce(tool, {"amount": "1.250,50"}) == {"amount": 1250.5}
    _out, failed = toolrun.run_tool(conn, "add_transaction", {"amount": "1,250", "category": "food"})
    assert failed, "an ambiguous amount is an error the model can correct, not a guess"
    assert conn.execute("SELECT count(*) FROM transactions").fetchone()[0] == 0


def _fresh(tmp_path, monkeypatch, currency_code):
    from finance import db as finance_db
    from finance.modules import ALL

    monkeypatch.setenv("ATLAS_HOME", str(tmp_path))
    monkeypatch.setenv("ATLAS_ALLOW_PLAIN", "1")
    conn = finance_db.connect()
    finance_db.migrate(conn, ALL)
    conn.execute("INSERT OR REPLACE INTO settings VALUES ('currency', ?)", (currency_code,))
    conn.commit()
    return conn


@pytest.mark.parametrize("code", ["EUR", "USD", "GBP"])
def test_two_decimal_currencies_keep_the_cent(tmp_path, monkeypatch, code):
    conn = _fresh(tmp_path, monkeypatch, code)
    finance_money.add_transaction(conn, {"amount": "1.005", "category": "food"})
    finance_money.add_transaction(conn, {"amount": "12.345", "category": "food"})
    assert [r[0] for r in conn.execute("SELECT amount_minor FROM transactions ORDER BY id")] == [101, 1235]


def test_a_zero_decimal_currency_is_stored_consistently_and_shown_back_exactly(tmp_path, monkeypatch):
    conn = _fresh(tmp_path, monkeypatch, "JPY")
    out = finance_money.add_transaction(conn, {"amount": 1000, "category": "food"})
    assert out["amount"] == 1000 and conn.execute("SELECT amount_minor FROM transactions").fetchone()[0] == 100000
    assert finance_money.summary(conn, {})["spent"] == 1000


def test_a_three_decimal_currency_is_refused_when_the_third_decimal_would_be_lost(tmp_path, monkeypatch):
    conn = _fresh(tmp_path, monkeypatch, "KWD")
    with pytest.raises(ValueError, match="3 decimals"):
        finance_money.add_transaction(conn, {"amount": "1.005", "category": "food"})
    assert conn.execute("SELECT count(*) FROM transactions").fetchone()[0] == 0
    finance_money.add_transaction(conn, {"amount": "1.500", "category": "food"})  # fits in hundredths: kept exactly
    assert conn.execute("SELECT amount_minor FROM transactions").fetchone()[0] == 150
    with pytest.raises(ValueError, match="3 decimals"):
        wealth.add_holding(conn, {"kind": "asset", "name": "x", "value": "2.0005", "currency": "BHD"})


def test_large_negative_and_repeated_amounts_stay_exact(tmp_path, monkeypatch):
    conn = _fresh(tmp_path, monkeypatch, "EUR")
    for _ in range(2000):
        finance_money.add_transaction(conn, {"amount": "0.07", "category": "food"})
    finance_money.add_transaction(conn, {"amount": "1234567890.12", "category": "big"})
    assert conn.execute("SELECT sum(amount_minor) FROM transactions").fetchone()[0] == 2000 * 7 + 123456789012
    assert money.to_minor("-1234567890.125") == -123456789013
