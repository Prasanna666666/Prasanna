"""parse_table's handling of every kind of printed line, pinned so refactors cannot change what is read."""

from finance import tables
from tests.test_verify import COLS, LAYOUT, table


def parse(rows, **layout):
    lay = tables.Layout(**{**LAYOUT, **layout})
    return tables.parse_table(table(rows, COLS), lay)


HEAD = ["Datum", "Omschrijving", "Af", "Bij", "Saldo"]


def test_a_dated_heading_line_with_nothing_else_is_ignored_not_flagged():
    p = parse([HEAD, ["01-10-2026", "Opening", "", "", "1.000,00"], ["02-10-2026", "", "", "", ""], ["02-10-2026", "Shop", "10,00", "", "990,00"]])
    assert p.issues == [] and len(p.txns) == 1 and p.status == "verified"


def test_a_description_that_wraps_onto_the_next_line_is_joined():
    p = parse([HEAD, ["01-10-2026", "Opening", "", "", "1.000,00"], ["02-10-2026", "Albert Heijn", "10,00", "", "990,00"], ["", "Utrecht 1234", "", "", ""]])
    assert p.txns[0].desc == "Albert Heijn Utrecht 1234"


def test_an_amount_without_any_date_is_reported_never_guessed():
    p = parse([HEAD, ["01-10-2026", "Opening", "", "", "1.000,00"], ["", "Mystery", "10,00", "", "990,00"]])
    assert any("has an amount but no date" in i for i in p.issues) and p.txns == []


def test_a_date_printed_once_for_several_lines_applies_to_all_of_them():
    p = parse(
        [HEAD, ["01-10-2026", "Opening", "", "", "1.000,00"], ["02-10-2026", "A", "10,00", "", "990,00"], ["", "B", "5,00", "", "985,00"]],
        date_on_every_row=False,
    )
    assert [(t.day, t.amount_minor) for t in p.txns] == [("2026-10-02", 1000), ("2026-10-02", 500)] and p.issues == []


def test_a_figure_sitting_in_the_description_column_means_the_columns_were_misread():
    p = parse([HEAD, ["01-10-2026", "Opening", "", "", "1.000,00"], ["02-10-2026", "12,50", "10,00", "", "990,00"]])
    assert any("sits in a column read as text" in i for i in p.issues)


def test_an_undated_balance_line_is_a_checkpoint_and_money_in_or_out_follows_the_column():
    p = parse(
        [HEAD, ["", "Beginsaldo", "", "", "1.000,00"], ["02-10-2026", "Salary", "", "100,00", "1.100,00"], ["03-10-2026", "Shop", "10,00", "", "1.090,00"]]
    )
    assert [(t.kind, t.amount_minor) for t in p.txns] == [("income", 10000), ("expense", 1000)] and p.status == "verified"
