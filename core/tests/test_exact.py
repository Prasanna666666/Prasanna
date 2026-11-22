"""WP3.4c: exact arithmetic, units and dates, computed by code (never a model). Hostile and edge inputs included."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from atlas_core.exact import (
    MAX_EXPR,
    ExactError,
    add_days,
    add_months,
    calculate,
    convert,
    days_between,
    parse_date,
    weekday,
)


def code(fn, *a) -> str:
    with pytest.raises(ExactError) as e:
        fn(*a)
    return str(e.value)


@pytest.mark.parametrize(
    ("expr", "dec"),
    [("1250.50 + 3.25", "1253.75"), ("0.1 + 0.2", "0.3"), ("2 * (3 + 4)", "14"), ("-5 + 2", "-3"), ("2 ** 10", "1024"), ("2 ^ -2", "0.25"),
     ("1.250,50 + 1", "1251.5"), ("1,250.50 * 2", "2501"), ("10 / 4", "2.5"), ("--3", "3"), ("(1+2)*(3+4)/7", "3"), ("100 - 0.01", "99.99")],
)  # fmt: skip
def test_arithmetic_is_exact_not_float(expr, dec):
    assert calculate(expr).exact_decimal == dec


def test_a_non_terminating_division_is_flagged_never_silently_rounded():
    n = calculate("1 / 3")
    assert n.value == Fraction(1, 3) and n.exact_decimal is None and n.rounded(4) == "0.3333"
    assert calculate("2 / 3").rounded(2) == "0.67"


@pytest.mark.parametrize(
    "expr", ["1 / 0", "0 ^ -1", "1 +", "(1", "1)", "abc", "1 2", "", "   ", "__import__('os')", "1e3", "1 ; 2", "2 ** 0.5", "2 ** 65", "1,250 + 1"]
)
def test_bad_syntax_zero_division_and_oversize_are_refused_without_echoing_input(expr):
    assert code(calculate, expr) in {"bad_expression", "division_by_zero", "bad_exponent", "bad_number"}
    assert expr.strip() == "" or expr not in code(calculate, expr)


def test_size_and_length_are_bounded():
    assert code(calculate, "9" * (MAX_EXPR + 1)) == "bad_expression"
    assert code(calculate, "(" + "99999999999 * " * 12 + "1) ** 64") == "too_large"
    assert code(calculate, None) == "bad_expression"


def test_the_exponent_must_be_a_whole_number_within_bounds_and_no_eval_is_used():
    import atlas_core.exact as m

    text = Path(m.__file__).read_text()
    assert "eval(" not in text and "float(" not in text


@pytest.mark.parametrize(
    ("value", "a", "b", "dec"),
    [("1", "km", "m", "1000"), ("1", "in", "cm", "2.54"), ("1", "mi", "km", "1.609344"), ("1", "lb", "kg", "0.45359237"), ("16", "oz", "lb", "1"), ("1", "gal_us", "l", "3.785411784"),
     ("2", "h", "min", "120"), ("1", "week", "d", "7"), ("0", "c", "f", "32"), ("212", "f", "c", "100"), ("0", "c", "k", "273.15"), ("100", "c", "c", "100")],
)  # fmt: skip
def test_unit_conversion_uses_exact_ratios(value, a, b, dec):
    assert convert(value, a, b).exact_decimal == dec


def test_conversion_refuses_unknown_and_mixed_dimensions():
    assert code(convert, "1", "m", "kg") == "incompatible_units"
    assert code(convert, "1", "parsec", "m") == "unknown_unit"
    assert code(convert, "1", "c", "m") == "unknown_unit"
    assert code(convert, "x", "m", "km") == "bad_number"


def test_dates_are_exact_and_strict():
    assert days_between("2026-01-01", "2026-03-01") == 59 and days_between("2026-03-01", "2026-01-01") == -59
    assert days_between("2024-02-28", "2024-03-01") == 2  # leap year
    assert add_days("2026-12-31", 1) == "2027-01-01" and add_days("2026-03-01", -1) == "2026-02-28"
    assert weekday("2026-11-22") == "sunday"
    for bad in ("2026-13-01", "2026-02-30", "26-01-01", "2026-1-1", "2026-01-01T00:00", " 2026-01-01", "", None, 20260101):
        assert code(parse_date, bad) == "bad_date"


def test_month_arithmetic_clamps_and_says_so():
    assert add_months("2026-01-31", 1) == ("2026-02-28", True)
    assert add_months("2024-01-31", 1) == ("2024-02-29", True)
    assert add_months("2026-01-15", 1) == ("2026-02-15", False)
    assert add_months("2026-12-15", 1) == ("2027-01-15", False) and add_months("2026-01-15", -1) == ("2025-12-15", False)
    assert add_months("2026-03-31", -1) == ("2026-02-28", True) and add_months("2026-01-31", 12) == ("2027-01-31", False)
    assert code(add_months, "9999-12-01", 1) == "bad_date" and code(add_days, "9999-12-31", 1) == "bad_date"
    assert code(add_days, "2026-01-01", True) == "bad_number"


# ---- the typed computation as the API serves it ----------------------------------------------------------------------------------------------------------------
def test_compute_results_have_the_contract_shape_and_say_when_a_value_is_not_a_finite_decimal():
    from atlas_core import contracts
    from atlas_core.exact import compute

    cases = [
        (("arithmetic", ["1250.50 + 3.25"]), ("1253.75", True, None, False)),
        (("arithmetic", ["1 / 3"]), ("1/3", False, "0.333333", False)),
        (("convert", ["1", "in", "cm"]), ("2.54", True, None, False)),
        (("days_between", ["2026-01-01", "2026-03-01"]), ("59", True, None, False)),
        (("add_days", ["2026-12-31", "1"]), ("2027-01-01", True, None, False)),
        (("add_months", ["2026-01-31", "1"]), ("2026-02-28", True, None, True)),
        (("weekday", ["2026-11-22"]), ("sunday", True, None, False)),
    ]
    for (kind, args), (value, exact, approx, clamped) in cases:
        result = compute(kind, args)
        contracts.validate("ComputeResult", result, "1.1")
        assert (result["value"], result["exact"], result["approximate"], result["clamped"]) == (value, exact, approx, clamped), kind


@pytest.mark.parametrize(
    ("kind", "args"),
    [
        ("nope", ["1"]),
        ("arithmetic", []),
        ("arithmetic", ["1", "2"]),
        ("add_days", ["2026-01-01", "1.5"]),
        ("add_days", ["2026-01-01", "x"]),
        ("add_months", ["2026-01-01", "99999999999"]),
        ("convert", ["1", "m", "kg"]),
    ],
)
def test_compute_refuses_a_bad_request_with_a_short_code(kind, args):
    from atlas_core.exact import compute

    with pytest.raises(ExactError):
        compute(kind, args)
