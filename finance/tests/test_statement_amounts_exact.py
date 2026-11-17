"""A statement amount is read exactly or not at all. A figure with a third decimal that is not zero (a three-decimal currency such as KWD or BHD) used to be rounded to cents without a word; now the cell is not taken as an amount, so the statement cannot be proven and is held back (review item O-1)."""

import pytest

from finance import tables

LAYOUT = tables.Layout(header_line=0, roles=["date", "desc", "amount"], date_format="%Y-%m-%d")
COMMA = tables.Layout(header_line=0, roles=["date", "desc", "amount"], date_format="%Y-%m-%d", decimal=",", thousands=".")


@pytest.mark.parametrize(
    ("text", "layout", "minor"),
    [
        ("12.50", LAYOUT, 1250),
        ("1,250.50".replace(",", ""), LAYOUT, 125050),
        ("1.250,50", COMMA, 125050),
        ("12.500", LAYOUT, 1250),
        ("12", LAYOUT, 1200),
        ("-0.05", LAYOUT, -5),
    ],
)
def test_two_decimal_amounts_and_trailing_zeros_are_exact(text, layout, minor):
    assert tables.parse_money(text, layout) == (minor, None)


@pytest.mark.parametrize(("text", "layout"), [("1250.505", LAYOUT), ("12.001", LAYOUT), ("1.250,505", COMMA), ("0.125", LAYOUT)])
def test_a_third_decimal_that_is_not_zero_is_not_rounded_away(text, layout):
    assert tables.parse_money(text, layout) is None


def _read(rows):
    cols = [(0, 60), (70, 200), (210, 260), (270, 320), (330, 400)]
    table = [[tables.Cell(*[cols[i][0], cols[i][1], c]) for i, c in enumerate(r) if c != ""] for r in rows]
    layout = tables.Layout(
        header_line=0,
        roles=["date", "description", "debit", "credit", "balance"],
        date_format="%d-%m-%Y",
        decimal=",",
        thousands=".",
        debit_words=["af"],
        credit_words=["bij"],
    )
    return tables.parse_table(table, layout)


HEAD = ["Datum", "Omschrijving", "Af", "Bij", "Saldo"]


def test_a_statement_with_a_three_decimal_amount_is_not_proved_and_nothing_is_rounded():
    exact = _read([HEAD, ["01-10-2026", "Opening", "", "", "2.000,00"], ["02-10-2026", "Shop", "23,45", "", "1.976,55"]])
    three = _read([HEAD, ["01-10-2026", "Opening", "", "", "2.000,000"], ["02-10-2026", "Shop", "23,455", "", "1.976,545"]])
    assert exact.status == "verified"
    assert three.status != "verified"
    assert all(t.amount_minor != 2346 and t.amount_minor != 2345 for t in three.txns if t.desc == "Shop")
