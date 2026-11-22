"""Exact numbers, units and dates, computed by code and never by a model (a product principle: INTELLIGENCE_AND_PERFORMANCE.md, G-021 context).

Arithmetic is done on exact rationals (`Fraction`) with a hand-written parser: no `eval`, no floats, bounded input, bounded exponents. A division that is not a terminating decimal is
reported as such (the exact fraction plus a labelled rounded form) and is never silently rounded. Dates are ISO calendar dates only; month arithmetic that has to clamp to the end of a
month says so. Unit conversion uses a fixed table of exact ratios and refuses unknown units and mixed dimensions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

from kit.money import parse_amount

MAX_EXPR = 200
MAX_EXPONENT = 64
MONTHS = 12
MAX_BITS = 1400  # of numerator plus denominator (about 420 digits), so a hostile expression cannot grow a number without bound
DISPLAY_DIGITS = 6
_TOKEN = re.compile(r"\s*(?:(\d[\d.,]*|\.\d+)|(\*\*|[-+*/()^]))")


class ExactError(ValueError):
    """Anything that cannot be computed exactly: syntax, size, division by zero, unknown unit, bad date. The text is a short code, never an echo of the input."""


@dataclass(frozen=True)
class Number:
    value: Fraction

    @property
    def exact_decimal(self) -> str | None:
        """The value as a terminating decimal, or None when it has no finite decimal form (1/3)."""
        d = self.value.denominator
        for p in (2, 5):
            while d % p == 0:
                d //= p
        if d != 1:
            return None
        return format(Decimal(self.value.numerator) / Decimal(self.value.denominator), "f") if self.value.denominator != 1 else str(self.value.numerator)

    def rounded(self, digits: int = DISPLAY_DIGITS) -> str:
        """A labelled approximation; callers must show it as approximate when `exact_decimal` is None."""
        quantum = Fraction(1, 10**digits)
        scaled = (self.value / quantum).__round__()
        return format(Decimal(scaled) / Decimal(10**digits), "f")


def _check_size(x: Fraction) -> Fraction:
    if abs(x.numerator).bit_length() + x.denominator.bit_length() > MAX_BITS:
        raise ExactError("too_large")
    return x


def _number(text: str) -> Fraction:
    try:
        d = parse_amount(text)
    except ValueError:
        raise ExactError("bad_number") from None
    return Fraction(d)


class _Parser:
    def __init__(self, text: str) -> None:
        if not isinstance(text, str) or len(text) > MAX_EXPR or not text.strip():
            raise ExactError("bad_expression")
        self.tokens: list[str] = []
        pos = 0
        while pos < len(text):
            m = _TOKEN.match(text, pos)
            if m is None:
                if text[pos:].strip():
                    raise ExactError("bad_expression")
                break
            self.tokens.append(m.group(1) or m.group(2))
            pos = m.end()
        self.i = 0

    def peek(self) -> str | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self) -> str:
        taken = self.tokens[self.i]
        self.i += 1
        return taken

    def parse(self) -> Fraction:
        value = self.sum()
        if self.peek() is not None:
            raise ExactError("bad_expression")
        return value

    def sum(self) -> Fraction:
        value = self.product()
        while self.peek() in ("+", "-"):
            op = self.take()
            right = self.product()
            value = _check_size(value + right if op == "+" else value - right)
        return value

    def product(self) -> Fraction:
        value = self.unary()
        while self.peek() in ("*", "/"):
            op = self.take()
            right = self.unary()
            if op == "/":
                if right == 0:
                    raise ExactError("division_by_zero")
                value = _check_size(value / right)
            else:
                value = _check_size(value * right)
        return value

    def unary(self) -> Fraction:
        if self.peek() in ("-", "+"):
            sign = self.take()
            inner = self.unary()
            return -inner if sign == "-" else inner
        return self.power()

    def power(self) -> Fraction:
        base = self.atom()
        if self.peek() in ("**", "^"):
            self.take()
            exponent = self.unary()
            if exponent.denominator != 1 or abs(exponent) > MAX_EXPONENT:
                raise ExactError("bad_exponent")
            if base == 0 and exponent < 0:
                raise ExactError("division_by_zero")
            if (abs(base.numerator).bit_length() + base.denominator.bit_length()) * abs(int(exponent)) > MAX_BITS * 2:
                raise ExactError("too_large")  # refused before the power is computed
            return _check_size(base ** int(exponent))
        return base

    def atom(self) -> Fraction:
        head = self.peek()
        if head is None:
            raise ExactError("bad_expression")
        if head == "(":
            self.take()
            value = self.sum()
            if self.peek() != ")":
                raise ExactError("bad_expression")
            self.take()
            return value
        if head[0].isdigit() or head[0] == ".":
            return _number(self.take())
        raise ExactError("bad_expression")


def calculate(expression: str) -> Number:
    """Evaluate +, -, *, /, ** (or ^) and parentheses exactly. Amounts may be written `1,250.50` or `1.250,50`; an ambiguous one (`1,250`) is refused."""
    return Number(_Parser(expression).parse())


# -- units: exact ratios to a base unit per dimension --------------------------------------------------------------------------------------------------------
_F = Fraction
UNITS: dict[str, tuple[str, Fraction]] = {
    "mm": ("length", _F(1, 1000)), "cm": ("length", _F(1, 100)), "m": ("length", _F(1)), "km": ("length", _F(1000)),
    "in": ("length", _F(254, 10000)), "ft": ("length", _F(3048, 10000)), "yd": ("length", _F(9144, 10000)), "mi": ("length", _F(1609344, 1000)),
    "mg": ("mass", _F(1, 1000000)), "g": ("mass", _F(1, 1000)), "kg": ("mass", _F(1)), "oz": ("mass", _F(28349523125, 1000000000000)), "lb": ("mass", _F(45359237, 100000000)),
    "ml": ("volume", _F(1, 1000)), "l": ("volume", _F(1)), "gal_us": ("volume", _F(3785411784, 1000000000)),
    "s": ("time", _F(1)), "min": ("time", _F(60)), "h": ("time", _F(3600)), "d": ("time", _F(86400)), "week": ("time", _F(604800)),
}  # fmt: skip
TEMPERATURE = ("c", "f", "k")


def convert(value: str, source: str, target: str) -> Number:
    amount = _number(str(value))
    if source in TEMPERATURE and target in TEMPERATURE:
        kelvin = amount + _F(27315, 100) if source == "c" else (amount - 32) * _F(5, 9) + _F(27315, 100) if source == "f" else amount
        out = kelvin - _F(27315, 100) if target == "c" else (kelvin - _F(27315, 100)) * _F(9, 5) + 32 if target == "f" else kelvin
        return Number(out)
    if source not in UNITS or target not in UNITS:
        raise ExactError("unknown_unit")
    (dim_a, ratio_a), (dim_b, ratio_b) = UNITS[source], UNITS[target]
    if dim_a != dim_b:
        raise ExactError("incompatible_units")
    return Number(amount * ratio_a / ratio_b)


# -- dates ------------------------------------------------------------------------------------------------------------------------------------------------------
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


def parse_date(text: str) -> date:
    if not isinstance(text, str) or not _ISO.match(text):
        raise ExactError("bad_date")
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ExactError("bad_date") from None


def days_between(start: str, end: str) -> int:
    """Whole days from `start` to `end` (negative when `end` is earlier)."""
    return (parse_date(end) - parse_date(start)).days


def add_days(start: str, days: int) -> str:
    if isinstance(days, bool) or not isinstance(days, int):
        raise ExactError("bad_number")
    try:
        return (parse_date(start) + timedelta(days=days)).isoformat()
    except OverflowError:
        raise ExactError("bad_date") from None


def add_months(start: str, months: int) -> tuple[str, bool]:
    """(date, clamped): January 31 plus one month is the last day of February and `clamped` is True, so the caller can say so."""
    if isinstance(months, bool) or not isinstance(months, int):
        raise ExactError("bad_number")
    d = parse_date(start)
    index = d.year * MONTHS + (d.month - 1) + months
    year, month = divmod(index, MONTHS)
    month += 1
    if not 1 <= year <= 9999:  # noqa: PLR2004
        raise ExactError("bad_date")
    last = (date(year + (month == MONTHS), month % MONTHS + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(d.day, last)).isoformat(), d.day > last


def weekday(text: str) -> str:
    return ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[parse_date(text).weekday()]
