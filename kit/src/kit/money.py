"""Money as whole minor units (cents), converted without binary floating point.

`round(float(x) * 100)` loses a cent on amounts such as 1.005 (the float is 1.00499999...). Every amount a person or a model
gives is read as the decimal it was written as, and rounded once, half away from zero, to the minor unit."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

MINOR_DIGITS = 2  # how many decimals the stored minor unit holds (cents)


def as_decimal(value: object) -> Decimal:
    """The decimal a number or text was written as. Booleans, empty text, NaN and infinity are not amounts."""
    if isinstance(value, bool) or value is None:
        raise ValueError("not an amount")
    try:
        found = Decimal(str(value).strip()) if isinstance(value, (str, int, float, Decimal)) else None
    except InvalidOperation as e:
        raise ValueError("not an amount") from e
    if found is None or not found.is_finite():
        raise ValueError("not an amount")
    return found


def _to_unit(amount: Decimal, digits: int) -> int:
    return int((amount * (Decimal(10) ** digits)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def to_minor(value: object, digits: int = MINOR_DIGITS) -> int:
    """The amount in minor units, rounded once half away from zero: 1.005 -> 101, 12.345 -> 1235, -1.005 -> -101."""
    return _to_unit(as_decimal(value), digits)


def total_to_minor(units: object, price: object, digits: int = MINOR_DIGITS) -> int:
    """What `units` of something at `price` each come to, rounded once at the end (not per unit)."""
    return _to_unit(as_decimal(units) * as_decimal(price), digits)


def scale_minor(units: object, price_minor: int) -> int:
    """What `units` at a price already in minor units come to, in minor units."""
    return int((as_decimal(units) * price_minor).quantize(Decimal(1), rounding=ROUND_HALF_UP))
