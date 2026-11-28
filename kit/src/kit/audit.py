"""The check that a figure in an answer was really returned by a tool.

Figures are compared as exact signed decimals: no float, no rounding tolerance and no absolute value, so 1250.49 does not prove 1250.50 (or 1250.5, or 1,250), and -250.00 does not prove 250.00. A figure
a tool returned only in accounting brackets, `(250.00)`, proves the negative value and nothing else. Dates and years are ignored.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

_MINUS = "-−"  # hyphen-minus and the Unicode minus sign
_SMALL = 3  # a bare integer of fewer digits is a count (3 payments, 30 days), not a figure
_GROUP_ONLY = "\u00a0\u202f\u2009'"  # no-break, narrow no-break and thin space, apostrophe: only ever thousands separators
# A numeric token: digits with any separators between them (a final full stop or comma is punctuation, not part of the number). Only an ASCII
# letter, digit or underscore before it makes it part of an identifier (ACME2041); a kana, kanji or other letter does not, since Japanese and
# Chinese write figures directly after words (支払総額は5800円).
_TOKEN = re.compile(rf"(?<![A-Za-z0-9_.,])(?P<open>\()?(?P<sign>[{_MINUS}])?(?P<num>\d(?:[\d.,{_GROUP_ONLY}]*\d)?)(?P<close>\))?")
_WESTERN = re.compile(r"\d{1,3}(?:G\d{3})+")
_INDIAN = re.compile(r"\d{1,2}(?:G\d{2})*G\d{3}")  # lakh and crore grouping: 4,52,000 and 1,23,45,678


def _ascii(text: str) -> str:
    """Every decimal digit as ASCII (full-width, Devanagari, Arabic-Indic ...), and the full-width comma, full stop and minus as their ASCII forms;
    one character for one, so nothing else moves."""
    wide = {"，": ",", "．": ".", "－": "-"}
    return "".join(str(unicodedata.decimal(ch)) if ch.isdecimal() else wide.get(ch, ch) for ch in text)


def _readings(num: str) -> frozenset[Decimal] | None:
    """Every value the written number can validly stand for. The decimal separator, if any, is the last separator and occurs once; the other
    separators are one grouping character in Western threes or Indian lakh/crore groups. 480,00 reads only as 480.00, 1.234,5 only as 1234.5,
    4,52,000 only as 452000; 1,250 reads as 1250 or 1.25. None when no reading is valid (a version number, a malformed figure)."""
    seps = [ch for ch in num if not ch.isdigit()]
    if not seps:
        return frozenset({Decimal(num)})
    values: set[Decimal] = set()
    for point in (".", ",", None):
        whole, frac = num, ""
        if point is not None:
            if seps.count(point) != 1 or seps[-1] != point:
                continue
            whole, frac = num.rsplit(point, 1)
        group = {ch for ch in whole if not ch.isdigit()}
        if len(group) > 1 or group == {point}:
            continue
        if group:
            shape = re.sub(r"[^\d]", "G", whole)
            if not (_WESTERN.fullmatch(shape) or _INDIAN.fullmatch(shape)):
                continue
        values.add(Decimal(re.sub(r"[^\d]", "", whole) + ("." + frac if frac else "")))
    return frozenset(values) or None


def _tokens(text: str, brackets: bool) -> list[tuple[str, frozenset[Decimal] | None, int, int]]:
    """(the number as written, its signed readings, start, end) for every numeric token. `brackets`: an accounting bracket, (250.00), means negative."""
    out = []
    for m in _TOKEN.finditer(text):
        num = m.group("num")
        negative = bool(m.group("sign")) or (brackets and bool(m.group("open")) and bool(m.group("close")))
        readings = _readings(num)
        signed = None if readings is None else frozenset(-v if negative else v for v in readings)
        out.append((("-" if negative else "") + num, signed, m.start("num"), m.end("num")))
    return out


_YEAR = re.compile(r"(?:19|20)\d{2}")
_DOTTED_DATE = re.compile(r"\d{1,2}[.]\d{1,2}[.](?:19|20)\d{2}")
# A currency next to a bare 19xx/20xx makes it an amount, not a year (€2026, 2026 euro, ₹2026, 2026円).
_CURRENCY = re.compile(r"[€$£¥₹₽円元]|\b(?:eur|euro|euros|usd|gbp|jpy|inr|rub|chf|dollars?|pounds?|yen|rupees?|евро|рублей|руб|रुपये)\b", re.IGNORECASE)
_NEAR = 12


def _is_date(written: str, text: str, start: int, end: int) -> bool:
    """A calendar year or date, judged on the whole token: a bare 19xx/20xx with no currency beside it, or a dotted day.month.year. A token with a
    decimal or grouping part (2026.50, 2.026,50) is an amount and is always checked."""
    if _DOTTED_DATE.fullmatch(written):
        return True
    if not _YEAR.fullmatch(written):
        return False
    return not (_CURRENCY.search(text[max(0, start - _NEAR) : start]) or _CURRENCY.search(text[end : end + _NEAR]))


def unproven_figures(reply: str, tool_outputs: list[str]) -> list[float]:
    """Figures in the agent's reply (amounts with decimals or thousands, and any number of 3+ digits) that no tool returned, exactly and with the same sign. Dates and years are ignored.
    A figure is proven only by a tool figure with exactly the same set of readings, so a decimal comma is never dropped (480,99 is not proven by
    480,00) and an ambiguous 1,250 is proven by 1,250 but not by 1.25 or 1250 alone. Empty if the agent used no tool: it then states no data of yours."""
    if not tool_outputs:
        return []
    proven = {(readings if readings is not None else written) for out in tool_outputs for written, readings, _s, _e in _tokens(_ascii(out), brackets=True)}
    text = _ascii(reply)
    unproven: set[float] = set()
    for written, readings, start, end in _tokens(text, brackets=False):
        digits = sum(ch.isdigit() for ch in written)
        if digits < _SMALL and written.lstrip("-").isdigit():
            continue  # a small count (3 payments, 30 days) is not a figure
        if _is_date(written.lstrip("-"), text, start, end):
            continue  # a year or a date: the date check (answer.py) covers dates
        if (readings if readings is not None else written) not in proven:
            unproven.add(float(_first(written, readings)))
    return sorted(unproven)


def _first(written: str, readings: frozenset[Decimal] | None) -> Decimal:
    """The reading reported for an unproven figure: the value without a decimal comma when there is one (1,250 is reported as 1250.0)."""
    if readings is None:
        return Decimal(("-" if written.startswith("-") else "") + re.sub(r"[^\d]", "", written))
    return max(readings, key=abs)
