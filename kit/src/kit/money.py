"""Money as whole minor units (cents), converted without binary floating point.

`round(float(x) * 100)` loses a cent on amounts such as 1.005 (the float is 1.00499999...). Every amount a person or a model
gives is read as the decimal it was written as, and rounded once, half away from zero, to the minor unit."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

MINOR_DIGITS = 2  # how many decimals the stored minor unit holds (cents)
THOUSAND_DIGITS = 3  # digits after a thousands separator


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


def parse_amount(text: str) -> Decimal:
    """An amount a person or model typed as text, in either notation: `1,250.50` and `1.250,50` are both 1250.50. When both separators are there, the last one is the decimal point.
    A single separator followed by exactly three digits (`1,250`, `1.250`) could be a thousand or a fraction, so it is refused rather than guessed. Currency signs and spaces are ignored."""
    cleaned = "".join(ch for ch in str(text) if ch.isdigit() or ch in ",.-")
    if not any(ch.isdigit() for ch in cleaned):
        raise ValueError("not an amount")
    last = max(cleaned.rfind(","), cleaned.rfind("."))
    if last < 0:
        return as_decimal(cleaned)
    marks = [ch for ch in cleaned if ch in ",."]
    whole, fraction = cleaned[:last], cleaned[last + 1 :]
    if len(set(marks)) == 1 and (len(marks) > 1 or len(fraction) == THOUSAND_DIGITS):
        if len(marks) > 1 and len(fraction) == THOUSAND_DIGITS:
            return as_decimal(cleaned.replace(marks[0], ""))  # 1,250,000: the mark is only a thousands separator
        raise ValueError("ambiguous amount: write it with a decimal point and two decimals")
    return as_decimal(whole.replace(",", "").replace(".", "") + "." + fraction)


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
